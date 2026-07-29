"""Tests for the Flask interface.

The service is patched out - these tests cover routing, form handling, status
codes, and downloads. Retrieval itself is tested in test_retrieval.py.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest
from flask.testing import FlaskClient

from patent_retriever.domain.exceptions import (
    InvalidPatentNumberError,
    PatentNotFoundError,
)
from patent_retriever.domain.models import Claim, Paragraph, PatentDocument
from patent_retriever.interfaces.web import app as web
from patent_retriever.services.retrieval import RetrievalResult

DOCUMENT = PatentDocument(
    publication_number="US20250097171A1",
    title="A Test Patent",
    inventors=("Jane Doe",),
    abstract="An abstract.",
    claims=(Claim(number=1, text="A method."),),
    detailed_description=(Paragraph(number=1, text="Detail."),),
)
COMPLETE = RetrievalResult(DOCUMENT, "google_patents", is_complete=True, missing_fields=())


def patch_service(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    class FakeService:
        def __init__(self, sources: object) -> None:
            pass

        def retrieve(self, number: str) -> object:
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(web, "PatentRetrievalService", FakeService)
    monkeypatch.setattr(web, "build_sources", lambda config: ("stub",))


@pytest.fixture
def client() -> FlaskClient:
    app = web.create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_index_renders_the_form(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b'name="number"' in response.data


def test_empty_number_is_rejected(client: FlaskClient) -> None:
    response = client.post("/retrieve", data={"number": "  "})
    assert response.status_code == 400
    assert b"Enter a patent number" in response.data


def test_invalid_number_returns_400(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_service(monkeypatch, InvalidPatentNumberError("bad number"))
    response = client.post("/retrieve", data={"number": "garbage"})
    assert response.status_code == 400
    assert b"bad number" in response.data


def test_not_found_returns_404(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_service(monkeypatch, PatentNotFoundError("nowhere"))
    response = client.post("/retrieve", data={"number": "US1A"})
    assert response.status_code == 404


def test_successful_retrieval_shows_preview_and_links(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_service(monkeypatch, COMPLETE)
    response = client.post("/retrieve", data={"number": "US20250097171A1"})
    assert response.status_code == 200
    assert b"A Test Patent" in response.data
    assert b"/download/US20250097171A1.docx" in response.data
    assert b"UNITED STATES LETTERS PATENT" in response.data


def test_incomplete_result_shows_a_warning(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_service(
        monkeypatch,
        RetrievalResult(
            DOCUMENT, "google_patents", is_complete=False, missing_fields=("abstract",)
        ),
    )
    response = client.post("/retrieve", data={"number": "US1A"})
    assert response.status_code == 200
    assert b'class="notice"' in response.data
    assert b"abstract" in response.data


def test_docx_download_returns_a_word_file(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_service(monkeypatch, COMPLETE)
    client.post("/retrieve", data={"number": "US20250097171A1"})

    response = client.get("/download/US20250097171A1.docx")
    assert response.status_code == 200
    assert response.mimetype == web.DOCX_MIME
    with zipfile.ZipFile(BytesIO(response.data)) as archive:
        assert "word/document.xml" in archive.namelist()


def test_json_download_carries_the_source_name(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_service(monkeypatch, COMPLETE)
    client.post("/retrieve", data={"number": "US20250097171A1"})

    response = client.get("/download/US20250097171A1.json")
    assert response.status_code == 200
    assert json.loads(response.data)["source"] == "google_patents"


def test_download_without_prior_retrieval_returns_404(client: FlaskClient) -> None:
    assert client.get("/download/US9999999B1.docx").status_code == 404


def test_render_options_reach_the_docx(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_service(monkeypatch, COMPLETE)
    client.post(
        "/retrieve",
        data={"number": "US1A", "docket": "ARM-42", "client_ref": "CR-7"},
    )
    response = client.get("/download/US20250097171A1.docx")
    with zipfile.ZipFile(BytesIO(response.data)) as archive:
        header_name = next(n for n in archive.namelist() if n.startswith("word/header"))
        header = archive.read(header_name).decode()
    assert "ARM-42" in header
    assert "CR-7" in header


def test_cache_evicts_beyond_its_limit() -> None:
    cache = web.ResultCache(max_entries=2)
    from patent_retriever.domain.models import RenderOptions

    for key in ("a", "b", "c"):
        cache.put(key, COMPLETE, RenderOptions())

    assert cache.get("a") is None
    assert cache.get("c") is not None
