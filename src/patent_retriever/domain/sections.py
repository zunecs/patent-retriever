"""Map arbitrary patent section headings onto the four canonical output sections.

The output format requires exactly BACKGROUND, SUMMARY, BRIEF DESCRIPTION OF
DRAWINGS, and DETAILED DESCRIPTION. Real patents use many variants, so sources
hand this module whatever headings they found and receive canonical sections back.

This is pure logic with no I/O, which is deliberate: it is the most failure-prone
part of the pipeline, so it must be testable against real headings without any
network access.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from patent_retriever.domain.models import Paragraph

_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9 ]")
_WHITESPACE = re.compile(r"\s+")


class Section(Enum):
    """The four canonical body sections, in output order."""

    BACKGROUND = "BACKGROUND"
    SUMMARY = "SUMMARY"
    DRAWINGS = "BRIEF DESCRIPTION OF DRAWINGS"
    DETAILED = "DETAILED DESCRIPTION"


# Order matters. "DETAILED DESCRIPTION OF THE DRAWINGS" must resolve to DETAILED,
# so the DETAILED rule is evaluated before the DRAWINGS rule.
_RULES: tuple[tuple[Section, tuple[str, ...]], ...] = (
    (Section.DETAILED, ("DETAILED", "EMBODIMENT", "BEST MODE", "MODES FOR CARRYING")),
    (Section.DRAWINGS, ("DRAWING", "FIGURE")),
    (Section.SUMMARY, ("SUMMARY", "DISCLOSURE OF THE INVENTION", "SOLUTION TO PROBLEM")),
    (
        Section.BACKGROUND,
        (
            "BACKGROUND",
            "FIELD",
            "RELATED ART",
            "PRIOR ART",
            "CROSS REFERENCE",
            "CROSSREFERENCE",
            "TECHNICAL PROBLEM",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class SourceSection:
    """A section as a source found it, before normalization.

    `heading` is None for content that appeared before any heading.
    """

    heading: str | None
    paragraphs: tuple[str, ...]


@dataclass(slots=True)
class MappedSections:
    """Paragraph text grouped into the four canonical sections."""

    background: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    drawings: list[str] = field(default_factory=list)
    detailed: list[str] = field(default_factory=list)

    def extend(self, section: Section, paragraphs: Sequence[str]) -> None:
        bucket = {
            Section.BACKGROUND: self.background,
            Section.SUMMARY: self.summary,
            Section.DRAWINGS: self.drawings,
            Section.DETAILED: self.detailed,
        }[section]
        bucket.extend(paragraphs)

    def to_paragraphs(
        self,
    ) -> tuple[
        tuple[Paragraph, ...],
        tuple[Paragraph, ...],
        tuple[Paragraph, ...],
        tuple[Paragraph, ...],
    ]:
        """Return the four sections as Paragraph tuples, numbered 1..N continuously.

        Numbering runs across all four sections, matching the output format.
        """
        counter = 1

        def build(texts: list[str]) -> tuple[Paragraph, ...]:
            nonlocal counter
            result = []
            for text in texts:
                result.append(Paragraph(number=counter, text=text))
                counter += 1
            return tuple(result)

        return (
            build(self.background),
            build(self.summary),
            build(self.drawings),
            build(self.detailed),
        )


def normalize_heading(heading: str) -> str:
    """Reduce a heading to uppercase letters, digits, and single spaces."""
    upper = heading.upper()
    stripped = _NON_ALPHANUMERIC.sub(" ", upper)
    return _WHITESPACE.sub(" ", stripped).strip()


def classify(heading: str | None) -> Section | None:
    """Return the canonical section for a heading, or None if unrecognized."""
    if heading is None:
        return None
    normalized = normalize_heading(heading)
    if not normalized:
        return None
    for section, keywords in _RULES:
        if any(keyword in normalized for keyword in keywords):
            return section
    return None


def map_sections(sections: Sequence[SourceSection]) -> MappedSections:
    """Group source sections into the four canonical buckets.

    Unrecognized headings fall through to the section currently being filled,
    which keeps their content in document order rather than discarding it. Content
    appearing before any recognized heading goes to BACKGROUND, since that is what
    a patent's opening material almost always is.
    """
    mapped = MappedSections()
    current = Section.BACKGROUND

    for source_section in sections:
        if not source_section.paragraphs:
            continue
        matched = classify(source_section.heading)
        if matched is not None:
            current = matched
        mapped.extend(current, source_section.paragraphs)

    return mapped
