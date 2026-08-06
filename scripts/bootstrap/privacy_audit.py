#!/usr/bin/env python3
"""Fail closed when a release tree contains machine- or user-specific data.

By default a Git worktree audit covers tracked files plus untracked, non-ignored
files.  A plain directory is scanned recursively.  Ignored build trees and
virtual environments are deliberately outside the default release surface.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tokenize
import warnings
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
HDF5_SUFFIXES = {".h5", ".hdf5"}
PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png"}
OFFICE_ZIP_SUFFIXES = {
    ".docm",
    ".docx",
    ".dotm",
    ".dotx",
    ".odp",
    ".ods",
    ".odt",
    ".potm",
    ".potx",
    ".ppsm",
    ".ppsx",
    ".pptm",
    ".pptx",
    ".xlsm",
    ".xlsx",
    ".xltm",
    ".xltx",
}
OPEN_DOCUMENT_SUFFIXES = {".odp", ".ods", ".odt"}
OFFICE_XML_SUFFIXES = {".rels", ".xml"}
OFFICE_MEDIA_PREFIXES = ("pictures/", "ppt/media/", "word/media/", "xl/media/")
MAX_OFFICE_MEMBERS = 20_000
MAX_OFFICE_MEMBER_BYTES = 256 * 1024 * 1024
MAX_OFFICE_TOTAL_BYTES = 512 * 1024 * 1024
SKIP_DIRECTORY_NAMES = {".git"}

ABSOLUTE_HOME_RE = re.compile(
    r"(?<![A-Za-z0-9_${])/(?:home|Users)/[A-Za-z0-9._-]+",
    re.IGNORECASE,
)
WINDOWS_HOME_RE = re.compile(
    r"(?<![A-Za-z0-9_${])(?:file:/+)?[A-Za-z]:[\\/](?:Users|Documents and Settings)"
    r"[\\/][A-Za-z0-9._ -]+",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
HOST_FIELD_RE = re.compile(
    r"(?im)^\s*(?:host|hostname|machine_name)\s*[:=]\s*"
    r"(?!<redacted>|anonymous|portable|\$\{)[^\s#]+"
)
SECRET_RES = (
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")),
)
ALLOWED_EMAILS = {
    "anonymous@arena-rosnav.org",
    "charles.chen@example.invalid",
    "pgrr-test@example.invalid",
}
ALLOWED_IDENTITIES = {"anonymous", "anonymous authors", "charles chen"}


@dataclass(frozen=True, order=True)
class Finding:
    """A privacy violation without echoing its sensitive value."""

    path: str
    source: str
    rule: str
    line: int | None = None

    def display(self) -> str:
        location = f"{self.path}:{self.line}" if self.line is not None else self.path
        return f"{location}: {self.source}: {self.rule}"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _allowed_email(value: str) -> bool:
    normalized = value.casefold()
    if normalized in ALLOWED_EMAILS or normalized.endswith("@example.invalid"):
        return True
    return normalized.startswith("anonymous@")


def _allowed_identity(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return not normalized or normalized in ALLOWED_IDENTITIES


def _sensitive_literals(extra_forbidden: Iterable[str]) -> tuple[str, ...]:
    candidates: set[str] = set()
    current_home = str(Path.home())
    if current_home not in {"", "/"}:
        candidates.add(current_home)
    environment_home = os.environ.get("HOME", "").strip()
    if environment_home not in {"", "/"}:
        candidates.add(environment_home)
    current_hostname = socket.gethostname().strip()
    if current_hostname:
        candidates.add(current_hostname)
    candidates.update(value for value in extra_forbidden if value)
    return tuple(sorted(candidates, key=lambda value: (-len(value), value.casefold())))


def _literal_text(token_text: str) -> str | None:
    """Return a static string token's value without evaluating source code."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            value = ast.literal_eval(token_text)
    except (SyntaxError, ValueError):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return None


