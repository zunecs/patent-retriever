"""Orchestrates retrieval across multiple patent sources.

This is the only component that knows more than one source exists. Sources are
injected rather than imported, so adding a new source never requires editing this
file - the caller simply passes a longer list.

Completeness is a policy decision and therefore lives here, not in the sources.
A source's job is to report what it found; deciding whether that is good enough
is the service's job.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from patent_retriever.domain.exceptions import PatentNotFoundError, SourceError
from patent_retriever.domain.models import PatentDocument
from patent_retriever.domain.patent_number import normalize
from patent_retriever.sources.base import PatentSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """A retrieved document plus the provenance the interfaces need to report.

    `source_name` is recorded for logging and display only. No downstream code
    should branch on it - doing so would recouple the application to its sources.
    """

    document: PatentDocument
    source_name: str
    is_complete: bool
    missing_fields: tuple[str, ...]


def find_missing_fields(document: PatentDocument) -> tuple[str, ...]:
    """Return the names of fields the output document really wants but lacks.

    Claims and title are absent from this list because the model already refuses
    to exist without them.
    """
    missing: list[str] = []
    if not document.abstract:
        missing.append("abstract")
    if not document.detailed_description:
        missing.append("detailed_description")
    if not document.inventors:
        missing.append("inventors")
    return tuple(missing)


class PatentRetrievalService:
    """Tries each source in order until one yields a complete document."""

    def __init__(self, sources: Sequence[PatentSource]) -> None:
        if not sources:
            raise ValueError("At least one source is required.")
        self._sources = tuple(sources)

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(source.name for source in self._sources)

    def retrieve(self, raw_number: str) -> RetrievalResult:
        """Retrieve a patent, falling back through the configured sources.

        An incomplete document is kept as a candidate while later sources are
        tried. If none returns a complete document, the best candidate found is
        returned rather than discarded - a partial document is more useful to the
        user than an error, and the caller is told what is missing.

        Raises:
            InvalidPatentNumberError: the input is not a patent number. Raised
                before any source is contacted, since retrying cannot help.
            PatentNotFoundError: every source failed.
        """
        number = normalize(raw_number)
        best: RetrievalResult | None = None
        failures: list[str] = []

        for source in self._sources:
            logger.info("Trying %s for %s", source.name, number)
            try:
                document = source.fetch(number)
            except SourceError as error:
                logger.warning("%s failed for %s: %s", source.name, number, error)
                failures.append(f"{source.name}: {error}")
                continue

            missing = find_missing_fields(document)
            result = RetrievalResult(
                document=document,
                source_name=source.name,
                is_complete=not missing,
                missing_fields=missing,
            )

            if result.is_complete:
                logger.info("%s returned a complete document for %s", source.name, number)
                return result

            logger.info(
                "%s returned an incomplete document for %s (missing: %s)",
                source.name,
                number,
                ", ".join(missing),
            )
            if best is None or len(missing) < len(best.missing_fields):
                best = result

        if best is not None:
            logger.info(
                "Returning best available document for %s from %s", number, best.source_name
            )
            return best

        raise PatentNotFoundError(
            f"{number} could not be retrieved from any source. " + "; ".join(failures)
        )
