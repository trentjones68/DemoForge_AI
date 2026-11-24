"""Bounded, offline document parser. The API runs this module in a subprocess."""

import logging
import os
import re
import resource
import sys
import sysconfig
import warnings
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

MAX_UPLOAD = 2 * 1024 * 1024
MAX_TEXT = 250_000
MAX_SEGMENTS = 3_000
SEGMENT_LENGTH = 4_000
FORMAT_MIME = {
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
WORD_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
RUNTIME_DIRS = tuple(
    sysconfig.get_path(name).rstrip("/") + "/" for name in ("stdlib", "platstdlib", "purelib")
)
BAD_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ParseFailure(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def docx_text(raw: bytes) -> str:
    if not raw.startswith(b"PK\x03\x04"):
        raise ParseFailure("invalid_document")
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = {entry.filename for entry in entries}
        if (
            len(entries) > 128
            or len(entries) != len(names)
            or sum(entry.file_size for entry in entries) > 8 * 1024 * 1024
            or any(
                entry.flag_bits & 1
                or "\\" in entry.filename
                or PurePosixPath(entry.filename).is_absolute()
                or ".." in PurePosixPath(entry.filename).parts
                or entry.filename.casefold().endswith("vbaproject.bin")
                for entry in entries
            )
        ):
            raise ParseFailure("unsafe_document")
        if not {"[Content_Types].xml", "word/document.xml"} <= names:
            raise ParseFailure("invalid_document")
        with archive.open("[Content_Types].xml") as types_file:
            types = types_file.read(64 * 1024 + 1)
        if len(types) > 64 * 1024:
            raise ParseFailure("unsafe_document")
        manifest = fromstring(types, forbid_dtd=True)
        if manifest.tag != TYPES + "Types" or not any(
            override.get("PartName") == "/word/document.xml"
            and override.get("ContentType") == WORD_CONTENT_TYPE
            for override in manifest.findall(TYPES + "Override")
        ):
            raise ParseFailure("invalid_document")
        with archive.open("word/document.xml") as document:
            xml = document.read(4 * 1024 * 1024 + 1)
        if len(xml) > 4 * 1024 * 1024:
            raise ParseFailure("unsafe_document")
    root = fromstring(xml, forbid_dtd=True)
    if root.tag != WORD + "document":
        raise ParseFailure("invalid_document")

    parts: list[str] = []
    for item in root.iter(WORD + "p"):
        pieces: list[str] = []
        for child in item.iter():
            match child.tag:
                case tag if tag == WORD + "t":
                    pieces.append(child.text or "")
                case tag if tag == WORD + "tab":
                    pieces.append("\t")
                case tag if tag in (WORD + "br", WORD + "cr"):
                    pieces.append("\n")
        parts.append("".join(pieces))
    return "\n".join(parts)


def pdf_text(raw: bytes) -> str:
    if not re.match(rb"%PDF-[0-9]\.[0-9]", raw):
        raise ParseFailure("invalid_document")
    reader = PdfReader(BytesIO(raw), strict=True)
    if reader.is_encrypted:
        raise ParseFailure("protected_pdf")
    if len(reader.pages) > 60:
        raise ParseFailure("unsafe_document")
    pages: list[str] = []
    length = 0
    for page in reader.pages:
        extracted = page.extract_text()
        length += len(extracted) + 2
        if length > MAX_TEXT:
            raise ParseFailure("text_limit")
        pages.append(extracted)
    result = "\n\n".join(pages)
    if not result.strip():
        raise ParseFailure("scanned_pdf")
    return result


def extract(raw: bytes, fmt: str) -> str:
    if not raw or len(raw) > MAX_UPLOAD:
        raise ParseFailure("invalid_document")
    match fmt:
        case "txt" | "md":
            result = raw.decode("utf-8-sig")
        case "docx":
            result = docx_text(raw)
        case "pdf":
            result = pdf_text(raw)
        case _:
            raise ParseFailure("invalid_document")
    result = result.replace("\r\n", "\n").replace("\r", "\n")
    if len(result) > MAX_TEXT:
        raise ParseFailure("text_limit")
    if BAD_CONTROL.search(result):
        raise ParseFailure("invalid_document")
    if not result.strip():
        raise ParseFailure("empty_document")
    return result


def offline(event: str, args: tuple[object, ...]) -> None:
    if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn", "os.system")):
        raise PermissionError("Document parsing is offline")
    if event == "open" and not (
        isinstance(args[0], str)
        and ".." not in PurePosixPath(args[0]).parts
        and args[0].startswith(RUNTIME_DIRS)
        and args[0].endswith((".py", ".pyc", ".so"))
        and isinstance(args[2], int)
        and not args[2] & (os.O_ACCMODE | os.O_CREAT | os.O_TRUNC)
    ):
        raise PermissionError("Document parsing cannot open external files")


def main() -> None:
    # Apply limits before accessing the original. The parent enforces a wall-clock limit.
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.addaudithook(offline)
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)
    try:
        extracted = extract(sys.stdin.buffer.read(MAX_UPLOAD + 1), sys.argv[1])
        sys.stdout.buffer.write(extracted.encode("utf-8"))
    except ParseFailure as error:
        sys.stderr.write(error.code)
        raise SystemExit(1) from None
    except (ValueError, MemoryError):
        sys.stderr.write("invalid_document")
        raise SystemExit(1) from None
    except Exception:
        # Third-party parsers may raise exceptions containing source data.
        sys.stderr.write("invalid_document")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
