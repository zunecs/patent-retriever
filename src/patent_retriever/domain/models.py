"""Core domain model.

This module has no I/O and no third-party dependencies. It defines what a
patent is as far as this application is concerned - independent of which
source the data came from and which format it will be rendered into.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import pairwise

from patent_retriever.domain.exceptions import InvalidPatentDocumentError


@dataclass(frozen=True, slots=True)
class Paragraph:
    """A numbered paragraph in the body of a patent.

    `number` is the plain integer value. Presentation - the four-digit
    zero-padded bracket form used in the output document - is the renderer's
    responsibility, not the model's.
    """

    number: int
    text: str

    def __post_init__(self) -> None:
        if self.number < 1:
            raise InvalidPatentDocumentError(
                f"Paragraph number must be 1 or greater, got {self.number}."
            )
        if not self.text.strip():
            raise InvalidPatentDocumentError(f"Paragraph {self.number} has no text.")


@dataclass(frozen=True, slots=True)
class Claim:
    """A single patent claim."""

    number: int
    text: str

    def __post_init__(self) -> None:
        if self.number < 1:
            raise InvalidPatentDocumentError(
                f"Claim number must be 1 or greater, got {self.number}."
            )
        if not self.text.strip():
            raise InvalidPatentDocumentError(f"Claim {self.number} has no text.")


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Values supplied per rendering job rather than by the patent source.

    These appear in the output document header but are not properties of the
    patent itself, so they deliberately do not live on PatentDocument.
    """

    attorney_docket_number: str = ""
    client_reference: str = ""


@dataclass(frozen=True, slots=True)
class PatentDocument:
    """A patent, normalized into the shape this application works with.

    Collections are tuples rather than lists so the object is deeply immutable:
    a frozen dataclass holding a list would still allow `doc.claims.append(...)`.
    Tuples also make the empty default `()` safe, with no mutable-default trap.
    """

    publication_number: str
    title: str
    claims: tuple[Claim, ...]
    inventors: tuple[str, ...] = ()
    abstract: str | None = None
    abstract_figure_reference: str | None = None
    background: tuple[Paragraph, ...] = ()
    summary: tuple[Paragraph, ...] = ()
    brief_description_of_drawings: tuple[Paragraph, ...] = ()
    detailed_description: tuple[Paragraph, ...] = ()

    def __post_init__(self) -> None:
        if not self.publication_number.strip():
            raise InvalidPatentDocumentError("publication_number is required.")
        if not self.title.strip():
            raise InvalidPatentDocumentError("title is required.")
        if not self.claims:
            raise InvalidPatentDocumentError(
                f"{self.publication_number}: at least one claim is required."
            )
        self._validate_ascending([claim.number for claim in self.claims], "Claim numbers")
        self._validate_ascending(
            [para.number for _, paras in self.body_sections() for para in paras],
            "Body paragraph numbers",
        )

    @staticmethod
    def _validate_ascending(numbers: list[int], label: str) -> None:
        """Require strictly increasing order - but permit gaps.

        Gaps are tolerated because sources legitimately produce them (amended
        applications with cancelled claims, for example). Making the numbering
        continuous is a rendering concern, handled by `renumbered()`.
        """
        if any(current >= following for current, following in pairwise(numbers)):
            raise InvalidPatentDocumentError(
                f"{label} must strictly increase in document order, got {numbers}."
            )

    def body_sections(self) -> tuple[tuple[str, tuple[Paragraph, ...]], ...]:
        """Return the four body sections with their headings, in document order.

        The headings are the exact strings required by the output format.
        """
        return (
            ("BACKGROUND", self.background),
            ("SUMMARY", self.summary),
            ("BRIEF DESCRIPTION OF DRAWINGS", self.brief_description_of_drawings),
            ("DETAILED DESCRIPTION", self.detailed_description),
        )

    def renumbered(self) -> PatentDocument:
        """Return a copy whose body paragraphs are numbered 1..N continuously.

        The output format requires an unbroken sequence running across all four
        body sections. Sources rarely provide one, so normalize before rendering.
        """
        next_number = 1

        def sequence(paragraphs: tuple[Paragraph, ...]) -> tuple[Paragraph, ...]:
            nonlocal next_number
            result = []
            for paragraph in paragraphs:
                result.append(Paragraph(number=next_number, text=paragraph.text))
                next_number += 1
            return tuple(result)

        background = sequence(self.background)
        summary = sequence(self.summary)
        drawings = sequence(self.brief_description_of_drawings)
        detailed = sequence(self.detailed_description)

        return replace(
            self,
            background=background,
            summary=summary,
            brief_description_of_drawings=drawings,
            detailed_description=detailed,
        )
