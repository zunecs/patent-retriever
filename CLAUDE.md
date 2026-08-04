# Patent Retriever — working context

Python application that retrieves patents, normalizes them into one internal
model, and renders a `.docx` matching a strict legal template plus a JSON
handoff file. It does **not** translate.

Repo: https://github.com/zunecs/patent-retriever (public)

---

## The one rule

**Dependencies point inward.** `domain/` imports nothing outside the standard
library. Sources, renderers, and interfaces all depend on the domain; the domain
depends on none of them.

If you find yourself adding `import httpx` or `import docx` under `domain/`, the
design has decayed — put it in the adapter instead.

```
CLI  ─┐
      ├─→  RetrievalService  ─→  Sources ─→ SectionMapper
Flask ─┘          ├─→  Renderers (.docx, JSON)
                  └─→  Domain (PatentDocument)
```

| Package | Owns | Must not |
|---|---|---|
| `domain/` | `PatentDocument`, `SectionMapper`, exceptions, number normalization | Any I/O |
| `sources/` | One adapter each, `fetch(number) -> PatentDocument` | Know other sources or output formats |
| `services/` | Fallback chain, completeness policy | Parse HTML or write files |
| `renderers/` | `PatentDocument` → bytes | Fetch anything, mutate the document |
| `interfaces/` | CLI, Flask — thin | Contain business logic |

Adding a source touches exactly two files: a new module in `sources/`, and one
entry in `sources/registry.py`.

---

## Decisions already made — don't relitigate

- **`PatentDocument` is a frozen dataclass holding tuples**, validated in
  `__post_init__`. Invalid documents cannot exist, so downstream code never
  checks for missing titles or empty claims.
- **No Pydantic.** Validation is five lines; a third-party import in the domain
  would reverse the dependency arrows.
- **Completeness is a service concern.** Sources return a document or raise.
  `services/retrieval.py` decides whether the result is good enough to stop.
- **Presentation lives in the renderer.** The model stores paragraph numbers as
  plain integers; `[0001]` formatting belongs to the `.docx` only.
- **`RenderOptions` carries docket and client reference** — properties of a
  rendering job, not of the patent.
- **Exception hierarchy drives the fallback.** Anything under `SourceError`
  means "try the next source". `InvalidPatentNumberError` stops immediately.

---

## Output format — non-obvious, measured from a real sample

Full spec in `docs/output-format.md`. The parts that surprise people:

- Times New Roman 13 pt, 1.5 line spacing, 6 pt after, justified body
- Margins: top 1.2", others 1"
- **Right-aligned running page header** on every page carrying the docket and
  client reference — not a one-time block
- Cover: four blank paragraphs, then `APPLICATION` / `FOR` /
  `UNITED STATES LETTERS PATENT` as three centred 18 pt bold lines
- `TITLE:` and `INVENTOR:` are 14 pt bold; `TITLE:` is followed by two tabs
- **No blank line between a section heading and its first paragraph**
- Section headings centred 13 pt not bold — except `ABSTRACT`, 14 pt bold
- Paragraph IDs are a **genuine Word numbered list**, not literal text. Word
  cannot zero-pad to four digits through any built-in format, so
  `renderers/docx_renderer.py` injects an ECMA-376
  `<w:numFmt w:val="custom" w:format="0001, 0002, 0003, ..."/>` definition into
  `numbering.xml` directly. python-docx has no API for this.
- The abstract closes with `Fig.1.` — no space after `Fig.`

---

## EPO OPS — findings from live probing

- Auth works: OAuth2 client credentials at `/3.2/auth/accesstoken`.
- **Reference format**: `epodoc` drops the kind code and, for US publications,
  the leading zero of the serial. `US20250097171A1` → `US2025097171`.
  Getting this wrong returns a misleading 404.
- **Full text is EP/WO only.** US claims and description return
  `CLIENT.InvalidCountryCode`. US biblio and abstract work fine.
- Therefore EPO is an EP/WO source; US patents raise and fall through to Google
  Patents. That is intended behaviour, not a bug.
- The `/search` endpoint times out at 20 s on the non-paying tier.
- JSON is a mechanical translation of XML: text under `"$"`, attributes under
  `"@name"`, and any element may be an object or a list. Claims and description
  are returned per language with **German first** for EP — select English
  explicitly.
- Fixtures saved in `tests/fixtures/epo_EP0000001_*.json`.

---

## Environment gotchas

- **The editable install does not work on this machine.** The `.pth` file is
  correct but silently ignored. Use `pip install .` and re-run it after code
  changes. Tests are unaffected — `pythonpath = ["src"]` in `pyproject.toml`.
- If `import patent_retriever` fails, run `which python` first. It must end in
  `patent-retriever/.venv/bin/python`.
- `.env` is gitignored and holds the EPO credentials. `.env.example` is the
  template.

---

## Commands

```bash
python -m pytest -q                        # 147 tests, no network
mypy                                       # strict, src only
ruff check . && ruff format .
python -m pip install . -q                 # after any code change
patent-retriever fetch US20250097171A1 -v
python -m patent_retriever.interfaces.web.app
```

---

## Conventions

- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`
- Type hints everywhere; mypy strict must pass
- Docstrings explain **why**, not what
- Tests never touch the network — saved fixtures plus `respx`
- Don't test generated dataclass methods or third-party behaviour
- No placeholder or half-finished modules committed

---

## Current state

Complete and published: domain, Google Patents source, retrieval service, both
renderers, CLI, Flask UI, CI, README, MIT licence.

In progress: `sources/epo_ops.py` — written, needs its test file built against
the saved EP fixtures, and needs verifying that `EP0000001A1` renders end to end
while `US20250097171A1` falls through to Google.

Not started: technical documentation `.docx`, screenshots for the README.