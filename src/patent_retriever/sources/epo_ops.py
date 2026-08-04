"""EPO Open Patent Services source.

OPS is an official authenticated REST API, so it is more reliable than scraping.
It has one significant limitation: full text (claims and description) is served
for EP and WO documents but not for US ones, which return
CLIENT.InvalidCountryCode. US patents therefore fail here and fall through to the
next source in the chain - exactly what the fallback design exists for.

Quirks measured against live responses, each of which drives code below:

1. Reference format. OPS `epodoc` references omit the kind code and, for US
   publications, drop the leading zero from the serial:
   US20250097171A1 -> US2025097171. Sending the untrimmed number returns
   SERVER.EntityNotFound, which reads as "no such patent" rather than "wrong
   reference format".
2. The JSON is a mechanical translation of XML. Text lives under "$", attributes
   under "@name", and any element may be a single object or a list depending on
   how many siblings it had. EP0000001 returns two exchange-documents (A1 and
   B1) as a list; US2025097171 returns one as a bare object.
3. Full text is returned per language, German first for EP documents, so English
   has to be selected explicitly rather than taken as the first entry.
4. Within a claims block, `claim-text` entries are lines, not claims: a claim
   that wrapped in the source is split across several of them. A new claim starts
   only where a line opens with "N. ".
5. Parties are repeated once per `@data-format`, and the two spellings differ
   ("BUSSE CLAUS-ADOLF" vs "BUSSE, CLAUS ADOLF, DR."), so string deduplication
   cannot collapse them. The `epodoc` format is the canonical one.
6. Description and abstract text carries the publication's own "[0001]"
   paragraph markers, HTML entities, and <img/> placeholders for equations.
"""

from __future__ import annotations

import base64
import html
import logging
import re
import time
from typing import Any

import httpx

from patent_retriever.domain.exceptions import (
    ParseError,
    PatentNotFoundError,
    SourceUnavailableError,
)
from patent_retriever.domain.models import Claim, PatentDocument
from patent_retriever.domain.sections import SourceSection, classify, map_sections

logger = logging.getLogger(__name__)

AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
BASE_URL = "https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc"
DEFAULT_TIMEOUT_SECONDS = 30.0

# Refresh a little before the token actually expires, to avoid racing the clock.
_TOKEN_SAFETY_MARGIN_SECONDS = 60

_KIND_CODE = re.compile(r"(?P<kind>[A-Z]\d?)$")
_US_PUBLICATION = re.compile(r"^US(?P<year>\d{4})0(?P<serial>\d{6})$")

# "[0001]    " at the head of a paragraph: the publication's own numbering, which
# the renderer regenerates and would otherwise print twice.
_PARAGRAPH_MARKER = re.compile(r"^\[\d{3,5}\]\s*")
# Equations arrive as image placeholders with no text content.
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
# epodoc names carry the party's country as a suffix: "HU YAZHE [US]".
_COUNTRY_SUFFIX = re.compile(r"\s*\[[A-Z]{2}\]\s*$")
# A claim opens with its own number; "10.5 cm" inside a wrapped line must not
# look like one, hence the required space after the dot.
_CLAIM_START = re.compile(r"^\d{1,3}\s*\.\s+")
_WHITESPACE = re.compile(r"\s+")
_ENGLISH = frozenset({"en", "eng"})
# text-only full text has no markup for headings; a heading is simply a short
# upper-case paragraph.
_HEADING_CANDIDATE = re.compile(r"^[A-Z0-9 ,.\-()]{4,60}$")


def to_epodoc(number: str) -> str:
    """Convert a normalized publication number into an OPS epodoc reference.

    The kind code is always dropped. US pre-grant publications additionally lose
    the leading zero of their seven-digit serial, which is why US20250097171A1
    becomes US2025097171 rather than US20250097171.
    """
    reference = _KIND_CODE.sub("", number.upper())
    match = _US_PUBLICATION.match(reference)
    if match is not None:
        return f"US{match.group('year')}{match.group('serial')}"
    return reference


