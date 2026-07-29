"""Google Patents source.

Google Patents renders patent content server-side, so a plain HTTP GET plus HTML
parsing is sufficient - no browser automation required.

Parsing is a pure function of the HTML, separate from fetching. That split means
the parser is tested against a saved fixture with no network access, and the HTTP
layer is tested only for its error mapping.
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup, Tag

from patent_retriever.domain.exceptions import (
    ParseError,
    PatentNotFoundError,
    SourceUnavailableError,
)
from patent_retriever.domain.models import Claim, PatentDocument
from patent_retriever.domain.sections import SourceSection, map_sections

BASE_URL = "https://patents.google.com/patent"
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "Mozilla/5.0 (compatible; PatentRetriever/0.1)"

# Google prefixes claim text with its own number, e.g. "1 . A method...".
_CLAIM_PREFIX = re.compile(r"^\s*\d+\s*\.\s*")
# A trailing figure reference that the output format requires on its own line.
_TRAILING_FIGURE = re.compile(r"\s*(Fig\.\s*\d+[A-Z]?\.)\s*$", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _meta(soup: BeautifulSoup, name: str, scheme: str | None = None) -> list[str]:
    selector = f'meta[name="{name}"]'
    if scheme is not None:
        selector += f'[scheme="{scheme}"]'
    return [_clean(str(tag.get("content", ""))) for tag in soup.select(selector)]


def _first_meta(soup: BeautifulSoup, name: str) -> str | None:
    values = _meta(soup, name)
    return values[0] if values else None


def _parse_publication_number(soup: BeautifulSoup, fallback: str) -> str:
    """Google formats this as 'US:20250097171:A1'."""
    raw = _first_meta(soup, "citation_patent_publication_number")
    return raw.replace(":", "") if raw else fallback


def _parse_abstract(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Return (abstract, trailing figure reference).

    The output format wants the figure reference on its own line, so it is split
    off here rather than left embedded in the abstract text.
    """
    node = soup.select_one("div.abstract") or soup.select_one("section[itemprop=abstract]")
    if node is None:
        return None, None

    text = _clean(node.get_text(" ", strip=True))
    if not text:
        return None, None

    match = _TRAILING_FIGURE.search(text)
    if match is None:
        return text, None
    return text[: match.start()].strip(), match.group(1)


def _parse_source_sections(soup: BeautifulSoup) -> list[SourceSection]:
    """Walk the description in document order, grouping lines under their heading.

    Google marks headings with a <heading> element and body paragraphs with
    <div class="description-line">. Both appear in reading order, so a single
    recursive walk reconstructs the original section structure.
    """
    description = soup.select_one("section[itemprop=description]")
    if description is None:
        return []

    sections: list[SourceSection] = []
    heading: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if lines:
            sections.append(SourceSection(heading=heading, paragraphs=tuple(lines)))

    for element in description.find_all(True):
        if not isinstance(element, Tag):
            continue
        if element.name == "heading":
            flush()
            heading = _clean(element.get_text(" ", strip=True))
            lines = []
        elif "description-line" in (element.get("class") or []):
            text = _clean(element.get_text(" ", strip=True))
            if text:
                lines.append(text)

    flush()
    return sections


def _parse_claims(soup: BeautifulSoup) -> tuple[Claim, ...]:
    """Extract claims, renumbering them 1..N in document order.

    Only <div class="claim"> elements carrying an id are real claims; the outer
    wrapper has none. Google's own numbering is discarded because the output format
    requires an unbroken sequence.
    """
    claims: list[Claim] = []
    for index, node in enumerate(soup.select("div.claim[id]"), start=1):
        text = _CLAIM_PREFIX.sub("", _clean(node.get_text(" ", strip=True)))
        if text:
            claims.append(Claim(number=index, text=text))
    return tuple(claims)


def parse_html(html: str, number: str) -> PatentDocument:
    """Convert a Google Patents page into a PatentDocument.

    Raises:
        ParseError: the page is missing a title or claims, which usually means
            Google changed its markup.
    """
    soup = BeautifulSoup(html, "lxml")

    title = _first_meta(soup, "DC.title")
    if not title:
        raise ParseError(f"{number}: no title found in the Google Patents page.")

    claims = _parse_claims(soup)
    if not claims:
        raise ParseError(f"{number}: no claims found in the Google Patents page.")

    abstract, figure_reference = _parse_abstract(soup)
    background, summary, drawings, detailed = map_sections(
        _parse_source_sections(soup)
    ).to_paragraphs()

    return PatentDocument(
        publication_number=_parse_publication_number(soup, number),
        title=title,
        inventors=tuple(_meta(soup, "DC.contributor", scheme="inventor")),
        abstract=abstract,
        abstract_figure_reference=figure_reference,
        background=background,
        summary=summary,
        brief_description_of_drawings=drawings,
        detailed_description=detailed,
        claims=claims,
    )


class GooglePatentsSource:
    """Fetches patents by scraping patents.google.com."""

    name = "google_patents"

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Accept an injected client so tests and the service can control transport."""
        self._client = client
        self._timeout = timeout

    def _get(self, url: str) -> httpx.Response:
        headers = {"User-Agent": USER_AGENT}
        if self._client is not None:
            return self._client.get(url, headers=headers, follow_redirects=True)
        with httpx.Client(timeout=self._timeout) as client:
            return client.get(url, headers=headers, follow_redirects=True)

    def fetch(self, number: str) -> PatentDocument:
        """Retrieve and parse a patent. `number` must already be normalized."""
        url = f"{BASE_URL}/{number}/en"

        try:
            response = self._get(url)
        except httpx.HTTPError as error:
            raise SourceUnavailableError(
                f"{self.name}: request to {url} failed: {error}"
            ) from error

        if response.status_code == 404:
            raise PatentNotFoundError(f"{self.name}: {number} not found.")
        if response.status_code >= 400:
            raise SourceUnavailableError(
                f"{self.name}: {url} returned HTTP {response.status_code}."
            )

        return parse_html(response.text, number)
