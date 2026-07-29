"""Tests for the .docx renderer.

Structure is asserted through `render_blocks` and `render_lines`. Only the tests
that genuinely concern the Word container - numbering XML, the running header,
page setup - open the generated file.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import docx
import pytest
from docx.enum.text import WD_ALIGN_PARAGRAPH

from patent_retriever.domain.models import Claim, Paragraph, PatentDocument, RenderOptions
from patent_retriever.renderers.docx_renderer import (
    Kind,
    normalize_figure_reference,
    render_blocks,
    render_docx,
    render_lines,
    render_text,
    write_docx,
)

OPTIONS = RenderOptions(attorney_docket_number="18733-1843001", client_reference="SA918489")


def kinds(document: PatentDocument) -> list[Kind]:
    return [block.kind for block in render_blocks(document)]


def test_cover_page_opens_with_three_centred_lines(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    start = lines.index("APPLICATION")
    assert lines[start : start + 3] == ["APPLICATION", "FOR", "UNITED STATES LETTERS PATENT"]
    assert lines[:start] == [""] * start


def test_title_and_inventor_labels_use_tabs(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    assert f"TITLE:\t\t{full_document.title}" in lines
    assert "INVENTOR:\tJane Doe, John Smith" in lines


def test_title_repeats_after_the_page_break(full_document: PatentDocument) -> None:
    block_kinds = kinds(full_document)
    break_index = block_kinds.index(Kind.PAGE_BREAK)
    assert block_kinds[break_index + 1] is Kind.DOC_TITLE


def test_docket_and_client_ref_are_not_in_the_body(full_document: PatentDocument) -> None:
    text = render_text(full_document, OPTIONS)
    assert "18733-1843001" not in text
    assert "CLIENT REF. NO." not in text


def test_no_blank_line_between_heading_and_first_paragraph(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    assert lines[lines.index("BACKGROUND") + 1].startswith("[0001] ")


def test_body_paragraphs_are_numbered_continuously(full_document: PatentDocument) -> None:
    prefixes = [line[:6] for line in render_lines(full_document) if line.startswith("[")]
    assert prefixes == ["[0001]", "[0002]", "[0003]", "[0004]", "[0005]"]


def test_section_headings_appear_in_order(full_document: PatentDocument) -> None:
    expected = [
        "BACKGROUND",
        "SUMMARY",
        "BRIEF DESCRIPTION OF DRAWINGS",
        "DETAILED DESCRIPTION",
        "CLAIMS",
        "ABSTRACT",
    ]
    lines = render_lines(full_document)
    assert [line for line in lines if line in expected] == expected


def test_empty_sections_are_omitted(minimal_document: PatentDocument) -> None:
    lines = render_lines(minimal_document)
    assert "BACKGROUND" not in lines
    assert "CLAIMS" in lines


def test_claims_use_literal_numeric_prefixes(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    index = lines.index("CLAIMS")
    assert lines[index + 1] == "What is claimed:"
    assert lines[index + 2] == ""
    assert lines[index + 3].startswith("1. ")
    assert lines[index + 4].startswith("2. ")


def test_abstract_closes_the_document(full_document: PatentDocument) -> None:
    lines = render_lines(full_document)
    assert lines[-1] == "Fig.1."
    assert lines[-2] == full_document.abstract
    assert lines[-3] == "ABSTRACT"


def test_abstract_omitted_when_absent(minimal_document: PatentDocument) -> None:
    assert "ABSTRACT" not in render_lines(minimal_document)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FIG. 1", "Fig.1."),
        ("Fig. 1.", "Fig.1."),
        ("fig 3A", "Fig.3A."),
        ("Fig.2.", "Fig.2."),
        (None, None),
        ("no reference here", None),
    ],
)
def test_figure_reference_is_normalized(raw: str | None, expected: str | None) -> None:
    assert normalize_figure_reference(raw) == expected


def test_render_text_joins_lines(full_document: PatentDocument) -> None:
    assert render_text(full_document) == "\n".join(render_lines(full_document))


def test_docx_is_a_valid_word_container(full_document: PatentDocument) -> None:
    data = render_docx(full_document, OPTIONS)
    assert data[:2] == b"PK"
    with zipfile.ZipFile(BytesIO(data)) as archive:
        assert "word/document.xml" in archive.namelist()


def test_custom_four_digit_numbering_is_defined(full_document: PatentDocument) -> None:
    with zipfile.ZipFile(BytesIO(render_docx(full_document))) as archive:
        numbering = archive.read("word/numbering.xml").decode()
    assert 'w:format="0001, 0002, 0003, ..."' in numbering
    assert 'w:lvlText w:val="[%1]"' in numbering


def test_body_paragraphs_reference_the_list(full_document: PatentDocument) -> None:
    with zipfile.ZipFile(BytesIO(render_docx(full_document))) as archive:
        body = archive.read("word/document.xml").decode()
    assert 'w:numId w:val="900"' in body


def test_running_header_carries_the_reference_numbers(full_document: PatentDocument) -> None:
    with zipfile.ZipFile(BytesIO(render_docx(full_document, OPTIONS))) as archive:
        header_name = next(n for n in archive.namelist() if n.startswith("word/header"))
        header = archive.read(header_name).decode()
    assert "PATENT APPLICATION" in header
    assert "18733-1843001" in header
    assert "SA918489" in header


def test_header_is_right_aligned_and_tight(full_document: PatentDocument) -> None:
    word_document = docx.Document(BytesIO(render_docx(full_document, OPTIONS)))
    header = word_document.sections[0].header
    assert [p.text for p in header.paragraphs] == [
        "PATENT APPLICATION",
        "ATTORNEY DOCKET NO. 18733-1843001",
        "CLIENT REF. NO. SA918489",
    ]
    for paragraph in header.paragraphs:
        assert paragraph.alignment == WD_ALIGN_PARAGRAPH.RIGHT
        assert paragraph.paragraph_format.space_after.pt == 0


def test_page_setup_matches_the_sample(full_document: PatentDocument) -> None:
    section = docx.Document(BytesIO(render_docx(full_document))).sections[0]
    assert section.top_margin.inches == pytest.approx(1.2)
    assert section.bottom_margin.inches == pytest.approx(1.0)
    assert section.left_margin.inches == pytest.approx(1.0)
    assert section.right_margin.inches == pytest.approx(1.0)


def test_normal_style_matches_the_sample(full_document: PatentDocument) -> None:
    normal = docx.Document(BytesIO(render_docx(full_document))).styles["Normal"]
    assert normal.font.name == "Times New Roman"
    assert normal.font.size.pt == 13
    assert normal.paragraph_format.line_spacing == 1.5
    assert normal.paragraph_format.space_after.pt == 6


def test_write_docx_creates_parent_directories(
    tmp_path: Path, full_document: PatentDocument
) -> None:
    target = tmp_path / "nested" / "out.docx"
    assert write_docx(full_document, target) == target
    assert target.stat().st_size > 0


def test_blank_render_options_leave_labels_clean() -> None:
    document = PatentDocument(
        publication_number="US1A",
        title="A Title",
        claims=(Claim(number=1, text="A method."),),
        background=(Paragraph(number=1, text="Some background."),),
    )
    with zipfile.ZipFile(BytesIO(render_docx(document))) as archive:
        header_name = next(n for n in archive.namelist() if n.startswith("word/header"))
        header = archive.read(header_name).decode()
    assert "ATTORNEY DOCKET NO." in header
