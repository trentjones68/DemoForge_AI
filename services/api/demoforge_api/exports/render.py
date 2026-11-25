"""Bounded offline document rendering with controlled fonts and markup."""

import re
from collections.abc import Sequence
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
from time import monotonic
from typing import Literal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate

from demoforge_api.exports.document import Block

ExportFormat = Literal["md", "pdf"]
MAX_BYTES = 4 * 1024 * 1024
MAX_CHARACTERS = 150_000
MAX_PAGES = 80
MAX_PDF_SECONDS = 4
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
MARKDOWN_SYNTAX = re.compile(r"([\\`*_{}\[\]()#!~|:])")
MARKDOWN_BLOCK = re.compile(r"^(?:([-+])(?=\s|$)|(\d+)([.)])(?=\s|$)|(=+|-{3,})$)")
INK = colors.HexColor("#132547")
MUTED = colors.HexColor("#485871")
TEAL = colors.HexColor("#087F7A")
AMBER = colors.HexColor("#8B3D08")
CONTROLS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


class ExportBoundsError(ValueError):
    """The document exceeds the on-demand renderer bounds."""


class ExportFontsError(RuntimeError):
    """The controlled font package is missing."""


def plain_text(value: str) -> str:
    return " ".join(CONTROLS.sub("", value).split())


def markdown(blocks: Sequence[Block]) -> bytes:
    prefixes = {
        "title": "# ",
        "subtitle": "## ",
        "section": "## ",
        "subheading": "### ",
        "text": "",
        "bullet": "- ",
        "warning": "> ",
    }
    lines = ["<!-- DemoForge AI · Confidential -->"]
    for block in blocks:
        if block.kind != "check" and not (block.kind == "bullet" and lines[-1].startswith("- ")):
            lines.append("")
        value = MARKDOWN_SYNTAX.sub(r"\\\1", escape(plain_text(block.text), quote=False))
        value = MARKDOWN_BLOCK.sub(
            lambda match: match[2] + "\\" + match[3] if match[2] else "\\" + match[0], value
        )
        # Link destinations are server-generated, authenticated app URLs.
        if block.href:
            value = f"[{value}]({block.href})"
        prefix = (
            f"- [{'x' if block.checked else ' '}] "
            if block.kind == "check"
            else prefixes[block.kind]
        )
        lines.append(prefix + value)
    return ("\n".join(lines) + "\n").encode()


@lru_cache(maxsize=1)
def pdf_styles() -> dict[str, ParagraphStyle]:
    for name, filename in (("DemoSans", "DejaVuSans.ttf"), ("DemoSansBold", "DejaVuSans-Bold.ttf")):
        path = FONT_DIR / filename
        if not path.is_file():
            raise ExportFontsError("Install the DejaVu Sans font package")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    body = ParagraphStyle(
        "body",
        fontName="DemoSans",
        fontSize=9.5,
        leading=14,
        textColor=INK,
        spaceAfter=5,
        splitLongWords=True,
    )
    heading = ParagraphStyle("heading", parent=body, fontName="DemoSansBold", keepWithNext=True)
    return {
        "title": ParagraphStyle("title", parent=heading, fontSize=32, leading=39, spaceAfter=10),
        "subtitle": ParagraphStyle(
            "subtitle", parent=heading, fontSize=16, leading=22, spaceAfter=6
        ),
        "section": ParagraphStyle(
            "section",
            parent=heading,
            fontSize=17,
            leading=23,
            spaceBefore=18,
            spaceAfter=7,
            textColor=TEAL,
        ),
        "subheading": ParagraphStyle(
            "subheading", parent=heading, fontSize=10, leading=14, spaceBefore=7, spaceAfter=3
        ),
        "text": body,
        "bullet": ParagraphStyle("bullet", parent=body, leftIndent=13, spaceAfter=3),
        "check": ParagraphStyle("check", parent=body, leftIndent=4, spaceAfter=3),
        "warning": ParagraphStyle(
            "warning",
            parent=body,
            fontName="DemoSansBold",
            borderPadding=6,
            spaceBefore=7,
            spaceAfter=8,
            backColor=colors.HexColor("#FFF2E2"),
            textColor=AMBER,
        ),
    }


def pdf(blocks: Sequence[Block]) -> bytes:
    started = monotonic()
    styles = pdf_styles()
    stream = BytesIO()
    layout = SimpleDocTemplate(
        stream,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=68,
        bottomMargin=54,
        title="Demo storyboard",
        author="DemoForge AI",
        pageCompression=1,
    )

    def page(canvas: Canvas, _: SimpleDocTemplate) -> None:
        number = canvas.getPageNumber()
        if number > MAX_PAGES or monotonic() - started > MAX_PDF_SECONDS:
            raise ExportBoundsError("The PDF exceeded its rendering limits")
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.rect(0, height - 42, width, 42, stroke=0, fill=1)
        canvas.setFillColor(TEAL)
        canvas.rect(0, height - 45, width, 3, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("DemoSansBold", 11)
        canvas.drawString(48, height - 26, "DemoForge AI")
        canvas.setFont("DemoSans", 8)
        canvas.drawRightString(width - 48, height - 26, "DEMO PLANNING")
        canvas.setStrokeColor(colors.HexColor("#D7E2EA"))
        canvas.line(48, 39, width - 48, 39)
        canvas.setFillColor(MUTED)
        canvas.drawString(48, 25, "Confidential · Prepared in Demo Studio")
        canvas.drawRightString(width - 48, 25, f"Page {number}")
        canvas.restoreState()

    contents: list[Flowable] = []
    for block in blocks:
        value = escape(plain_text(block.text))
        if block.href:
            value = f'<link href="{escape(block.href, quote=True)}" color="#087F7A">{value}</link>'
        if block.kind == "check":
            value = ("[x] " if block.checked else "[ ] ") + value
        contents.append(
            Paragraph(value, styles[block.kind], bulletText="•" if block.kind == "bullet" else None)
        )
    layout.build(contents, onFirstPage=page, onLaterPages=page)
    if monotonic() - started > MAX_PDF_SECONDS:
        raise ExportBoundsError("The PDF exceeded its rendering limits")
    return stream.getvalue()


def render(blocks: Sequence[Block], fmt: ExportFormat) -> bytes:
    if sum(len(block.text) + len(block.href or "") for block in blocks) > MAX_CHARACTERS:
        raise ExportBoundsError("The storyboard is too large for an on-demand export")
    result = pdf(blocks) if fmt == "pdf" else markdown(blocks)
    if len(result) > MAX_BYTES:
        raise ExportBoundsError("The output exceeds the download limit")
    return result
