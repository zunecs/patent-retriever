"""Normalization and validation for patent publication numbers.

Users type patent numbers inconsistently: "us 2025/0097171 a1", "US-20250097171-A1",
"US20250097171A1" are the same document. Sources need one canonical form, so this
is done once at the boundary rather than in every adapter.
"""

from __future__ import annotations

import re

from patent_retriever.domain.exceptions import InvalidPatentNumberError

_SEPARATORS = re.compile(r"[\s\-/,._]")

# Two-letter country code, a serial number, and an optional kind code (A1, B2, ...).
_PATENT_NUMBER = re.compile(r"^(?P<country>[A-Z]{2})(?P<serial>\d+)(?P<kind>[A-Z]\d?)?$")


def normalize(raw: str) -> str:
    """Return the canonical uppercase form of a patent number.

    Raises InvalidPatentNumberError if the input cannot be a patent number. This
    is a user error, not a source failure, so it is deliberately not a SourceError
    and must never trigger the fallback chain.
    """
    candidate = _SEPARATORS.sub("", raw).upper()
    if not candidate:
        raise InvalidPatentNumberError("Patent number is empty.")
    if not _PATENT_NUMBER.match(candidate):
        raise InvalidPatentNumberError(
            f"{raw!r} is not a recognizable patent number. Expected a form like 'US20250097171A1'."
        )
    return candidate


def country_code(number: str) -> str:
    """Return the two-letter country code of an already-normalized number."""
    match = _PATENT_NUMBER.match(number)
    if match is None:
        raise InvalidPatentNumberError(f"{number!r} is not normalized.")
    return match.group("country")
