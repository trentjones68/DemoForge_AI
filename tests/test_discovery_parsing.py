from uuid import uuid4

import pytest
from demoforge_api.discovery.imports import (
    ManualPlaudExport,
    manual_original,
    parse_original,
    segment_text,
)
from demoforge_api.discovery.parser import MAX_TEXT
from discovery_fixtures import WORD_NS, docx, pdf
from fastapi import HTTPException


def test_word_and_pdf_are_extracted_outside_the_request_process() -> None:
    word = docx(
        f'<w:document xmlns:w="{WORD_NS}"><w:body>'
        "<w:p><w:r><w:t>[00:01:02] Ana: Synthetic notes.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>More detail.</w:t></w:r></w:p></w:body></w:document>"
    )
    extracted = parse_original(word, "docx")
    assert extracted == "[00:01:02] Ana: Synthetic notes.\nMore detail."
    assert parse_original(pdf(True), "pdf").strip() == "Synthetic PDF transcript"
    assert parse_original(b"\xef\xbb\xbf# Heading\r\n**Bold**\r\n", "md") == "# Heading\n**Bold**\n"


@pytest.mark.parametrize(
    ("raw", "fmt", "message"),
    [
        (pdf(False), "pdf", "Run OCR"),
        (pdf(False, 61), "pdf", "safe parsing limits"),
        (b"not a PDF", "pdf", "valid UTF-8"),
        (b"not a ZIP", "docx", "valid UTF-8"),
        (b"\xff\xfe", "txt", "valid UTF-8"),
        (b"ok\x00hidden", "txt", "valid UTF-8"),
        (pdf(True), "txt", "contents do not match"),
        (b"x" * (MAX_TEXT + 1), "md", "too much text"),
        (
            docx(f'<w:document xmlns:w="{WORD_NS}"/>', ("../bad.txt", b"text")),
            "docx",
            "safe parsing limits",
        ),
        (
            docx(f'<w:document xmlns:w="{WORD_NS}"/>', ("word/stuff.bin", b"x" * (9 << 20))),
            "docx",
            "safe parsing limits",
        ),
        (
            docx(
                '<!DOCTYPE word [<!ENTITY leak SYSTEM "file:///synthetic-private.txt">]>'
                f'<w:document xmlns:w="{WORD_NS}"><w:p><w:t>&leak;</w:t></w:p></w:document>'
            ),
            "docx",
            "valid UTF-8",
        ),
    ],
)
def test_unreadable_and_unsafe_inputs_have_safe_errors(raw: bytes, fmt: str, message: str) -> None:
    with pytest.raises(HTTPException) as failure:
        parse_original(raw, fmt)
    assert message in failure.value.detail


def test_file_mime_and_provenance() -> None:
    adapter = ManualPlaudExport()
    info = adapter.adapt("summary", "%2E%2E%2Fnotes%3C%3E.MD", "text/markdown")
    assert (info.provider, info.kind, info.method, info.filename) == (
        "plaud",
        "summary",
        "file",
        "notes__.md",
    )
    with pytest.raises(HTTPException) as failure:
        adapter.adapt("transcript", "meeting.pdf", "image/png")
    assert failure.value.status_code == 415
    assert manual_original("manual", "transcript", None, "text/plain; charset=utf-8").method == (
        "paste"
    )


def test_offsets_timing_and_stable_segment_ids() -> None:
    text = "[01:02:03.100 --> 01:02:05,15] Ana: Montréal 📊\nBo: Another point.\n" + "x" * 4100
    first, second, *continuation = segment_text(text)
    assert (first.speaker, first.start_ms, first.end_ms) == ("Ana", 3723100, 3725150)
    assert (second.speaker, second.start_ms) == ("Bo", None)
    assert len(continuation) == 2
    assert "".join(item.text for item in (first, second, *continuation)) == text
    assert text[first.start_offset : first.end_offset] == first.text
    assert text[second.start_offset : second.end_offset] == second.text
    source = uuid4()
    assert first.id(source) == segment_text(text)[0].id(source)
    assert first.id(source) != second.id(source)
    with pytest.raises(HTTPException) as failure:
        segment_text("x\n" * 3001)
    assert failure.value.status_code == 422


def test_timestamp_and_speaker_headers_apply_to_the_next_line() -> None:
    extracted = "[00:00:15]\nSpeaker 1\nFirst synthetic response.\n\nUnattributed.\n"
    _, _, response, blank, unattributed = segment_text(extracted)
    assert (response.speaker, response.start_ms) == ("Speaker 1", 15000)
    assert blank.speaker is None and unattributed.start_ms is None
