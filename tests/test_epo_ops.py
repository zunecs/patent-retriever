"""Tests for the EPO OPS source.

Parsing runs against JSON captured from live OPS by `scripts/check_epo.py`, so
the quirks under test are the real ones rather than invented ones. The three
references each carry their own:

* EP3000001 - an ordinary modern document. German, French, English full text in
  that order, wrapped claim lines, and a description that exists in French only.
* EP0000001 - a 1978 document. One reference returns two publications (A1 and
  B1), and its description carries escaped paragraph markers and image
  placeholders.
* US2025097171 - biblio works, full text is refused with CLIENT.InvalidCountryCode.

respx covers the HTTP layer, which owns nothing but error mapping and the token
cache. Nothing here touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from patent_retriever.domain.exceptions import (
    ParseError,
    PatentNotFoundError,
    SourceUnavailableError,
)
from patent_retriever.domain.sections import map_sections
from patent_retriever.sources.base import PatentSource
from patent_retriever.sources.epo_ops import (
    AUTH_URL,
    BASE_URL,
    EpoOpsSource,
    _split_claims,
    kind_code,
    parse_biblio,
    parse_claims,
    parse_description,
    to_epodoc,
)

FIXTURES = Path(__file__).parent / "fixtures"

EP_MODERN = "EP3000001A1"
EP_OLD = "EP0000001A1"
US_NUMBER = "US20250097171A1"


def load(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return payload


def service_url(reference: str, service: str) -> str:
    return f"{BASE_URL}/{reference}/{service}"


@pytest.fixture
def source() -> EpoOpsSource:
    return EpoOpsSource(key="key", secret="secret")


@pytest.fixture
def token_route() -> Any:
    """Mock the OAuth2 endpoint. Callers inspect `.call_count` to test caching."""
    return respx.post(AUTH_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t0ken", "expires_in": 1200})
    )


def mock_epo(reference: str, **bodies: Any) -> None:
    """Mock the three OPS endpoints for one reference."""
    for service, body in bodies.items():
        response = body if isinstance(body, httpx.Response) else httpx.Response(200, json=body)
        respx.get(service_url(reference, service)).mock(return_value=response)


# --------------------------------------------------------------------------
# Reference normalization
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        # The kind code is always dropped.
        ("EP0000001A1", "EP0000001"),
        ("EP3000001B1", "EP3000001"),
        ("WO2024123456A1", "WO2024123456"),
        # US publications also lose the leading zero of the seven-digit serial.
        ("US20250097171A1", "US2025097171"),
        ("US20250097171", "US2025097171"),
        ("US20240000001A1", "US2024000001"),
        # US grants are not publications and keep their number intact.
        ("US11234567B2", "US11234567"),
        ("US11234567", "US11234567"),
    ],
)
def test_to_epodoc(number: str, expected: str) -> None:
    assert to_epodoc(number) == expected


def test_kind_code_is_read_back_off_the_number() -> None:
    assert kind_code("EP0000001A1") == "A1"
    assert kind_code("US11234567B2") == "B2"
    assert kind_code("EP0000001") is None


# --------------------------------------------------------------------------
# Biblio parsing
# --------------------------------------------------------------------------


def test_english_title_is_selected_when_german_comes_first() -> None:
    title, _, _ = parse_biblio(load("epo_EP3000001_biblio.json"), EP_MODERN)
    assert title == "METHOD FOR DEFINING FIBRE TRAJECTORIES ON THE BASIS OF A VECTOR FIELD"


def test_kind_code_picks_between_the_two_publications_of_one_reference() -> None:
    """EP0000001 returns the A1 and the B1, whose English titles differ."""
    payload = load("epo_EP0000001_biblio.json")
    assert parse_biblio(payload, "EP0000001A1")[0] == "Thermal heat pump"
    assert parse_biblio(payload, "EP0000001B1")[0] == "THERMAL HEAT PUMP"


def test_a_single_exchange_document_object_is_handled_like_a_list() -> None:
    """US biblio returns one exchange-document as a bare object, not a list."""
    title, _, _ = parse_biblio(load("epo_US2025097171_biblio.json"), US_NUMBER)
    assert title == "LLM FINE-TUNING FOR CHATBOT"


def test_inventors_are_taken_from_the_epodoc_format_only() -> None:
    """The same person appears once per data format under different spellings."""
    _, inventors, _ = parse_biblio(load("epo_EP0000001_biblio.json"), EP_OLD)
    assert inventors == ("BUSSE CLAUS-ADOLF",)


def test_inventor_country_suffix_is_removed() -> None:
    _, inventors, _ = parse_biblio(load("epo_US2025097171_biblio.json"), US_NUMBER)
    assert inventors[0] == "HU YAZHE"
    assert len(inventors) == 6


def test_abstract_paragraph_marker_is_stripped() -> None:
    _, _, abstract = parse_biblio(load("epo_EP0000001_biblio.json"), EP_OLD)
    assert abstract is not None
    assert abstract.startswith("The invention relates to a thermal heat pump")


def test_a_document_without_an_abstract_reports_none() -> None:
    _, _, abstract = parse_biblio(load("epo_EP3000001_biblio.json"), EP_MODERN)
    assert abstract is None


def test_missing_exchange_document_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="no exchange-document"):
        parse_biblio({"ops:world-patent-data": {}}, EP_MODERN)


def test_missing_title_raises_parse_error() -> None:
    payload = {
        "ops:world-patent-data": {
            "exchange-documents": {"exchange-document": {"bibliographic-data": {}}}
        }
    }
    with pytest.raises(ParseError, match="no invention title"):
        parse_biblio(payload, EP_MODERN)


# --------------------------------------------------------------------------
# Claims parsing
# --------------------------------------------------------------------------


def test_claims_are_taken_from_the_english_block_not_the_first_one() -> None:
    """EP3000001 serves DE, FR, then EN."""
    claims = parse_claims(load("epo_EP3000001_claims.json"), EP_MODERN)
    assert claims[0].text.startswith("Method for defining the trajectories of fiber")


def test_wrapped_claim_lines_are_joined_rather_than_counted_as_claims() -> None:
    """21 claim-text lines carry 12 claims; the rest are continuations."""
    claims = parse_claims(load("epo_EP3000001_claims.json"), EP_MODERN)
    assert len(claims) == 12
    assert claims[-1].text.startswith("Method for the manufacture of parts")


def test_claims_are_renumbered_from_one() -> None:
    claims = parse_claims(load("epo_EP3000001_claims.json"), EP_MODERN)
    assert [claim.number for claim in claims] == list(range(1, 13))


def test_claim_numbers_are_removed_from_the_text() -> None:
    claims = parse_claims(load("epo_EP3000001_claims.json"), EP_MODERN)
    assert not any(claim.text[:4].strip().rstrip(".").isdigit() for claim in claims)


def test_split_claims_starts_a_new_claim_only_on_a_numbered_line() -> None:
    lines = ["1. A method comprising:", "a first step, and", "2. The method of claim 1."]
    assert _split_claims(lines) == [
        "A method comprising: a first step, and",
        "The method of claim 1.",
    ]


def test_split_claims_does_not_mistake_a_decimal_for_a_claim_number() -> None:
    """A continuation line opening with "10.5 cm" must not start claim 10."""
    assert _split_claims(["1. A method.", "10.5 cm wide."]) == ["A method. 10.5 cm wide."]


def test_missing_claims_block_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="no claims"):
        parse_claims({"ops:world-patent-data": {}}, EP_MODERN)


def test_empty_claims_block_raises_parse_error() -> None:
    payload = {
        "ops:world-patent-data": {
            "ftxt:fulltext-documents": {
                "ftxt:fulltext-document": {
                    "claims": {"@lang": "EN", "claim": {"claim-text": {"$": "   "}}}
                }
            }
        }
    }
    with pytest.raises(ParseError, match="no text"):
        parse_claims(payload, EP_MODERN)


# --------------------------------------------------------------------------
# Description parsing
# --------------------------------------------------------------------------


def test_description_paragraph_markers_are_stripped() -> None:
    sections = parse_description(load("epo_EP0000001_description.json"), EP_OLD)
    paragraphs = [text for section in sections for text in section.paragraphs]
    assert paragraphs[0].startswith("In order to raise heat")
    assert not any(text.startswith("[00") for text in paragraphs)


def test_escaped_markers_and_image_placeholders_leave_no_empty_paragraphs() -> None:
    """Two paragraphs hold only "&#91;0003&#93;" and a bare <img/> respectively."""
    sections = parse_description(load("epo_EP0000001_description.json"), EP_OLD)
    paragraphs = [text for section in sections for text in section.paragraphs]
    assert len(paragraphs) == 35  # 37 in the response, two of which carry no text
    assert not any("<img" in text for text in paragraphs)
    assert all(text.strip() for text in paragraphs)


def test_subscript_markup_is_left_alone() -> None:
    """Subscripts like "T <2>" are literal text here, not tags to strip."""
    sections = parse_description(load("epo_EP0000001_description.json"), EP_OLD)
    body = " ".join(text for section in sections for text in section.paragraphs)
    assert "Q <2>" in body


def test_description_falls_back_to_another_language_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """EP3000001 has English claims but a French-only description."""
    with caplog.at_level("WARNING"):
        sections = parse_description(load("epo_EP3000001_description.json"), EP_MODERN)
    assert sections
    assert "no English description; using FR" in caplog.text


def test_missing_description_returns_no_sections() -> None:
    assert parse_description({"ops:world-patent-data": {}}, EP_MODERN) == []


def test_an_unheaded_description_is_labelled_detailed_description() -> None:
    """OPS carries no heading markup, so an unlabelled body is not BACKGROUND.

    The mapper's default is right for Google Patents, where text before the first
    heading really is background material. It is wrong here, and which of the two
    applies is a fact about the source.
    """
    for fixture, number in (
        ("epo_EP0000001_description.json", EP_OLD),
        ("epo_EP3000001_description.json", EP_MODERN),
    ):
        sections = parse_description(load(fixture), number)
        assert [section.heading for section in sections] == ["DETAILED DESCRIPTION"]


def test_unheaded_description_reaches_the_detailed_description_section() -> None:
    sections = parse_description(load("epo_EP0000001_description.json"), EP_OLD)
    background, summary, drawings, detailed = map_sections(sections).to_paragraphs()
    assert not background and not summary and not drawings
    assert len(detailed) == 35
    assert [paragraph.number for paragraph in detailed] == list(range(1, 36))


def test_recognized_headings_are_kept_rather_than_relabelled() -> None:
    """The relabelling only fires when nothing at all was recognized."""
    payload = {
        "ops:world-patent-data": {
            "ftxt:fulltext-documents": {
                "ftxt:fulltext-document": {
                    "description": {
                        "@lang": "EN",
                        "p": [
                            {"$": "Opening material."},
                            {"$": "BACKGROUND OF THE INVENTION"},
                            {"$": "Prior art is inadequate."},
                            {"$": "BRIEF DESCRIPTION OF THE DRAWINGS"},
                            {"$": "FIG. 1 shows an apparatus."},
                        ],
                    }
                }
            }
        }
    }
    sections = parse_description(payload, EP_MODERN)
    assert [section.heading for section in sections] == [
        None,
        "BACKGROUND OF THE INVENTION",
        "BRIEF DESCRIPTION OF THE DRAWINGS",
    ]


# --------------------------------------------------------------------------
# HTTP layer: token handling
# --------------------------------------------------------------------------


def test_credentials_are_required() -> None:
    with pytest.raises(ValueError, match="key and a secret"):
        EpoOpsSource(key="", secret="secret")


@respx.mock
def test_source_satisfies_the_protocol(source: EpoOpsSource) -> None:
    assert isinstance(source, PatentSource)


@respx.mock
def test_one_token_is_shared_by_all_three_endpoints(source: EpoOpsSource, token_route: Any) -> None:
    mock_epo(
        "EP3000001",
        biblio=load("epo_EP3000001_biblio.json"),
        claims=load("epo_EP3000001_claims.json"),
        description=load("epo_EP3000001_description.json"),
    )
    source.fetch(EP_MODERN)
    assert token_route.call_count == 1


@respx.mock
def test_an_expired_token_is_refetched(source: EpoOpsSource) -> None:
    """expires_in below the safety margin means the token is stale on arrival."""
    route = respx.post(AUTH_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t0ken", "expires_in": 0})
    )
    mock_epo(
        "EP3000001",
        biblio=load("epo_EP3000001_biblio.json"),
        claims=load("epo_EP3000001_claims.json"),
        description=load("epo_EP3000001_description.json"),
    )
    source.fetch(EP_MODERN)
    assert route.call_count == 3


@respx.mock
def test_failed_authentication_raises_source_unavailable(source: EpoOpsSource) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(SourceUnavailableError, match="HTTP 401"):
        source.fetch(EP_MODERN)


@respx.mock
def test_authentication_without_a_token_raises_source_unavailable(source: EpoOpsSource) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"scope": "ops"}))
    with pytest.raises(SourceUnavailableError, match="no access token"):
        source.fetch(EP_MODERN)


@respx.mock
def test_unreachable_auth_endpoint_raises_source_unavailable(source: EpoOpsSource) -> None:
    respx.post(AUTH_URL).mock(side_effect=httpx.ConnectError("no route to host"))
    with pytest.raises(SourceUnavailableError, match="authentication failed"):
        source.fetch(EP_MODERN)


# --------------------------------------------------------------------------
# HTTP layer: error mapping
# --------------------------------------------------------------------------


@respx.mock
def test_fetch_returns_a_document(source: EpoOpsSource, token_route: Any) -> None:
    mock_epo(
        "EP3000001",
        biblio=load("epo_EP3000001_biblio.json"),
        claims=load("epo_EP3000001_claims.json"),
        description=load("epo_EP3000001_description.json"),
    )
    document = source.fetch(EP_MODERN)
    assert document.publication_number == EP_MODERN
    assert document.title.startswith("METHOD FOR DEFINING FIBRE TRAJECTORIES")
    assert len(document.claims) == 12
    assert document.detailed_description


@respx.mock
def test_us_full_text_is_refused_and_names_the_reason(
    source: EpoOpsSource, token_route: Any
) -> None:
    """The fallback chain exists for exactly this: biblio works, full text does not."""
    fault = (FIXTURES / "epo_US2025097171_claims_fault.xml").read_text(encoding="utf-8")
    mock_epo(
        "US2025097171",
        biblio=load("epo_US2025097171_biblio.json"),
        claims=httpx.Response(404, text=fault, headers={"Content-Type": "application/xml"}),
    )
    with pytest.raises(PatentNotFoundError, match="EP and WO documents only"):
        source.fetch(US_NUMBER)


@respx.mock
def test_unknown_reference_raises_patent_not_found(source: EpoOpsSource, token_route: Any) -> None:
    mock_epo("EP3000001", biblio=httpx.Response(404, text="<fault>SERVER.EntityNotFound</fault>"))
    with pytest.raises(PatentNotFoundError, match="has no biblio"):
        source.fetch(EP_MODERN)


@pytest.mark.parametrize("status", [403, 429])
@respx.mock
def test_quota_and_access_denial_raise_source_unavailable(
    source: EpoOpsSource, token_route: Any, status: int
) -> None:
    mock_epo("EP3000001", biblio=httpx.Response(status))
    with pytest.raises(SourceUnavailableError, match="quota or access denied"):
        source.fetch(EP_MODERN)


@pytest.mark.parametrize("status", [500, 502, 503])
@respx.mock
def test_server_errors_raise_source_unavailable(
    source: EpoOpsSource, token_route: Any, status: int
) -> None:
    mock_epo("EP3000001", biblio=httpx.Response(status))
    with pytest.raises(SourceUnavailableError, match=f"HTTP {status}"):
        source.fetch(EP_MODERN)


@respx.mock
def test_network_failure_raises_source_unavailable(source: EpoOpsSource, token_route: Any) -> None:
    respx.get(service_url("EP3000001", "biblio")).mock(
        side_effect=httpx.ConnectError("no route to host")
    )
    with pytest.raises(SourceUnavailableError, match="failed"):
        source.fetch(EP_MODERN)


@respx.mock
def test_unparseable_body_raises_parse_error(source: EpoOpsSource, token_route: Any) -> None:
    mock_epo(
        "EP3000001",
        biblio=httpx.Response(
            200, text="<html>maintenance</html>", headers={"Content-Type": "application/json"}
        ),
    )
    with pytest.raises(ParseError, match="invalid JSON"):
        source.fetch(EP_MODERN)
