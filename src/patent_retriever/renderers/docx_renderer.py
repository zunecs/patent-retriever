"""Render a PatentDocument into the format required by the Patent Translation tool.

The exact structure is specified in docs/output-format.md.

The module builds a list of plain-text lines first, then maps those lines onto
Word paragraphs. Two reasons:

1. The line list is trivial to assert in tests. Verifying the format by parsing
   a generated .docx is slow, brittle, and hard to read in a failure message.
2. The same line list gives the web interface a free text preview, with no
   duplicated formatting logic.

An empty string in the line list means a blank line, which becomes an empty
Word paragraph.
"""

from __future__ import annotations

import io
from pathlib import Path

import docx
from docx.shared import Inches, Pt

from patent_retriever.domain.models import PatentDocument, RenderOptions
import re


DEFAULT_FONT_NAME = "Times New Roman"
DEFAULT_FONT_SIZE_PT = 12

CLAIMS_HEADING = "CLAIMS"
CLAIMS_SUBHEADING = "What is claimed:"
ABSTRACT_HEADING = "ABSTRACT"
PARAGRAPH_ID_INDENT_INCHES = 0.6
_NUMBERED_LINE = re.compile(r"^\[\d{4}\] ")


def _header_lines(document: PatentDocument, options: RenderOptions) -> list[str]:
    """Build the metadata block at the top of the document.

    The title repeats after the inventor line, per the format specification.
    """
    docket = f"ATTORNEY DOCKET NO. {options.attorney_docket_number}".rstrip()
    client_ref = f"CLIENT REF. NO. {options.client_reference}".rstrip()

    return [
        f"PATENT APPLICATION    {docket}    {client_ref}",
        "APPLICATION FOR UNITED STATES LETTERS PATENT",
        "TITLE:",
        document.title,
        "INVENTOR:",
        ", ".join(document.inventors),
        "",
        document.title,
    ]


def _body_lines(document: PatentDocument) -> list[str]:
    """Build the four numbered body sections.

    Sections with no paragraphs are omitted entirely - heading included - so the
    output never contains an empty heading. Paragraph numbers are formatted here
    as four-digit zero-padded brackets; the model stores plain integers.
    """
    lines: list[str] = []
    for heading, paragraphs in document.body_sections():
        if not paragraphs:
            continue
        lines.append("")
        lines.append(heading)
        lines.append("")
        lines.extend(f"[{paragraph.number:04d}] {paragraph.text}" for paragraph in paragraphs)
    return lines


def _claims_lines(document: PatentDocument) -> list[str]:
    """Build the claims section.

    Claims switch from bracketed IDs to a plain numeric listing.
    """
    lines = ["", CLAIMS_HEADING, "", CLAIMS_SUBHEADING, ""]
    lines.extend(f"{claim.number}. {claim.text}" for claim in document.claims)
    return lines


def _abstract_lines(document: PatentDocument) -> list[str]:
    """Build the abstract, which closes the document and carries no numbering."""
    if not document.abstract:
        return []
    lines = ["", ABSTRACT_HEADING, "", document.abstract]
    if document.abstract_figure_reference:
        lines.append(document.abstract_figure_reference)
    return lines


def render_lines(document: PatentDocument, options: RenderOptions | None = None) -> list[str]:
    """Return the full document as a list of lines, one per Word paragraph.

    The document is renumbered first: the output format requires an unbroken
    paragraph sequence across all four body sections, which sources rarely give.
    """
    options = options or RenderOptions()
    normalized = document.renumbered()

    return [
        *_header_lines(normalized, options),
        *_body_lines(normalized),
        *_claims_lines(normalized),
        *_abstract_lines(normalized),
    ]


def render_text(document: PatentDocument, options: RenderOptions | None = None) -> str:
    """Return the document as plain text. Used for previews."""
    return "\n".join(render_lines(document, options))


def render_docx(document: PatentDocument, options: RenderOptions | None = None) -> bytes:
    """Return the document as .docx bytes.

    Returning bytes rather than writing to a path keeps this function free of
    filesystem concerns, which is what lets the Flask interface stream the file
    straight to the browser without a temporary file.
    """
    word_document = docx.Document()

    normal_style = word_document.styles["Normal"]
    normal_style.font.name = DEFAULT_FONT_NAME
    normal_style.font.size = Pt(DEFAULT_FONT_SIZE_PT)

    for line in render_lines(document, options):
        paragraph = word_document.add_paragraph(line)
        if _NUMBERED_LINE.match(line):
            paragraph.paragraph_format.left_indent = Inches(PARAGRAPH_ID_INDENT_INCHES)
            paragraph.paragraph_format.first_line_indent = Inches(-PARAGRAPH_ID_INDENT_INCHES)

    buffer = io.BytesIO()
    word_document.save(buffer)
    return buffer.getvalue()


def write_docx(
    document: PatentDocument,
    path: Path,
    options: RenderOptions | None = None,
) -> Path:
    """Write the rendered document to disk and return the path written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_docx(document, options))
    return path
