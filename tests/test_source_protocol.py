"""Verify the PatentSource protocol accepts a conforming implementation."""

from patent_retriever.domain.models import Claim, PatentDocument
from patent_retriever.sources.base import PatentSource


class StubSource:
    """A minimal source. Note it does not inherit from PatentSource."""

    name = "stub"

    def fetch(self, number: str) -> PatentDocument:
        return PatentDocument(
            publication_number=number,
            title="A Title",
            claims=(Claim(number=1, text="A method."),),
        )


def test_conforming_class_satisfies_the_protocol_without_inheriting() -> None:
    assert isinstance(StubSource(), PatentSource)


def test_stub_returns_a_document() -> None:
    source: PatentSource = StubSource()
    assert source.fetch("US20250097171A1").publication_number == "US20250097171A1"
