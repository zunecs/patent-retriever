"""Tests for the JSON renderer."""

from __future__ import annotations

import json
from pathlib import Path

from patent_retriever.domain.models import PatentDocument, RenderOptions
from patent_retriever.renderers.json_renderer import (
    SCHEMA_VERSION,
    render_dict,
    render_json,
    write_json,
)


def test_envelope_contains_schema_version_and_source(full_document: PatentDocument) -> None:
    result = render_dict(full_document, source_name="google_patents")
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["source"] == "google_patents"


def test_render_options_are_included(full_document: PatentDocument) -> None:
    result = render_dict(
        full_document,
        RenderOptions(attorney_docket_number="ARM-1", client_reference="CR-1"),
    )
    assert result["render_options"] == {
        "attorney_docket_number": "ARM-1",
        "client_reference": "CR-1",
    }


def test_patent_fields_are_present(full_document: PatentDocument) -> None:
    patent = render_dict(full_document)["patent"]
    assert patent["publication_number"] == full_document.publication_number
    assert patent["title"] == full_document.title
    assert patent["inventors"] == ["Jane Doe", "John Smith"]
    assert patent["abstract_figure_reference"] == "Fig. 1."


def test_paragraphs_are_renumbered_continuously(full_document: PatentDocument) -> None:
    patent = render_dict(full_document)["patent"]
    numbers = [
        paragraph["number"]
        for key in (
            "background",
            "summary",
            "brief_description_of_drawings",
            "detailed_description",
        )
        for paragraph in patent[key]
    ]
    assert numbers == [1, 2, 3, 4, 5]


def test_claims_keep_their_own_numbering(full_document: PatentDocument) -> None:
    patent = render_dict(full_document)["patent"]
    assert [claim["number"] for claim in patent["claims"]] == [1, 2]


def test_no_docx_formatting_leaks_into_json(full_document: PatentDocument) -> None:
    output = render_json(full_document)
    assert "[0001]" not in output
    assert "What is claimed:" not in output


def test_output_is_valid_json_and_round_trips(full_document: PatentDocument) -> None:
    parsed = json.loads(render_json(full_document))
    assert parsed == render_dict(full_document)


def test_non_ascii_characters_are_not_escaped() -> None:
    from patent_retriever.domain.models import Claim

    document = PatentDocument(
        publication_number="EP1000000B1",
        title="Procédé de fabrication",
        claims=(Claim(number=1, text="Un procédé."),),
    )
    output = render_json(document)
    assert "Procédé" in output
    assert "\\u" not in output


def test_write_json_creates_parent_directories(
    tmp_path: Path, full_document: PatentDocument
) -> None:
    target = tmp_path / "nested" / "out.json"
    result = write_json(full_document, target, source_name="stub")
    assert result == target
    assert json.loads(target.read_text(encoding="utf-8"))["source"] == "stub"
