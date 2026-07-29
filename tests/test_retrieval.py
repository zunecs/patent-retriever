"""Tests for the retrieval service.

Every source here is a stub. The service's job is orchestration, so the tests
assert on which sources were called and in what order - never on real HTTP.
"""

from __future__ import annotations

import pytest

from patent_retriever.domain.exceptions import (
    InvalidPatentNumberError,
    PatentNotFoundError,
    SourceUnavailableError,
)
from patent_retriever.domain.models import Claim, Paragraph, PatentDocument
from patent_retriever.services.retrieval import (
    PatentRetrievalService,
    find_missing_fields,
)

NUMBER = "US20250097171A1"


def make_document(*, complete: bool = True, number: str = NUMBER) -> PatentDocument:
    return PatentDocument(
        publication_number=number,
        title="A Title",
        claims=(Claim(number=1, text="A method."),),
        inventors=("Jane Doe",) if complete else (),
        abstract="An abstract." if complete else None,
        detailed_description=((Paragraph(number=1, text="Detail."),) if complete else ()),
    )


class StubSource:
    """Returns a document, or raises, and records that it was called."""

    def __init__(
        self,
        name: str,
        document: PatentDocument | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._document = document
        self._error = error
        self.calls: list[str] = []

    def fetch(self, number: str) -> PatentDocument:
        self.calls.append(number)
        if self._error is not None:
            raise self._error
        assert self._document is not None
        return self._document


def test_service_requires_at_least_one_source() -> None:
    with pytest.raises(ValueError, match="At least one source"):
        PatentRetrievalService([])


def test_first_complete_source_wins_and_later_sources_are_not_called() -> None:
    first = StubSource("first", make_document())
    second = StubSource("second", make_document())
    result = PatentRetrievalService([first, second]).retrieve(NUMBER)

    assert result.source_name == "first"
    assert result.is_complete
    assert second.calls == []


def test_number_is_normalized_before_sources_are_called() -> None:
    source = StubSource("only", make_document())
    PatentRetrievalService([source]).retrieve("  us 2025/0097171 a1 ")
    assert source.calls == [NUMBER]


def test_invalid_number_fails_before_any_source_is_contacted() -> None:
    source = StubSource("only", make_document())
    with pytest.raises(InvalidPatentNumberError):
        PatentRetrievalService([source]).retrieve("not-a-patent")
    assert source.calls == []


def test_failing_source_falls_through_to_the_next() -> None:
    failing = StubSource("failing", error=SourceUnavailableError("timeout"))
    working = StubSource("working", make_document())
    result = PatentRetrievalService([failing, working]).retrieve(NUMBER)

    assert result.source_name == "working"
    assert failing.calls == [NUMBER]


def test_incomplete_document_triggers_fallback() -> None:
    partial = StubSource("partial", make_document(complete=False))
    complete = StubSource("complete", make_document())
    result = PatentRetrievalService([partial, complete]).retrieve(NUMBER)

    assert result.source_name == "complete"
    assert result.is_complete
    assert partial.calls == [NUMBER]


def test_best_incomplete_document_is_returned_when_none_are_complete() -> None:
    worse = StubSource("worse", make_document(complete=False))
    better_document = PatentDocument(
        publication_number=NUMBER,
        title="A Title",
        claims=(Claim(number=1, text="A method."),),
        inventors=("Jane Doe",),
        abstract="An abstract.",
    )
    better = StubSource("better", better_document)
    result = PatentRetrievalService([worse, better]).retrieve(NUMBER)

    assert result.source_name == "better"
    assert not result.is_complete
    assert result.missing_fields == ("detailed_description",)


def test_all_sources_failing_raises_with_every_reason_included() -> None:
    first = StubSource("first", error=SourceUnavailableError("timeout"))
    second = StubSource("second", error=SourceUnavailableError("http 503"))

    with pytest.raises(PatentNotFoundError) as error:
        PatentRetrievalService([first, second]).retrieve(NUMBER)

    message = str(error.value)
    assert "first: timeout" in message
    assert "second: http 503" in message


def test_source_names_are_exposed_in_order() -> None:
    service = PatentRetrievalService(
        [StubSource("a", make_document()), StubSource("b", make_document())]
    )
    assert service.source_names == ("a", "b")


def test_find_missing_fields_lists_absent_content() -> None:
    assert find_missing_fields(make_document()) == ()
    assert set(find_missing_fields(make_document(complete=False))) == {
        "abstract",
        "detailed_description",
        "inventors",
    }
