"""The contract every patent source must satisfy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from patent_retriever.domain.models import PatentDocument


@runtime_checkable
class PatentSource(Protocol):
    """A source of patent documents.

    Implementations must not know about other sources, about output formats, or
    about the fallback chain. Their only job is: given a normalized patent number,
    return a PatentDocument or raise a SourceError.
    """

    @property
    def name(self) -> str:
        """Short identifier used in logs and in the configured source order."""
        ...

    def fetch(self, number: str) -> PatentDocument:
        """Retrieve a patent.

        Args:
            number: an already-normalized publication number.

        Raises:
            PatentNotFoundError: the source has no record of this patent.
            SourceUnavailableError: the source could not be reached.
            ParseError: the response could not be interpreted.
        """
        ...