def _concatenated_string_literals(text: str) -> list[tuple[str, int]]:
    """Reconstruct Python-style literal ``+`` chains for privacy scanning.

    Splitting an identifier across quoted literals must not let it evade the
    release audit.  Tokenization plus ``ast.literal_eval`` handles ordinary and
    raw string prefixes without executing the inspected source.
    """

    if "'" not in text and '"' not in text:
        return []

    tokens: list[tokenize.TokenInfo] = []
    generator = tokenize.generate_tokens(io.StringIO(text).readline)
    try:
        tokens.extend(generator)
    except (IndentationError, tokenize.TokenError):
        # Non-Python text may not tokenize completely.  Tokens yielded before
        # the malformed region are still safe and useful to inspect.
        pass

    reconstructed: list[tuple[str, int]] = []
    skippable = {tokenize.COMMENT, tokenize.NL}
    index = 0
    while index < len(tokens):
        first = tokens[index]
        first_value = _literal_text(first.string) if first.type == tokenize.STRING else None
        if first_value is None:
            index += 1
            continue

        parts = [first_value]
        cursor = index + 1
        while cursor < len(tokens):
            while cursor < len(tokens) and tokens[cursor].type in skippable:
                cursor += 1
            if cursor < len(tokens) and tokens[cursor].type == tokenize.OP:
                if tokens[cursor].string != "+":
                    break
                cursor += 1
                while cursor < len(tokens) and tokens[cursor].type in skippable:
                    cursor += 1
            if cursor >= len(tokens) or tokens[cursor].type != tokenize.STRING:
                break
            next_value = _literal_text(tokens[cursor].string)
            if next_value is None:
                break
            parts.append(next_value)
            cursor += 1

        if len(parts) > 1:
            reconstructed.append(("".join(parts), first.start[0]))
            index = cursor
        else:
            index += 1
    return reconstructed


def _scan_text(
    text: str,
    relative_path: str,
    source: str,
    *,
    extra_forbidden: Iterable[str] = (),
) -> set[Finding]:
    findings: set[Finding] = set()
    sensitive_literals = _sensitive_literals(extra_forbidden)
    lowered = text.casefold()
    for literal in sensitive_literals:
        start = lowered.find(literal.casefold())
        if start >= 0:
            findings.add(
                Finding(
                    relative_path,
                    source,
                    "forbidden machine/user identifier",
                    _line_number(text, start) if source == "text" else None,
                )
            )
    assembled_literals = _concatenated_string_literals(text) if source == "text" else []
    for assembled, line in assembled_literals:
        assembled_lower = assembled.casefold()
        if any(literal.casefold() in assembled_lower for literal in sensitive_literals):
            findings.add(
                Finding(
                    relative_path,
                    source,
                    "forbidden machine/user identifier assembled from string literals",
                    line if source == "text" else None,
                )
            )
        if ABSOLUTE_HOME_RE.search(assembled) is not None:
            findings.add(
                Finding(
                    relative_path,
                    source,
                    "absolute home-directory path assembled from string literals",
                    line if source == "text" else None,
                )
            )
    home_match = ABSOLUTE_HOME_RE.search(text)
    if home_match is not None:
        findings.add(
            Finding(
                relative_path,
                source,
                "absolute home-directory path",
                _line_number(text, home_match.start()) if source == "text" else None,
            )
        )
    windows_home_match = WINDOWS_HOME_RE.search(text)
    if windows_home_match is not None:
        findings.add(
            Finding(
                relative_path,
                source,
                "absolute Windows home-directory path",
                _line_number(text, windows_home_match.start()) if source == "text" else None,
            )
        )
    host_match = HOST_FIELD_RE.search(text)
    if host_match is not None:
        findings.add(
            Finding(
                relative_path,
                source,
                "unredacted hostname field",
                _line_number(text, host_match.start()) if source == "text" else None,
            )
        )
    for match in EMAIL_RE.finditer(text):
        if not _allowed_email(match.group(0)):
            findings.add(
                Finding(
                    relative_path,
                    source,
                    "non-allowlisted email address",
                    _line_number(text, match.start()) if source == "text" else None,
                )
            )
            break
    for label, pattern in SECRET_RES:
        match = pattern.search(text)
        if match is not None:
            findings.add(
                Finding(
                    relative_path,
                    source,
                    label,
                    _line_number(text, match.start()) if source == "text" else None,
                )
            )
    return findings


