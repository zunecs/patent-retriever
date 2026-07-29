"""Tests for the .docx renderer.

Most assertions run against `render_lines`, not the generated file. The line
list is the format; the .docx is just a container for it. Only two tests touch
python-docx at all, and they verify the container, not the content.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import docx

from patent_retriever.domain.models import Claim, Paragraph, PatentDocument, RenderOptions
from patent_retriever.renderers.docx_renderer import (
    render_docx,
    render_lines,
    render_text,
    write_docx,
)


def test_header_block_order(full_document: PatentDocument) -> None:
    lines = render_lines(
        full_document,
        RenderOptions(attorney_docket_number="ARM-1234", client_reference="CR-99"),
    )
    assert lines[0] == (
        "PATENT APPLICATION    ATTORNEY DOCKET NO. ARM-1234    CLIENT REF. NO. CR-99"
    )
    assert lines[1] == "APPLICATION FOR UNITED STATES LETTERS PATENT"
    assert lines[2] == "TITLE:"
    assert lines[3] == full_document.title
    assert lines[4] == "INVENTOR:"
    assert lines[5] == "Jane Doe, John Smith"


def test_title_repeats_after_inventor(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    assert lines[6] == ""
    assert lines[7] == full_document.title


def test_body_paragraphs_are_zero_padded_and_continuous(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    numbered = [line for line in lines if line.startswith("[")]
    prefixes = [line[:6] for line in numbered]
    assert prefixes == ["[0001]", "[0002]", "[0003]", "[0004]", "[0005]"]


def test_section_headings_appear_in_order(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    headings = [
        line
        for line in lines
        if line
        in {
            "BACKGROUND",
            "SUMMARY",
            "BRIEF DESCRIPTION OF DRAWINGS",
            "DETAILED DESCRIPTION",
            "CLAIMS",
            "ABSTRACT",
        }
    ]
    assert headings == [
        "BACKGROUND",
        "SUMMARY",
        "BRIEF DESCRIPTION OF DRAWINGS",
        "DETAILED DESCRIPTION",
        "CLAIMS",
        "ABSTRACT",
    ]


def test_empty_sections_are_omitted_entirely(minimal_document: PatentDocument) -> None:
    lines = render_lines(minimal_document)
    assert "BACKGROUND" not in lines
    assert "DETAILED DESCRIPTION" not in lines
    assert "CLAIMS" in lines


def test_claims_use_numeric_listing_not_brackets(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    claims_index = lines.index("CLAIMS")
    assert lines[claims_index + 1] == ""
    assert lines[claims_index + 2] == "What is claimed:"
    assert lines[claims_index + 3] == ""
    assert lines[claims_index + 4].startswith("1. ")
    assert lines[claims_index + 5].startswith("2. ")


def test_abstract_is_last_and_ends_with_figure_reference(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    assert lines[-1] == "Fig. 1."
    assert lines[-2] == full_document.abstract
    assert lines[-4] == "ABSTRACT"


def test_abstract_omitted_when_absent(minimal_document: PatentDocument) -> None:
    assert "ABSTRACT" not in render_lines(minimal_document)


def test_blank_line_precedes_every_section_heading(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    for heading in ("BACKGROUND", "SUMMARY", "CLAIMS", "ABSTRACT"):
        assert lines[lines.index(heading) - 1] == ""


def test_render_text_joins_lines(full_document: PatentDocument) -> None:
    assert render_text(full_document) == "\n".join(render_lines(full_document))


def test_render_docx_produces_a_valid_zip_container(full_document: PatentDocument) -> None:
    data = render_docx(full_document)
    assert data[:2] == b"PK"
    with zipfile.ZipFile(BytesIO(data)) as archive:
        assert "word/document.xml" in archive.namelist()


def test_docx_paragraphs_match_rendered_lines(full_document: PatentDocument) -> None:
    data = render_docx(full_document)
    word_document = docx.Document(BytesIO(data))
    assert [p.text for p in word_document.paragraphs] == render_lines(full_document)


def test_write_docx_creates_parent_directories(
    tmp_path: Path, full_document: PatentDocument
) -> None:
    target = tmp_path / "nested" / "out.docx"
    result = write_docx(full_document, target)
    assert result == target
    assert target.exists()
    assert target.stat().st_size > 0


def test_missing_render_options_produce_empty_reference_values() -> None:
    document = PatentDocument(
        publication_number="US1A",
        title="A Title",
        claims=(Claim(number=1, text="A method."),),
        background=(Paragraph(number=1, text="Some background."),),
    )
    lines = render_lines(document)
    assert lines[0] == "PATENT APPLICATION    ATTORNEY DOCKET NO.    CLIENT REF. NO."
