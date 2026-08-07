#!/usr/bin/env python3
"""Render a compact 5x6 visual audit sheet for the 30-page briefing PDF."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ContactSheetError(RuntimeError):
    """Raised when the PDF cannot be rendered into exactly 30 thumbnails."""


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def make_contact_sheet(pdf: Path, output: Path) -> None:
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise ContactSheetError(f"presentation PDF is missing or empty: {pdf}")
    executable = shutil.which("pdftoppm")
    if executable is None:
        raise ContactSheetError("pdftoppm is required to build the presentation contact sheet")
    with tempfile.TemporaryDirectory(prefix="pgrr-contact-") as directory:
        destination = Path(directory) / "slide"
        subprocess.run(
            [executable, "-png", "-r", "72", str(pdf), str(destination)],
            check=True,
            capture_output=True,
            text=True,
        )
        pages = sorted(
            Path(directory).glob("slide-*.png"),
            key=lambda path: int(path.stem.rsplit("-", maxsplit=1)[1]),
        )
        if len(pages) != 30:
            raise ContactSheetError(f"expected 30 rendered pages, found {len(pages)}")

        columns, rows = 5, 6
        thumb_width, thumb_height = 320, 180
        label_height, gap, margin = 24, 14, 20
        canvas_width = margin * 2 + columns * thumb_width + (columns - 1) * gap
        canvas_height = margin * 2 + rows * (thumb_height + label_height) + (rows - 1) * gap
        canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
        draw = ImageDraw.Draw(canvas)
        label_font = _font(16)
        for index, page in enumerate(pages):
            row, column = divmod(index, columns)
            x = margin + column * (thumb_width + gap)
            y = margin + row * (thumb_height + label_height + gap)
            with Image.open(page) as source:
                image = source.convert("RGB")
                image.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
                offset_x = x + (thumb_width - image.width) // 2
                offset_y = y + (thumb_height - image.height) // 2
                canvas.paste(image, (offset_x, offset_y))
            draw.rectangle(
                (x, y, x + thumb_width, y + thumb_height),
                outline="#D7DDE1",
                width=1,
            )
            draw.text(
                (x, y + thumb_height + 2),
                f"{index + 1:02d}",
                fill="#59636B",
                font=label_font,
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="PNG", optimize=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise ContactSheetError(f"contact sheet was not created: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=PROJECT_ROOT / "presentation/PGRR_report_zh.pdf",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "presentation/contact_sheet.png",
    )
    args = parser.parse_args()
    try:
        make_contact_sheet(args.pdf, args.output)
    except (ContactSheetError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Contact sheet PASS: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