def _printable_strings(payload: bytes, minimum_length: int = 4) -> str:
    strings = re.findall(rb"[\x20-\x7e]{%d,}" % minimum_length, payload)
    return "\n".join(value.decode("ascii", errors="ignore") for value in strings)


def _attribute_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _scan_hdf5_attributes(
    path: Path,
    relative_path: str,
    *,
    extra_forbidden: Iterable[str],
) -> set[Finding]:
    try:
        import h5py  # type: ignore[import-untyped]
    except ImportError:
        return {
            Finding(
                relative_path,
                "hdf5-attribute",
                "h5py unavailable; HDF5 attributes were not auditable",
            )
        }

    findings: set[Finding] = set()
    try:
        with h5py.File(path, "r") as handle:
            objects = [("/", handle)]

            def collect(name: str, item: object) -> None:
                objects.append((f"/{name}", item))

            handle.visititems(collect)
            for object_name, item in objects:
                attrs = getattr(item, "attrs", {})
                for attribute_name, value in attrs.items():
                    payload = _attribute_text(value)
                    object_findings = _scan_text(
                        payload,
                        relative_path,
                        "hdf5-attribute",
                        extra_forbidden=extra_forbidden,
                    )
                    if object_findings:
                        findings.update(object_findings)
                        findings.add(
                            Finding(
                                relative_path,
                                "hdf5-attribute",
                                f"sensitive attribute at {object_name}:{attribute_name}",
                            )
                        )
    except OSError:
        findings.add(Finding(relative_path, "hdf5-attribute", "unreadable HDF5 file"))
    return findings


