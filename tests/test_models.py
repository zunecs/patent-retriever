"""Tests for the domain model."""

import dataclasses

import pytest

from patent_retriever.domain.exceptions import InvalidPatentDocumentError
from patent_retriever.domain.models import Claim, Paragraph, PatentDocument


def test_minimal_document_is_valid(minimal_document: PatentDocument) -> None:
    assert minimal_document.publication_number == "US20250097171A1"
    assert len(minimal_document.claims) == 1
    assert minimal_document.background == ()


def test_document_is_immutable(minimal_document: PatentDocument) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        minimal_document.title = "Something else"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [("publication_number", "   "), ("title", "")],
)
def test_required_string_fields_reject_blanks(field: str, value: str) -> None:
    kwargs = {
        "publication_number": "US1A",
        "title": "A Title",
        "claims": (Claim(number=1, text="A method."),),
        field: value,
    }
    with pytest.raises(InvalidPatentDocumentError):
        PatentDocument(**kwargs)  # type: ignore[arg-type]


def test_document_requires_at_least_one_claim() -> None:
    with pytest.raises(InvalidPatentDocumentError, match="at least one claim"):
        PatentDocument(
            publication_number="US1A",
            title="A Title",
            claims=(),
        )


def test_claim_numbers_must_ascend() -> None:
    with pytest.raises(InvalidPatentDocumentError, match="Claim numbers"):
        PatentDocument(
            publication_number="US1A",
            title="A Title",
            claims=(
                Claim(number=2, text="Second."),
                Claim(number=1, text="First."),
            ),
        )


def test_body_paragraph_numbers_must_ascend_across_sections() -> None:
    with pytest.raises(InvalidPatentDocumentError, match="Body paragraph numbers"):
        PatentDocument(
            publication_number="US1A",
            title="A Title",
            claims=(Claim(number=1, text="A method."),),
            background=(Paragraph(number=5, text="Later."),),
            summary=(Paragraph(number=2, text="Earlier."),),
        )


def test_gaps_in_numbering_are_allowed(full_document: PatentDocument) -> None:
    numbers = [p.number for _, paras in full_document.body_sections() for p in paras]
    assert numbers == [1, 5, 9, 12, 13]


def test_paragraph_rejects_blank_text() -> None:
    with pytest.raises(InvalidPatentDocumentError, match="no text"):
        Paragraph(number=1, text="   ")


def test_paragraph_rejects_zero_number() -> None:
    with pytest.raises(InvalidPatentDocumentError, match="1 or greater"):
        Paragraph(number=0, text="Some text.")


def test_renumbered_produces_a_continuous_sequence(full_document: PatentDocument) -> None:
    result = full_document.renumbered()
    numbers = [p.number for _, paras in result.body_sections() for p in paras]
    assert numbers == [1, 2, 3, 4, 5]


def test_renumbered_preserves_text_and_leaves_original_untouched(
    full_document: PatentDocument,
) -> None:
    result = full_document.renumbered()
    assert result.detailed_description[0].text == full_document.detailed_description[0].text
    assert full_document.summary[0].number == 5
    assert result.summary[0].number == 2


def test_body_sections_uses_exact_output_headings(minimal_document: PatentDocument) -> None:
    headings = [heading for heading, _ in minimal_document.body_sections()]
    assert headings == [
        "BACKGROUND",
        "SUMMARY",
        "BRIEF DESCRIPTION OF DRAWINGS",
        "DETAILED DESCRIPTION",
    ]
