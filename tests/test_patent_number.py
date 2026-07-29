"""Tests for patent number normalization."""

import pytest

from patent_retriever.domain.exceptions import InvalidPatentNumberError
from patent_retriever.domain.patent_number import country_code, normalize


@pytest.mark.parametrize(
    "raw",
    [
        "US20250097171A1",
        "us20250097171a1",
        "  US 2025/0097171 A1  ",
        "US-20250097171-A1",
        "US.20250097171.A1",
    ],
)
def test_equivalent_inputs_normalize_identically(raw: str) -> None:
    assert normalize(raw) == "US20250097171A1"


@pytest.mark.parametrize("raw", ["EP1000000B1", "WO2020123456A1", "JP2020123456A"])
def test_other_jurisdictions_are_accepted(raw: str) -> None:
    assert normalize(raw) == raw


def test_number_without_kind_code_is_accepted() -> None:
    assert normalize("US20250097171") == "US20250097171"


@pytest.mark.parametrize("raw", ["", "   ", "12345", "USA20250097171A1", "US", "hello"])
def test_malformed_input_is_rejected(raw: str) -> None:
    with pytest.raises(InvalidPatentNumberError):
        normalize(raw)


def test_country_code_extraction() -> None:
    assert country_code("US20250097171A1") == "US"
    assert country_code("EP1000000B1") == "EP"


def test_country_code_rejects_unnormalized_input() -> None:
    with pytest.raises(InvalidPatentNumberError):
        country_code("us-2025/0097171")
