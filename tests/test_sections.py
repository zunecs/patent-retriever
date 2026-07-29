"""Tests for section mapping."""

import pytest

from patent_retriever.domain.sections import (
    Section,
    SourceSection,
    classify,
    map_sections,
    normalize_heading,
)


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("BACKGROUND", Section.BACKGROUND),
        ("Background of the Invention", Section.BACKGROUND),
        ("TECHNICAL FIELD", Section.BACKGROUND),
        ("FIELD OF THE INVENTION", Section.BACKGROUND),
        ("DESCRIPTION OF RELATED ART", Section.BACKGROUND),
        ("CROSS-REFERENCE TO RELATED APPLICATIONS", Section.BACKGROUND),
        ("SUMMARY", Section.SUMMARY),
        ("BRIEF SUMMARY OF THE INVENTION", Section.SUMMARY),
        ("DISCLOSURE OF THE INVENTION", Section.SUMMARY),
        ("BRIEF DESCRIPTION OF THE DRAWINGS", Section.DRAWINGS),
        ("DESCRIPTION OF THE FIGURES", Section.DRAWINGS),
        ("DETAILED DESCRIPTION", Section.DETAILED),
        ("DETAILED DESCRIPTION OF THE PREFERRED EMBODIMENTS", Section.DETAILED),
        ("MODES FOR CARRYING OUT THE INVENTION", Section.DETAILED),
        ("BEST MODE FOR CARRYING OUT THE INVENTION", Section.DETAILED),
    ],
)
def test_real_world_headings_classify_correctly(heading: str, expected: Section) -> None:
    assert classify(heading) == expected


def test_detailed_wins_over_drawings_when_both_words_appear() -> None:
    assert classify("DETAILED DESCRIPTION OF THE DRAWINGS") == Section.DETAILED


@pytest.mark.parametrize("heading", [None, "", "   ", "EXAMPLES", "ADVANTAGEOUS EFFECTS"])
def test_unrecognized_headings_return_none(heading: str | None) -> None:
    assert classify(heading) is None


def test_normalize_heading_strips_punctuation_and_case() -> None:
    assert normalize_heading("  Brief   Description of the Drawings.  ") == (
        "BRIEF DESCRIPTION OF THE DRAWINGS"
    )


def test_sections_are_grouped_by_canonical_heading() -> None:
    result = map_sections(
        [
            SourceSection("TECHNICAL FIELD", ("Field text.",)),
            SourceSection("BRIEF SUMMARY", ("Summary text.",)),
            SourceSection("BRIEF DESCRIPTION OF THE DRAWINGS", ("FIG. 1 shows.",)),
            SourceSection("DETAILED DESCRIPTION", ("Detail text.",)),
        ]
    )
    assert result.background == ["Field text."]
    assert result.summary == ["Summary text."]
    assert result.drawings == ["FIG. 1 shows."]
    assert result.detailed == ["Detail text."]


def test_multiple_sections_map_to_the_same_bucket() -> None:
    result = map_sections(
        [
            SourceSection("TECHNICAL FIELD", ("Field text.",)),
            SourceSection("BACKGROUND ART", ("Background text.",)),
        ]
    )
    assert result.background == ["Field text.", "Background text."]


def test_content_before_any_heading_goes_to_background() -> None:
    result = map_sections([SourceSection(None, ("Opening text.",))])
    assert result.background == ["Opening text."]


def test_unrecognized_heading_continues_the_current_section() -> None:
    result = map_sections(
        [
            SourceSection("DETAILED DESCRIPTION", ("First.",)),
            SourceSection("EXAMPLE 1", ("Second.",)),
        ]
    )
    assert result.detailed == ["First.", "Second."]
    assert result.background == []


def test_empty_sections_are_skipped() -> None:
    result = map_sections(
        [
            SourceSection("SUMMARY", ()),
            SourceSection("DETAILED DESCRIPTION", ("Detail.",)),
        ]
    )
    assert result.summary == []
    assert result.detailed == ["Detail."]


def test_to_paragraphs_numbers_continuously_across_sections() -> None:
    result = map_sections(
        [
            SourceSection("BACKGROUND", ("A.", "B.")),
            SourceSection("SUMMARY", ("C.",)),
            SourceSection("DETAILED DESCRIPTION", ("D.", "E.")),
        ]
    )
    background, summary, drawings, detailed = result.to_paragraphs()

    assert [p.number for p in background] == [1, 2]
    assert [p.number for p in summary] == [3]
    assert drawings == ()
    assert [p.number for p in detailed] == [4, 5]
    assert detailed[0].text == "D."
