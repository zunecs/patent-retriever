"""Tests for the Google Patents source.

Parsing tests use a saved fixture so they never touch the network. Only the
error-mapping tests use respx, because that is the only behavior the HTTP layer
actually owns.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from patent_retriever.domain.exceptions import (
    ParseError,
    PatentNotFoundError,
    SourceUnavailableError,
)
from patent_retriever.domain.models import PatentDocument
from patent_retriever.sources.base import PatentSource
from patent_retriever.sources.google_patents import GooglePatentsSource, parse_html

FIXTURE = Path(__file__).parent / "fixtures" / "US20250097171A1.html"
NUMBER = "US20250097171A1"
URL = f"https://patents.google.com/patent/{NUMBER}/en"


@pytest.fixture(scope="module")
def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(fixture_html: str) -> PatentDocument:
    return parse_html(fixture_html, NUMBER)


def test_source_satisfies_the_protocol() -> None:
    assert isinstance(GooglePatentsSource(), PatentSource)


def test_publication_number_has_colons_removed(parsed: PatentDocument) -> None:
    assert parsed.publication_number == "US20250097171A1"


def test_title_is_extracted_and_stripped(parsed: PatentDocument) -> None:
    assert parsed.title == "Llm fine-tuning for chatbot"


def test_inventors_are_extracted_without_the_assignee(parsed: PatentDocument) -> None:
    assert parsed.inventors[0] == "Yazhe Hu"
    assert len(parsed.inventors) == 6
    assert "Oracle International Corp" not in parsed.inventors


def test_abstract_is_extracted(parsed: PatentDocument) -> None:
    assert parsed.abstract is not None
    assert "fine-tuning" in parsed.abstract.lower()


def test_claims_are_renumbered_from_one(parsed: PatentDocument) -> None:
    assert parsed.claims[0].number == 1
    assert [c.number for c in parsed.claims] == list(range(1, len(parsed.claims) + 1))


def test_claim_text_has_googles_number_prefix_removed(parsed: PatentDocument) -> None:
    assert parsed.claims[0].text.startswith("One or more non-transitory")


def test_body_paragraphs_are_numbered_continuously(parsed: PatentDocument) -> None:
    numbers = [p.number for _, paras in parsed.body_sections() for p in paras]
    assert numbers == list(range(1, len(numbers) + 1))


def test_sections_are_populated(parsed: PatentDocument) -> None:
    assert parsed.background, "expected CROSS REFERENCE and BACKGROUND content"
    assert parsed.brief_description_of_drawings, "expected drawings content"
    assert parsed.detailed_description, "expected detailed description content"


def test_drawings_section_contains_figure_references(parsed: PatentDocument) -> None:
    text = " ".join(p.text for p in parsed.brief_description_of_drawings)
    assert "FIG. 1" in text


def test_missing_title_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="no title"):
        parse_html("<html><body></body></html>", NUMBER)


def test_missing_claims_raises_parse_error() -> None:
    html = '<html><head><meta name="DC.title" content="A Title"></head><body></body></html>'
    with pytest.raises(ParseError, match="no claims"):
        parse_html(html, NUMBER)


@respx.mock
def test_fetch_returns_a_document(fixture_html: str) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text=fixture_html))
    document = GooglePatentsSource().fetch(NUMBER)
    assert document.publication_number == NUMBER


@respx.mock
def test_404_raises_patent_not_found() -> None:
    respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(PatentNotFoundError):
        GooglePatentsSource().fetch(NUMBER)


@respx.mock
def test_server_error_raises_source_unavailable() -> None:
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(SourceUnavailableError, match="503"):
        GooglePatentsSource().fetch(NUMBER)


@respx.mock
def test_network_failure_raises_source_unavailable() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("no route to host"))
    with pytest.raises(SourceUnavailableError):
        GooglePatentsSource().fetch(NUMBER)
