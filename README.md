# Patent Retriever

Retrieves patent documents from external sources, normalizes them into a
single internal model, and generates the `.docx` format required by the
Patent Translation tool, plus a JSON representation of the same data.

**This application does not perform translation.**

## Status

In development.

## Requirements

- Python 3.11+

## Installation

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

## Architecture

- `domain/` — the `PatentDocument` model and section-mapping logic. No I/O.
- `sources/` — one adapter per patent source, each implementing `fetch(number) -> PatentDocument`.
- `services/` — orchestrates the source fallback chain.
- `renderers/` — turns a `PatentDocument` into `.docx` or JSON.
- `interfaces/` — CLI and Flask entry points.

Adding a new source requires only a new module in `sources/`. Nothing else changes.

The required output format is specified in [`docs/output-format.md`](docs/output-format.md).