def kind_code(number: str) -> str | None:
    """Return the kind code of a normalized number, or None if it carries none.

    Dropping the kind code from the request means OPS answers with every
    publication of the family member, so it is needed again to pick the right one.
    """
    match = _KIND_CODE.search(number.upper())
    return match.group("kind") if match is not None else None


def _as_list(node: Any) -> list[Any]:
    """Return a list whichever way OPS serialized the element."""
    if node is None:
        return []
    return node if isinstance(node, list) else [node]


def _text(node: Any) -> str:
    """Collect the text content of an OPS node, ignoring XML attributes."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if "$" in node:
            return _text(node["$"])
        return " ".join(
            _text(value) for key, value in node.items() if not key.startswith("@")
        ).strip()
    if isinstance(node, list):
        return " ".join(_text(item) for item in node).strip()
    return str(node)


def _clean(raw: str) -> str:
    """Normalize one OPS text run into a renderable paragraph.

    Entities are unescaped first, because an escaped paragraph marker
    ("&#91;0003&#93;") must become "[0003]" before it can be recognized and
    removed. Image placeholders are dropped rather than the whole tag vocabulary:
    "T <2>" is literal subscript text in text-only full text, not markup.
    """
    text = html.unescape(raw)
    text = _IMG_TAG.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return _PARAGRAPH_MARKER.sub("", text).strip()


def _english_or_first(node: Any) -> tuple[Any, str]:
    """Return (element, language) preferring English.

    OPS orders EP full text with German first, so position cannot be trusted. The
    language is returned as well because some documents have no English variant at
    all and callers need to be able to say so.
    """
    items = [item for item in _as_list(node) if item is not None]
    for item in items:
        if isinstance(item, dict) and str(item.get("@lang", "")).lower() in _ENGLISH:
            return item, "EN"
    if not items:
        return None, ""
    first = items[0]
    language = str(first.get("@lang", "")).upper() if isinstance(first, dict) else ""
    return first, language


def _prefer_english(node: Any) -> Any:
    """Pick the English variant of a multilingual element, or the first available."""
    return _english_or_first(node)[0]


def _select_document(documents: list[Any], number: str) -> dict[str, Any] | None:
    """Pick the publication that was actually asked for.

    An epodoc reference has no kind code, so a request for EP0000001A1 returns
    the A1 and the B1. Their claims and description differ, so falling back to
    the first one silently would return the wrong text.
    """
    wanted = kind_code(number)
    candidates = [item for item in documents if isinstance(item, dict)]
    if wanted is not None:
        for candidate in candidates:
            if str(candidate.get("@kind", "")).upper() == wanted:
                return candidate
    return candidates[0] if candidates else None


def _inventors(data: dict[str, Any]) -> tuple[str, ...]:
    """Return inventor names, one entry per person.

    OPS repeats every party once per data format with different spellings, so the
    epodoc format is taken alone when present. Its trailing country marker is a
    database annotation rather than part of the name, so it is removed.
    """
    nodes = [
        node
        for node in _as_list(data.get("parties", {}).get("inventors", {}).get("inventor"))
        if isinstance(node, dict)
    ]
    epodoc = [node for node in nodes if node.get("@data-format") == "epodoc"]

    seen: set[str] = set()
    names: list[str] = []
    for node in epodoc or nodes:
        name = _COUNTRY_SUFFIX.sub("", _clean(_text(node.get("inventor-name")))).strip(" ,")
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return tuple(names)


def parse_biblio(payload: dict[str, Any], number: str) -> tuple[str, tuple[str, ...], str | None]:
    """Return (title, inventors, abstract) from a biblio response."""
    root = payload.get("ops:world-patent-data", {})
    documents = _as_list(root.get("exchange-documents", {}).get("exchange-document"))
    document = _select_document(documents, number)
    if document is None:
        raise ParseError(f"{number}: no exchange-document in the OPS biblio response.")

    data = document.get("bibliographic-data", {})

    title = _clean(_text(_prefer_english(data.get("invention-title"))))
    if not title:
        raise ParseError(f"{number}: no invention title in the OPS biblio response.")

    abstract_node = _prefer_english(document.get("abstract"))
    abstract = _clean(_text(abstract_node.get("p"))) if isinstance(abstract_node, dict) else ""

    return title, _inventors(data), abstract or None


def _fulltext_block(payload: dict[str, Any], element: str, number: str) -> Any:
    """Return the `claims` or `description` block of a full-text response.

    English is chosen wherever it exists. Not every EP publication has an English
    full text - EP3000001 serves its description in French only - and returning
    nothing would throw the whole description away. The other language is used
    instead, loudly, because the caller is preparing a document for translation
    and needs to know it is not getting English.
    """
    root = payload.get("ops:world-patent-data", {})
    documents = _as_list(root.get("ftxt:fulltext-documents", {}).get("ftxt:fulltext-document"))
    if not documents or not isinstance(documents[0], dict):
        return None

    block, language = _english_or_first(documents[0].get(element))
    if block is not None and language not in {"EN", ""}:
        logger.warning(
            "epo_ops: %s has no English %s; using %s instead.", number, element, language
        )
    return block


def _split_claims(lines: list[str]) -> list[str]:
    """Group claim-text lines into claims.

    A wrapped claim arrives as several sibling lines, only the first of which
    carries the claim number, so a line without one continues the claim above it.
    """
    claims: list[str] = []
    for line in lines:
        if not claims or _CLAIM_START.match(line):
            claims.append(_CLAIM_START.sub("", line))
        else:
            claims[-1] = f"{claims[-1]} {line}"
    return claims


def parse_claims(payload: dict[str, Any], number: str) -> tuple[Claim, ...]:
    """Return the English claims, renumbered from 1 in document order.

    The output format requires an unbroken sequence and OPS numbering lives in
    the text rather than in an attribute, so position decides the number.
    """
    block = _fulltext_block(payload, "claims", number)
    if not isinstance(block, dict):
        raise ParseError(f"{number}: no claims in the OPS response.")

    texts: list[str] = []
    for claim in _as_list(block.get("claim")):
        if not isinstance(claim, dict):
            continue
        lines = [_clean(_text(line)) for line in _as_list(claim.get("claim-text"))]
        texts.extend(_split_claims([line for line in lines if line]))

    texts = [text for text in texts if text]
    if not texts:
        raise ParseError(f"{number}: claims block contained no text.")
    return tuple(Claim(number=index, text=text) for index, text in enumerate(texts, start=1))


def parse_description(payload: dict[str, Any], number: str) -> list[SourceSection]:
    """Split the description into sections using heading-like paragraphs.

    Anything the section mapper recognizes starts a new section; everything else
    is body text. Most EP descriptions carry no headings at all, which is handled
    below rather than left to the mapper's default.
    """
    block = _fulltext_block(payload, "description", number)
    if not isinstance(block, dict):
        return []

    sections: list[SourceSection] = []
    heading: str | None = None
    paragraphs: list[str] = []

    def flush() -> None:
        if paragraphs:
            sections.append(SourceSection(heading=heading, paragraphs=tuple(paragraphs)))

    for node in _as_list(block.get("p")):
        text = _clean(_text(node))
        if not text:
            continue
        if _HEADING_CANDIDATE.match(text) and classify(text) is not None:
            flush()
            heading = text
            paragraphs = []
        else:
            paragraphs.append(text)

    flush()

    # OPS text-only full text carries no heading markup. When nothing was
    # recognized, the whole body is the detailed description - labelling it as
    # such is more accurate than letting the mapper default it to BACKGROUND,
    # and it is a fact about this source, so the source decides it.
    if len(sections) == 1 and sections[0].heading is None:
        return [SourceSection(heading="DETAILED DESCRIPTION", paragraphs=sections[0].paragraphs)]

    return sections


class EpoOpsSource:
    """Fetches patents from EPO Open Patent Services.

    Full text is unavailable for US documents; those raise PatentNotFoundError so
    the retrieval service moves on to the next source.
    """

    name = "epo_ops"

    def __init__(
        self,
        key: str,
        secret: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not key or not secret:
            raise ValueError("EPO OPS requires both a key and a secret.")
        self._key = key
        self._secret = secret
        self._timeout = timeout
        self._client = client
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return self._client.request(method, url, **kwargs)
        with httpx.Client(timeout=self._timeout) as client:
            return client.request(method, url, **kwargs)

    def _access_token(self) -> str:
        """Return a cached token, fetching a new one when it is close to expiry.

        Tokens last twenty minutes and each fetch is a billed request, so a single
        retrieval must not pay for one per endpoint.
        """
        if self._token is not None and time.monotonic() < self._token_expires_at:
            return self._token

        credentials = base64.b64encode(f"{self._key}:{self._secret}".encode()).decode()
        try:
            response = self._request(
                "POST",
                AUTH_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
            )
        except httpx.HTTPError as error:
            raise SourceUnavailableError(f"{self.name}: authentication failed: {error}") from error

        if response.status_code != 200:
            raise SourceUnavailableError(
                f"{self.name}: authentication returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise SourceUnavailableError(
                f"{self.name}: authentication returned a non-JSON response."
            ) from error

        token = payload.get("access_token")
        if not token:
            raise SourceUnavailableError(f"{self.name}: no access token in the auth response.")

        self._token = str(token)
        lifetime = float(payload.get("expires_in", 1200))
        self._token_expires_at = time.monotonic() + lifetime - _TOKEN_SAFETY_MARGIN_SECONDS
        return self._token

    def _service(self, reference: str, service: str, number: str) -> dict[str, Any]:
        """Call one OPS endpoint and map its failures onto the source exceptions."""
        url = f"{BASE_URL}/{reference}/{service}"
        try:
            response = self._request(
                "GET",
                url,
                headers={
                    "Authorization": f"Bearer {self._access_token()}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as error:
            raise SourceUnavailableError(f"{self.name}: {url} failed: {error}") from error

        if response.status_code == 404:
            # OPS answers faults in XML whatever the Accept header asked for.
            if "InvalidCountryCode" in response.text:
                raise PatentNotFoundError(
                    f"{self.name}: OPS does not serve {service} for {number} - "
                    "full text is available for EP and WO documents only."
                )
            raise PatentNotFoundError(f"{self.name}: {number} has no {service} in OPS.")
        if response.status_code in (403, 429):
            raise SourceUnavailableError(
                f"{self.name}: quota or access denied (HTTP {response.status_code})."
            )
        if response.status_code >= 400:
            raise SourceUnavailableError(
                f"{self.name}: {url} returned HTTP {response.status_code}."
            )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as error:
            raise ParseError(f"{self.name}: {url} returned invalid JSON.") from error
        return payload

    def fetch(self, number: str) -> PatentDocument:
        """Retrieve a patent. `number` must already be normalized.

        Biblio, claims, and description are three separate endpoints; there is no
        combined one. Claims come before the description so that a document
        without full text fails on the cheaper call.
        """
        reference = to_epodoc(number)
        logger.info("%s: requesting %s as %s", self.name, number, reference)

        title, inventors, abstract = parse_biblio(
            self._service(reference, "biblio", number), number
        )
        claims = parse_claims(self._service(reference, "claims", number), number)
        sections = parse_description(self._service(reference, "description", number), number)
        background, summary, drawings, detailed = map_sections(sections).to_paragraphs()

        return PatentDocument(
            publication_number=number,
            title=title,
            inventors=inventors,
            abstract=abstract,
            background=background,
            summary=summary,
            brief_description_of_drawings=drawings,
            detailed_description=detailed,
            claims=claims,
        )
