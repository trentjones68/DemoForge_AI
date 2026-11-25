"""Validate manual and Plaud export inputs before reserving private storage."""

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import BoundedSemaphore
from typing import Annotated, Literal, Protocol
from urllib.parse import unquote
from uuid import UUID, uuid5

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints

from demoforge_api.discovery.parser import FORMAT_MIME, MAX_SEGMENTS, MAX_TEXT, SEGMENT_LENGTH

SourceKind = Literal["transcript", "summary"]
Provider = Literal["manual", "plaud"]
Method = Literal["paste", "file"]

# A supplementary character can take two six-byte JSON escapes.
MAX_IMPORT_JSON = MAX_TEXT * 12 + 1024


class TextImport(BaseModel):
    """One authenticated text import into a discovery session."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    kind: SourceKind
    text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT)]
    provider: Provider = "manual"


PARSE_SLOTS = BoundedSemaphore(2)
ERRORS = {
    "invalid_document": "Use a valid UTF-8 text, Markdown, DOCX or text-based PDF.",
    "empty_document": "This source has no readable text.",
    "unsafe_document": "This document exceeds the safe parsing limits. Try a smaller export.",
    "text_limit": "This document expands to too much text. Split it into smaller sources.",
    "protected_pdf": "Export an unlocked PDF or upload a text transcript.",
    "scanned_pdf": "This PDF has no selectable text. Run OCR first or export as TXT.",
}
STAMP = r"(?:\d{1,3}:)?[0-5]?\d:[0-5]\d(?:[.,]\d{1,3})?"
TIMED = re.compile(
    rf"^\s*\[?(?P<start>{STAMP})(?:\s*(?:-->|[-–])\s*\[?(?P<end>{STAMP})\]?)?\]?(?=\s|$)"
)
SPEAKER_HEADER = re.compile(r"^\s*\[?(?P<label>Speaker \d{1,5})\]?\s*$", re.IGNORECASE)
SPEAKER = re.compile(r"^\s*(?P<label>[^\W\d_][\w .'-]{0,63}):(?=\s|$)")


@dataclass(frozen=True)
class Original:
    provider: Provider
    kind: SourceKind
    method: Method
    format: str
    filename: str | None


class PlaudImportAdapter(Protocol):
    def adapt(self, kind: SourceKind, filename: str | None, content_type: str) -> Original: ...


def manual_original(
    provider: Provider, kind: SourceKind, filename: str | None, content_type: str
) -> Original:
    parts = [part.strip().lower() for part in content_type.split(";")]
    mime = parts[0]
    if not filename:
        if mime != "text/plain":
            raise HTTPException(415, "Paste must be sent as UTF-8 plain text.")
        return Original(provider, kind, "paste", "txt", None)

    if len(filename) > 1536:
        raise HTTPException(422, "The source filename is too long.")
    try:
        decoded = unquote(filename, errors="strict").replace("\\", "/")
    except UnicodeError:
        raise HTTPException(422, "Invalid source filename.") from None
    basename = PurePosixPath(decoded).name
    stem, _, suffix = basename.rpartition(".")
    fmt = suffix.lower()
    if fmt not in FORMAT_MIME:
        raise HTTPException(415, "Upload a TXT, MD, DOCX or text-based PDF file.")
    accepted = {FORMAT_MIME[fmt], "application/octet-stream"}
    if fmt == "md":
        accepted.add("text/plain")
    if mime not in accepted:
        raise HTTPException(415, "The file type does not match the filename.")
    clean_stem = re.sub(r"[^a-zA-Z0-9 _.-]", "_", stem)[:110].strip(" .") or "original"
    return Original(provider, kind, "file", fmt, f"{clean_stem}.{fmt}")


class ManualPlaudExport:
    def adapt(self, kind: SourceKind, filename: str | None, content_type: str) -> Original:
        return manual_original("plaud", kind, filename, content_type)


def parse_original(raw: bytes, fmt: str) -> str:
    head = raw.removeprefix(b"\xef\xbb\xbf").lstrip()
    if fmt in ("txt", "md") and head.startswith((b"%PDF-", b"PK\x03\x04")):
        raise HTTPException(415, "The file contents do not match the text format.")
    if not PARSE_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "The document parser is busy. Try again shortly.")
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(Path(__file__).with_name("parser.py")), fmt],
            input=raw,
            capture_output=True,
            timeout=5,
            env={"LANG": "C.UTF-8"},
            cwd="/",
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(422, ERRORS["unsafe_document"]) from None
    except OSError:
        raise HTTPException(503, "Document parsing is unavailable.") from None
    finally:
        PARSE_SLOTS.release()

    if result.returncode != 0:
        code = result.stderr.decode("utf-8", errors="replace")
        if result.returncode < 0:
            code = "unsafe_document"
        raise HTTPException(422, ERRORS.get(code, ERRORS["invalid_document"]))
    return result.stdout.decode("utf-8")


@dataclass(frozen=True)
class Segment:
    ordinal: int
    start_offset: int
    end_offset: int
    text: str
    speaker: str | None
    start_ms: int | None
    end_ms: int | None

    def id(self, source: UUID) -> UUID:
        return uuid5(source, str(self.ordinal))


def milliseconds(value: str) -> int:
    whole, _, fraction = value.replace(",", ".").partition(".")
    seconds = 0
    for part in whole.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds * 1_000 + int(fraction.ljust(3, "0"))


def segment_text(text: str) -> list[Segment]:
    segments: list[Segment] = []
    offset = 0
    preceding_header: tuple[str | None, int | None, int | None] = (None, None, None)
    for line in text.splitlines(keepends=True):
        stamp = TIMED.match(line)
        remaining = line[stamp.end() :] if stamp else line
        speaker = SPEAKER.match(remaining) or SPEAKER_HEADER.match(remaining)
        prior_speaker, prior_start, prior_end = preceding_header
        label = speaker["label"].strip() if speaker else prior_speaker
        start_ms = milliseconds(stamp["start"]) if stamp else prior_start
        end_ms = (
            milliseconds(stamp["end"]) if stamp and stamp["end"] else (None if stamp else prior_end)
        )
        if start_ms is not None and end_ms is not None and end_ms < start_ms:
            end_ms = None
        following_text = remaining[speaker.end() :] if speaker else remaining
        preceding_header = (
            (label, start_ms, end_ms)
            if ((stamp or speaker) and not following_text.strip())
            else (None, None, None)
        )
        if not line.strip():
            label, start_ms, end_ms = (None, None, None)
        for start in range(0, len(line), SEGMENT_LENGTH):
            if len(segments) >= MAX_SEGMENTS:
                raise HTTPException(422, "This source has too many segments. Split the document.")
            chunk = line[start : start + SEGMENT_LENGTH]
            end = offset + len(chunk)
            segments.append(Segment(len(segments), offset, end, chunk, label, start_ms, end_ms))
            offset = end
    return segments
