#!/usr/bin/env python3
"""Capture a mapped X11 application window without synthetic re-rendering.

The Arena runtime image already contains PyQt5 and X11, but intentionally does
not carry desktop screenshot utilities.  This helper enumerates genuine X11
windows and asks Qt to copy the selected window pixels from the X server.  It
then re-encodes the PNG with Pillow so host names and paths cannot leak through
ancillary PNG text chunks.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import math
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat
from PyQt5.QtWidgets import QApplication


@dataclass(frozen=True)
class WindowCandidate:
    window_id: int
    title: str
    width: int
    height: int


class X11Windows:
    """Small, read-only wrapper around the Xlib window-tree API."""

    def __init__(self) -> None:
        library_name = ctypes.util.find_library("X11")
        if library_name is None:
            raise RuntimeError("libX11 is unavailable")
        self._x11 = ctypes.cdll.LoadLibrary(library_name)
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._x11.XCloseDisplay.restype = ctypes.c_int
        self._x11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._x11.XRaiseWindow.restype = ctypes.c_int
        self._x11.XMoveResizeWindow.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        self._x11.XMoveResizeWindow.restype = ctypes.c_int
        self._x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._x11.XSync.restype = ctypes.c_int
        self._x11.XQueryTree.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self._x11.XQueryTree.restype = ctypes.c_int
        self._x11.XFetchName.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_char_p),
        ]
        self._x11.XFetchName.restype = ctypes.c_int
        self._x11.XGetGeometry.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self._x11.XGetGeometry.restype = ctypes.c_int
        self._x11.XFree.argtypes = [ctypes.c_void_p]
        self._x11.XFree.restype = ctypes.c_int
        self._display = self._x11.XOpenDisplay(None)
        if not self._display:
            raise RuntimeError("cannot connect to DISPLAY")

    def close(self) -> None:
        if self._display:
            self._x11.XCloseDisplay(self._display)
            self._display = None

    def _title(self, window_id: int) -> str:
        raw_name = ctypes.c_char_p()
        if not self._x11.XFetchName(
            self._display, ctypes.c_ulong(window_id), ctypes.byref(raw_name)
        ):
            return ""
        try:
            return raw_name.value.decode("utf-8", errors="replace") if raw_name.value else ""
        finally:
            if raw_name:
                self._x11.XFree(raw_name)

    def _geometry(self, window_id: int) -> tuple[int, int]:
        root = ctypes.c_ulong()
        x = ctypes.c_int()
        y = ctypes.c_int()
        width = ctypes.c_uint()
        height = ctypes.c_uint()
        border = ctypes.c_uint()
        depth = ctypes.c_uint()
        ok = self._x11.XGetGeometry(
            self._display,
            ctypes.c_ulong(window_id),
            ctypes.byref(root),
            ctypes.byref(x),
            ctypes.byref(y),
            ctypes.byref(width),
            ctypes.byref(height),
            ctypes.byref(border),
            ctypes.byref(depth),
        )
        return (int(width.value), int(height.value)) if ok else (0, 0)

    def _children(self, window_id: int) -> list[int]:
        root = ctypes.c_ulong()
        parent = ctypes.c_ulong()
        children = ctypes.POINTER(ctypes.c_ulong)()
        count = ctypes.c_uint()
        ok = self._x11.XQueryTree(
            self._display,
            ctypes.c_ulong(window_id),
            ctypes.byref(root),
            ctypes.byref(parent),
            ctypes.byref(children),
            ctypes.byref(count),
        )
        if not ok:
            return []
        try:
            return [int(children[index]) for index in range(count.value)]
        finally:
            if children:
                self._x11.XFree(children)

    def candidates(self) -> list[WindowCandidate]:
        root = int(self._x11.XDefaultRootWindow(self._display))
        pending = [root]
        visited: set[int] = set()
        result: list[WindowCandidate] = []
        while pending:
            window_id = pending.pop()
            if window_id in visited:
                continue
            visited.add(window_id)
            pending.extend(self._children(window_id))
            title = self._title(window_id).strip()
            if not title:
                continue
            width, height = self._geometry(window_id)
            result.append(WindowCandidate(window_id, title, width, height))
        return result

    def raise_window(self, window_id: int) -> None:
        """Raise a selected application before copying its visible pixels."""
        self._x11.XRaiseWindow(self._display, ctypes.c_ulong(window_id))
        self._x11.XSync(self._display, 0)

    def move_resize_window(self, window_id: int, width: int, height: int) -> None:
        """Fill the isolated Xvfb screen so the rendered scene stays legible."""
        self._x11.XMoveResizeWindow(
            self._display,
            ctypes.c_ulong(window_id),
            0,
            0,
            ctypes.c_uint(width),
            ctypes.c_uint(height),
        )
        self._x11.XSync(self._display, 0)


def _visual_statistics(path: Path) -> dict[str, float | int]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        if image.width < 640 or image.height < 480:
            raise RuntimeError(f"captured window is too small: {image.width}x{image.height}")
        thumbnail = image.copy()
        thumbnail.thumbnail((320, 240))
        stat = ImageStat.Stat(thumbnail.convert("L"))
        grayscale_stddev = float(stat.stddev[0])
        colors = thumbnail.getcolors(maxcolors=thumbnail.width * thumbnail.height)
        unique_colors = len(colors) if colors is not None else thumbnail.width * thumbnail.height
        if not math.isfinite(grayscale_stddev) or grayscale_stddev < 5.0:
            raise RuntimeError(
                "captured window has insufficient visual variation; GUI rendering likely failed"
            )
        if unique_colors < 64:
            raise RuntimeError(
                "captured window has too few colors; refusing a blank or placeholder frame"
            )
        # Gazebo's Scene3D viewport occupies the left portion below the two
        # toolbars.  Under software GL the X11 window may be mapped before the
        # front render buffer is ready; in that case the rest of the GUI is
        # colorful enough to pass a whole-window check while the actual scene
        # remains flat gray.  Validate the scene region independently.
        scene = image.crop(
            (
                0,
                int(image.height * 0.16),
                int(image.width * 0.58),
                int(image.height * 0.96),
            )
        )
        scene.thumbnail((320, 240))
        scene_stat = ImageStat.Stat(scene.convert("L"))
        scene_stddev = float(scene_stat.stddev[0])
        scene_colors = scene.getcolors(maxcolors=scene.width * scene.height)
        scene_unique_colors = (
            len(scene_colors) if scene_colors is not None else scene.width * scene.height
        )
        if scene_stddev < 15.0 or scene_unique_colors < 300:
            raise RuntimeError(
                "Gazebo Scene3D viewport is not populated yet; refusing a gray GUI frame"
            )
        return {
            "width_px": image.width,
            "height_px": image.height,
            "grayscale_stddev": round(grayscale_stddev, 4),
            "thumbnail_unique_colors": unique_colors,
            "scene_viewport_grayscale_stddev": round(scene_stddev, 4),
            "scene_viewport_unique_colors": scene_unique_colors,
        }


def _strip_png_metadata(path: Path) -> None:
    with Image.open(path) as source:
        clean = source.convert("RGB")
    temporary = path.with_suffix(path.suffix + ".clean.tmp")
    clean.save(temporary, format="PNG", optimize=True)
    temporary.replace(path)


def capture_window(
    output: Path,
    title_pattern: str,
    *,
    timeout_s: float,
    info_output: Path | None = None,
    capture_context: dict[str, Any] | None = None,
    resize_width: int | None = None,
    resize_height: int | None = None,
) -> dict[str, Any]:
    if timeout_s <= 0 or not math.isfinite(timeout_s):
        raise ValueError("timeout_s must be finite and positive")
    if (resize_width is None) != (resize_height is None):
        raise ValueError("capture resize width and height must be provided together")
    if resize_width is not None and resize_height is not None:
        if resize_width < 640 or resize_height < 480:
            raise ValueError("capture resize must be at least 640x480")
    pattern = re.compile(title_pattern, flags=re.IGNORECASE)
    application = QApplication.instance() or QApplication(["pgrr-x11-capture"])
    deadline = time.monotonic() + timeout_s
    selected: WindowCandidate | None = None
    observed: list[WindowCandidate] = []
    while time.monotonic() < deadline:
        windows = X11Windows()
        try:
            observed = windows.candidates()
        finally:
            windows.close()
        matches = [
            candidate
            for candidate in observed
            if pattern.search(candidate.title)
            and candidate.width >= 640
            and candidate.height >= 480
        ]
        if matches:
            selected = max(matches, key=lambda item: item.width * item.height)
            break
        application.processEvents()
        time.sleep(0.5)
    if selected is None:
        titles = sorted({candidate.title for candidate in observed})
        raise RuntimeError(
            "no matching mapped X11 window; observed titles=" + json.dumps(titles[:30])
        )
    windows = X11Windows()
    try:
        # Gazebo's QtQuick Scene3D render buffer does not reliably resize under
        # a bare Xvfb server without a window manager.  Forcing the top-level
        # X11 geometry can therefore surround the unchanged live render buffer
        # with blank backing pixels.  Preserve the mapped native window unless
        # a caller explicitly requests a resize.
        if resize_width is not None and resize_height is not None:
            windows.move_resize_window(selected.window_id, resize_width, resize_height)
        windows.raise_window(selected.window_id)
    finally:
        windows.close()
    application.processEvents()
    time.sleep(1.0)
    windows = X11Windows()
    try:
        refreshed = next(
            (
                candidate
                for candidate in windows.candidates()
                if candidate.window_id == selected.window_id
            ),
            None,
        )
    finally:
        windows.close()
    if refreshed is not None:
        selected = refreshed
    screen = application.primaryScreen()
    if screen is None:
        raise RuntimeError("Qt did not expose an X11 screen")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".capture.tmp.png")
    render_deadline = time.monotonic() + timeout_s
    visual: dict[str, float | int] | None = None
    last_render_error = "Gazebo Scene3D viewport did not render"
    try:
        while time.monotonic() < render_deadline:
            pixmap = screen.grabWindow(selected.window_id)
            if pixmap.isNull() or not pixmap.save(str(temporary), "PNG"):
                last_render_error = f"failed to capture X11 window {selected.window_id}"
            else:
                _strip_png_metadata(temporary)
                try:
                    visual = _visual_statistics(temporary)
                except RuntimeError as error:
                    last_render_error = str(error)
                else:
                    temporary.replace(output)
                    break
            application.processEvents()
            time.sleep(0.75)
    finally:
        temporary.unlink(missing_ok=True)
    if visual is None:
        raise RuntimeError(last_render_error)
    result: dict[str, Any] = {
        "capture_backend": "PyQt5.QScreen.grabWindow(X11 window)",
        "selected_window": asdict(selected),
        "visual_validation": visual,
    }
    if capture_context is not None:
        result["capture_context"] = capture_context
    if info_output is not None:
        info_output.parent.mkdir(parents=True, exist_ok=True)
        info_output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title-pattern", default=r"Gazebo|gz sim")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--info-output", type=Path)
    parser.add_argument("--capture-context", type=json.loads)
    parser.add_argument("--resize-width", type=int)
    parser.add_argument("--resize-height", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = capture_window(
            args.output,
            args.title_pattern,
            timeout_s=args.timeout,
            info_output=args.info_output,
            capture_context=args.capture_context,
            resize_width=args.resize_width,
            resize_height=args.resize_height,
        )
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
