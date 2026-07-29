"""Tests for the CLI.

The CLI is tested through typer's runner with the service patched out. What
matters here is argument handling, exit codes, and file writing - not retrieval,
which has its own tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from patent_retriever.domain.exceptions import (
    InvalidPatentNumberError,
    PatentNotFoundError,
)
from patent_retriever.domain.models import Claim, Paragraph, PatentDocument
from patent_retriever.interfaces import cli
from patent_retriever.services.retrieval import RetrievalResult

runner = CliRunner()

DOCUMENT = PatentDocument(
    publication_number="US20250097171A1",
    title="A Title",
    inventors=("Jane Doe",),
    abstract="An abstract.",
    claims=(Claim(number=1, text="A method."),),
    detailed_description=(Paragraph(number=1, text="Detail."),),
)


def patch_service(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    class FakeService:
        def __init__(self, sources: object) -> None:
            pass

        def retrieve(self, number: str) -> object:
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(cli, "PatentRetrievalService", FakeService)
    monkeypatch.setattr(cli, "build_sources", lambda config: ("stub",))


def test_fetch_writes_both_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_service(
        monkeypatch,
        RetrievalResult(DOCUMENT, "google_patents", is_complete=True, missing_fields=()),
    )
    result = runner.invoke(cli.app, ["fetch", "US20250097171A1", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "US20250097171A1.docx").exists()
    assert (tmp_path / "US20250097171A1.json").exists()


def test_json_only_skips_the_docx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_service(
        monkeypatch,
        RetrievalResult(DOCUMENT, "google_patents", is_complete=True, missing_fields=()),
    )
    runner.invoke(cli.app, ["fetch", "US1A", "--output-dir", str(tmp_path), "--json-only"])
    assert not (tmp_path / "US20250097171A1.docx").exists()
    assert (tmp_path / "US20250097171A1.json").exists()


def test_incomplete_result_warns_but_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_service(
        monkeypatch,
        RetrievalResult(
            DOCUMENT, "google_patents", is_complete=False, missing_fields=("abstract",)
        ),
    )
    result = runner.invoke(cli.app, ["fetch", "US1A", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "abstract" in result.output


def test_invalid_number_exits_with_input_error_code(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_service(monkeypatch, InvalidPatentNumberError("bad number"))
    result = runner.invoke(cli.app, ["fetch", "garbage"])
    assert result.exit_code == cli.EXIT_INVALID_INPUT


def test_not_found_exits_with_not_found_code(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_service(monkeypatch, PatentNotFoundError("nowhere"))
    result = runner.invoke(cli.app, ["fetch", "US1A"])
    assert result.exit_code == cli.EXIT_NOT_FOUND


def test_sources_command_lists_sources() -> None:
    result = runner.invoke(cli.app, ["sources"])
    assert result.exit_code == 0
    assert "google_patents" in result.output
