"""Render a PatentDocument as JSON.

The JSON output is the same data as the .docx, in a form other tools can consume.
It deliberately mirrors the domain model rather than the document format: the
.docx exists to be read by a translation tool, the JSON exists to be parsed.

Note the absence of formatting concerns here. No bracketed paragraph IDs, no
uppercase headings - those belong to the .docx presentation and would be noise
in a data interchange format.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from patent_retriever.domain.models import PatentDocument, RenderOptions

SCHEMA_VERSION = 1


def _to_json_types(value: Any) -> Any:
    """Convert tuples to lists so render_dict matches the parsed JSON exactly.

    dataclasses.asdict preserves tuple types, but JSON has only arrays. Without
    this, a dict -> JSON -> dict round-trip would not compare equal.
    """
    if isinstance(value, tuple | list):
        return [_to_json_types(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_json_types(item) for key, item in value.items()}
    return value


def render_dict(
    document: PatentDocument,
    options: RenderOptions | None = None,
    source_name: str | None = None,
) -> dict[str, Any]:
    """Return the document as a plain dictionary.

    `schema_version` lets consumers detect format changes instead of inferring
    them. `source` is provenance for humans reading the file - nothing should
    branch on it.
    """
    options = options or RenderOptions()

    return {
        "schema_version": SCHEMA_VERSION,
        "source": source_name,
        "render_options": _to_json_types(asdict(options)),
        "patent": _to_json_types(asdict(document.renumbered())),
    }


def render_json(
    document: PatentDocument,
    options: RenderOptions | None = None,
    source_name: str | None = None,
    indent: int = 2,
) -> str:
    """Return the document as a JSON string.

    `ensure_ascii=False` keeps non-ASCII characters readable rather than escaping
    them - patent text routinely contains accented names and symbols, and this
    output is read by people as well as machines.
    """
    return json.dumps(
        render_dict(document, options, source_name),
        indent=indent,
        ensure_ascii=False,
    )


def write_json(
    document: PatentDocument,
    path: Path,
    options: RenderOptions | None = None,
    source_name: str | None = None,
) -> Path:
    """Write the rendered JSON to disk and return the path written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(document, options, source_name), encoding="utf-8")
    return path