def _scan_pdf_metadata(
    path: Path,
    relative_path: str,
    *,
    extra_forbidden: Iterable[str],
) -> set[Finding]:
    findings: set[Finding] = set()
    pdfinfo = shutil.which("pdfinfo")
    pdftotext = shutil.which("pdftotext")
    if pdfinfo is None:
        findings.add(
            Finding(
                relative_path,
                "pdf-metadata",
                "pdfinfo unavailable; PDF metadata was not auditable",
            )
        )
    else:
        completed = subprocess.run(
            [pdfinfo, str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            findings.add(Finding(relative_path, "pdf-metadata", "unreadable PDF metadata"))
        else:
            findings.update(
                _scan_text(
                    completed.stdout,
                    relative_path,
                    "pdf-metadata",
                    extra_forbidden=extra_forbidden,
                )
            )
            for line in completed.stdout.splitlines():
                key, separator, value = line.partition(":")
                if separator and key.strip().casefold() == "author" and value.strip():
                    if not _allowed_identity(value):
                        findings.add(
                            Finding(
                                relative_path,
                                "pdf-metadata",
                                "non-allowlisted PDF author",
                            )
                        )
    if pdftotext is None:
        findings.add(
            Finding(
                relative_path,
                "pdf-text",
                "pdftotext unavailable; compressed PDF text was not auditable",
            )
        )
    else:
        completed = subprocess.run(
            [pdftotext, "-enc", "UTF-8", str(path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            findings.add(Finding(relative_path, "pdf-text", "unreadable PDF text"))
        else:
            findings.update(
                _scan_text(
                    completed.stdout,
                    relative_path,
                    "pdf-text",
                    extra_forbidden=extra_forbidden,
                )
            )
    return findings


def _scan_image_payload(
    payload: bytes,
    relative_path: str,
    *,
    source: str,
    extra_forbidden: Iterable[str],
) -> set[Finding]:
    """Inspect compressed raster metadata supplied as bytes."""

    try:
        from PIL import ExifTags, Image
    except ImportError:
        return {
            Finding(
                relative_path,
                source,
                "Pillow unavailable; image metadata was not auditable",
            )
        }

    findings: set[Finding] = set()
    try:
        with Image.open(io.BytesIO(payload)) as image:
            metadata: list[tuple[str, object]] = [
                (str(key), value) for key, value in image.info.items()
            ]
            metadata.extend(
                (str(ExifTags.TAGS.get(key, key)), value) for key, value in image.getexif().items()
            )
    except (OSError, ValueError):
        return {Finding(relative_path, source, "unreadable image metadata")}

    for key, value in metadata:
        metadata_text = (
            _printable_strings(value) if isinstance(value, bytes) else _attribute_text(value)
        )
        metadata_findings = _scan_text(
            metadata_text,
            relative_path,
            source,
            extra_forbidden=extra_forbidden,
        )
        if metadata_findings:
            findings.update(metadata_findings)
            findings.add(
                Finding(
                    relative_path,
                    source,
                    f"sensitive image metadata field: {key}",
                )
            )
        if key.strip().casefold() in {"artist", "author"} and metadata_text.strip():
            if not _allowed_identity(metadata_text):
                findings.add(Finding(relative_path, source, "non-allowlisted image author"))
    return findings


def _scan_image_metadata(
    path: Path,
    relative_path: str,
    *,
    extra_forbidden: Iterable[str],
) -> set[Finding]:
    """Inspect compressed PNG/JPEG metadata, including EXIF text fields."""

    try:
        payload = path.read_bytes()
    except OSError:
        return {Finding(relative_path, "image-metadata", "unreadable image metadata")}
    return _scan_image_payload(
        payload,
        relative_path,
        source="image-metadata",
        extra_forbidden=extra_forbidden,
    )


def _xml_local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _decode_office_xml(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("office-xml", payload, 0, len(payload), "unsupported XML encoding")


def _scan_office_archive(
    path: Path,
    relative_path: str,
    *,
    extra_forbidden: Iterable[str],
) -> set[Finding]:
    """Inspect OOXML/OpenDocument contents instead of only ZIP container strings."""

    findings: set[Finding] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_OFFICE_MEMBERS:
                return {
                    Finding(
                        relative_path,
                        "office-archive",
                        "Office archive has too many members to audit safely",
                    )
                }
            total_size = sum(member.file_size for member in members)
            if total_size > MAX_OFFICE_TOTAL_BYTES:
                return {
                    Finding(
                        relative_path,
                        "office-archive",
                        "Office archive is too large to audit safely",
                    )
                }
            names = [member.filename for member in members if not member.is_dir()]
            if len(names) != len(set(names)):
                findings.add(
                    Finding(relative_path, "office-archive", "duplicate Office archive member")
                )
            normalized_names = {name.casefold() for name in names}
            required_core = (
                "meta.xml"
                if path.suffix.casefold() in OPEN_DOCUMENT_SUFFIXES
                else "docprops/core.xml"
            )
            if required_core not in normalized_names:
                findings.add(
                    Finding(
                        relative_path,
                        "office-core-properties",
                        f"required Office core properties are missing: {required_core}",
                    )
                )

            for member in members:
                if member.is_dir():
                    continue
                member_name = member.filename
                normalized_member = member_name.replace("\\", "/")
                member_path_findings = _scan_text(
                    unquote(member_name),
                    relative_path,
                    "office-member-path",
                    extra_forbidden=extra_forbidden,
                )
                if member_path_findings:
                    findings.update(member_path_findings)
                    findings.add(
                        Finding(
                            relative_path,
                            "office-member-path",
                            f"sensitive Office member name: {member_name}",
                        )
                    )
                if normalized_member.startswith("/") or ".." in normalized_member.split("/"):
                    findings.add(
                        Finding(
                            relative_path,
                            "office-archive",
                            "unsafe Office archive member path",
                        )
                    )
                if member.flag_bits & 0x1:
                    findings.add(
                        Finding(
                            relative_path,
                            "office-archive",
                            f"encrypted Office member is not auditable: {member_name}",
                        )
                    )
                    continue
                if member.file_size > MAX_OFFICE_MEMBER_BYTES:
                    findings.add(
                        Finding(
                            relative_path,
                            "office-archive",
                            f"Office member is too large to audit safely: {member_name}",
                        )
                    )
                    continue
                payload = archive.read(member)
                member_suffix = Path(normalized_member).suffix.casefold()
                if member_suffix in OFFICE_XML_SUFFIXES:
                    try:
                        decoded = _decode_office_xml(payload)
                        root = ElementTree.fromstring(payload)
                    except (ElementTree.ParseError, UnicodeDecodeError, ValueError):
                        findings.add(
                            Finding(
                                relative_path,
                                "office-xml",
                                f"malformed or undecodable Office XML: {member_name}",
                            )
                        )
                        continue
                    serialized = ElementTree.tostring(root, encoding="unicode")
                    xml_findings = _scan_text(
                        f"{decoded}\n{serialized}",
                        relative_path,
                        "office-xml",
                        extra_forbidden=extra_forbidden,
                    )
                    if xml_findings:
                        findings.update(xml_findings)
                        findings.add(
                            Finding(
                                relative_path,
                                "office-xml",
                                f"sensitive Office XML member: {member_name}",
                            )
                        )
                    for element in root.iter():
                        local_name = _xml_local_name(element.tag).casefold()
                        if local_name in {"creator", "initial-creator", "lastmodifiedby"}:
                            identity = "".join(element.itertext()).strip()
                            if not _allowed_identity(identity):
                                findings.add(
                                    Finding(
                                        relative_path,
                                        "office-core-properties",
                                        f"non-allowlisted Office {local_name}: {member_name}",
                                    )
                                )
                        if local_name != "relationship":
                            continue
                        attributes = {
                            _xml_local_name(key).casefold(): value
                            for key, value in element.attrib.items()
                        }
                        if attributes.get("targetmode", "").casefold() != "external":
                            continue
                        target = unquote(attributes.get("target", ""))
                        if not target:
                            findings.add(
                                Finding(
                                    relative_path,
                                    "office-external-relationship",
                                    f"empty external Office relationship: {member_name}",
                                )
                            )
                            continue
                        target_findings = _scan_text(
                            target,
                            relative_path,
                            "office-external-relationship",
                            extra_forbidden=extra_forbidden,
                        )
                        if target_findings:
                            findings.update(target_findings)
                            findings.add(
                                Finding(
                                    relative_path,
                                    "office-external-relationship",
                                    f"sensitive external Office relationship: {member_name}",
                                )
                            )
                    continue

                strings_findings = _scan_text(
                    _printable_strings(payload),
                    relative_path,
                    "office-member-strings",
                    extra_forbidden=extra_forbidden,
                )
                if strings_findings:
                    findings.update(strings_findings)
                    findings.add(
                        Finding(
                            relative_path,
                            "office-member-strings",
                            f"sensitive Office binary member: {member_name}",
                        )
                    )
                lowered_member = normalized_member.casefold()
                if lowered_member.startswith(OFFICE_MEDIA_PREFIXES):
                    if member_suffix in IMAGE_SUFFIXES:
                        media_findings = _scan_image_payload(
                            payload,
                            relative_path,
                            source="office-media-metadata",
                            extra_forbidden=extra_forbidden,
                        )
                        if media_findings:
                            findings.update(media_findings)
                            findings.add(
                                Finding(
                                    relative_path,
                                    "office-media-metadata",
                                    f"sensitive embedded Office media: {member_name}",
                                )
                            )
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        findings.add(Finding(relative_path, "office-archive", "unreadable Office ZIP archive"))
    return findings


def _git_files(root: Path) -> list[Path] | None:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    return [
        root / value.decode("utf-8", errors="surrogateescape")
        for value in completed.stdout.split(b"\0")
        if value
    ]


def _recursive_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if not any(part in SKIP_DIRECTORY_NAMES for part in path.relative_to(root).parts)
        and (path.is_file() or path.is_symlink())
    ]


def _candidate_files(root: Path, *, all_files: bool) -> list[Path]:
    candidates = None if all_files else _git_files(root)
    if candidates is None:
        candidates = _recursive_files(root)
    return sorted(
        {
            path
            for path in candidates
            if path.exists() or path.is_symlink()
            if not any(part in SKIP_DIRECTORY_NAMES for part in path.relative_to(root).parts)
        }
    )


def scan_tree(
    root: Path,
    *,
    all_files: bool = False,
    extra_forbidden: Iterable[str] = (),
) -> tuple[list[Finding], int]:
    """Return sorted findings and the number of audited files."""

    root = root.expanduser().resolve()
    findings: set[Finding] = set()
    files = _candidate_files(root, all_files=all_files)
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        findings.update(
            _scan_text(
                relative_path,
                relative_path,
                "path",
                extra_forbidden=extra_forbidden,
            )
        )
        if path.is_symlink():
            findings.update(
                _scan_text(
                    os.readlink(path),
                    relative_path,
                    "symlink",
                    extra_forbidden=extra_forbidden,
                )
            )
            continue
        try:
            payload = path.read_bytes()
        except OSError:
            findings.add(Finding(relative_path, "file", "unreadable file"))
            continue
        suffix = path.suffix.casefold()
        if suffix in HDF5_SUFFIXES:
            findings.update(
                _scan_hdf5_attributes(
                    path,
                    relative_path,
                    extra_forbidden=extra_forbidden,
                )
            )
        if suffix in PDF_SUFFIXES:
            findings.update(
                _scan_pdf_metadata(
                    path,
                    relative_path,
                    extra_forbidden=extra_forbidden,
                )
            )
        if suffix in IMAGE_SUFFIXES:
            findings.update(
                _scan_image_metadata(
                    path,
                    relative_path,
                    extra_forbidden=extra_forbidden,
                )
            )
        if suffix in OFFICE_ZIP_SUFFIXES:
            findings.update(
                _scan_office_archive(
                    path,
                    relative_path,
                    extra_forbidden=extra_forbidden,
                )
            )
        try:
            decoded = payload.decode("utf-8")
            is_text = b"\0" not in payload[:8192]
        except UnicodeDecodeError:
            decoded = ""
            is_text = False
        source = "text" if is_text else "binary-strings"
        searchable = decoded if is_text else _printable_strings(payload)
        findings.update(
            _scan_text(
                searchable,
                relative_path,
                source,
                extra_forbidden=extra_forbidden,
            )
        )
    return sorted(findings), len(files)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=ROOT,
        help="release tree to audit (default: repository root)",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="scan a plain recursive tree instead of the Git release surface",
    )
    parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        help="additional exact private value to reject; may be repeated",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: privacy audit root is not a directory: {root}", file=sys.stderr)
        return 2
    environment_forbidden = [
        value for value in os.environ.get("PGRR_PRIVACY_FORBIDDEN", "").split(os.pathsep) if value
    ]
    findings, file_count = scan_tree(
        root,
        all_files=args.all_files,
        extra_forbidden=[*args.forbid, *environment_forbidden],
    )
    if findings:
        print(f"Privacy audit FAIL: {len(findings)} finding(s) in {file_count} file(s)")
        for finding in findings:
            print(finding.display())
        return 1
    print(f"Privacy audit PASS: {file_count} file(s); no private identifiers found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
