# Build report — finishing the EPO OPS source

Scope of this session: complete `sources/epo_ops.py`, register it, test it
against saved fixtures, verify it end to end, and update the documentation.
Commits `ca4d8ef`, `cda6022`, `157babf` on `main`.

---

## 1. What changed

### Added

| File | Why |
|---|---|
| `src/patent_retriever/sources/epo_ops.py` | The EPO OPS adapter. Existed in partial form (untracked, never committed); rewritten to fix four parsing defects found against real responses — see §5. |
| `tests/test_epo_ops.py` | 48 tests covering reference normalization, every parsing quirk, every error mapping, and token caching. |
| `tests/fixtures/epo_EP3000001_biblio.json` | Modern EP document: DE/FR/EN titles, two publications for one reference, no abstract. |
| `tests/fixtures/epo_EP3000001_claims.json` | English claims served third after DE and FR; 21 `claim-text` lines carrying 12 claims. |
| `tests/fixtures/epo_EP3000001_description.json` | Description served as a single object in French only — no English variant exists. |
| `tests/fixtures/epo_EP0000001_biblio.json` | 1978 document: one reference returns the A1 and the B1, parties repeated per data format, abstract carrying a `[0001]` marker. (Existed untracked; re-captured.) |
| `tests/fixtures/epo_EP0000001_claims.json` | German claims split across lines; English block is a corrupt OCR dump — see §5. (Existed untracked; re-captured.) |
| `tests/fixtures/epo_EP0000001_description.json` | English description with escaped paragraph markers and `<img/>` placeholders. (Existed untracked; re-captured.) |
| `tests/fixtures/epo_US2025097171_biblio.json` | US biblio, which OPS *does* serve. Single `exchange-document` object and single `invention-title` object — the single-vs-list counter-case to EP. |
| `tests/fixtures/epo_US2025097171_claims_fault.xml` | The literal `CLIENT.InvalidCountryCode` fault, used to test the US fallback trigger. |
| `tests/fixtures/epo_US2025097171_description_fault.xml` | Same fault from the description endpoint; written by the capture script for completeness. |
| `BUILD-REPORT.md` | This file. |

### Modified

| File | Why |
|---|---|
| `src/patent_retriever/sources/registry.py` | Registers `epo_ops`. Its builder now names the specific missing credential variable instead of listing both. |
| `src/patent_retriever/interfaces/web/app.py` | Replaced a global `errorhandler(ValueError)` with a `try/except` around source construction — see §5. |
| `scripts/check_epo.py` | Generalized to capture all three references and to save fault bodies, so the fixture set is reproducible rather than hand-made. |
| `tests/test_config.py` | Four tests: `epo_ops` builds with credentials, and the error names `EPO_OPS_KEY`, `EPO_OPS_SECRET`, or both. |
| `tests/test_web.py` | One test: an unbuildable source returns 500 with the configuration message. |
| `README.md` | EPO OPS setup section, four new limitation entries, EP usage example, fixture note in Development. |
| `.env.example` | Registration steps, both variables marked required, `epo_ops,google_patents` shown as the recommended order. |
| `CLAUDE.md` | Current state updated (EPO source finished); the OPS findings section extended with the seven behaviours measured this session; test count 147 → 200. |

Nothing under `domain/` was touched. `services/`, `renderers/`, and the CLI are
unchanged — adding the source touched exactly the two files the architecture
promises, plus its tests.

---

## 2. EPO OPS implementation

### Auth flow

OAuth2 client credentials against `https://ops.epo.org/3.2/auth/accesstoken`.

- `POST` with `Authorization: Basic base64(key:secret)` and
  `Content-Type: application/x-www-form-urlencoded`, body `grant_type=client_credentials`.
- The response carries `access_token` and `expires_in` (observed: `1199`, i.e. 20 minutes).
- The token is cached on the source instance. `_token_expires_at` is set to
  `time.monotonic() + expires_in - 60`; the 60-second margin avoids presenting a
  token that expires mid-flight.
- `_access_token()` returns the cached token while it is inside that window, so a
  retrieval pays for one auth request, not three. Verified by
  `test_one_token_is_shared_by_all_three_endpoints`.
- `time.monotonic()` rather than wall clock, so a clock adjustment cannot make a
  live token look expired or vice versa.

### Reference normalization

`to_epodoc(number)` converts a normalized publication number into an epodoc
reference:

1. The kind code is always dropped: `EP0000001A1` → `EP0000001`.
2. US **publications** additionally lose the leading zero of their seven-digit
   serial: `US20250097171A1` → `US2025097171`.
3. US **grants** are not publications and are left intact: `US11234567B2` →
   `US11234567`.

Rule 2 is matched by `^US(\d{4})0(\d{6})$` against the kind-stripped reference,
so it only fires on the 4-digit-year + 7-digit-serial shape. Getting it wrong is
punished misleadingly: the live probe confirmed
`GET .../epodoc/US20250097171/biblio` returns **404 `SERVER.EntityNotFound`**
("No results found"), which reads as "this patent does not exist" rather than
"your reference is malformed", while `US2025097171` returns 200.

Because the kind code is dropped from the request, it is read back off the
original number by `kind_code()` and used to pick the right publication out of
the response — `EP0000001` returns both the A1 and the B1.

### The three endpoints

All under `https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{reference}/`,
called with `Authorization: Bearer <token>` and `Accept: application/json`.
There is no combined endpoint; `fetch()` makes three calls.

| Call | Yields |
|---|---|
| `/biblio` | title, inventors, abstract |
| `/claims` | claims |
| `/description` | description paragraphs, fed to the existing `SectionMapper` |

Claims are requested before the description so that a document without full text
fails on the smaller response.

The description is converted to `SourceSection` objects and handed to the
existing `domain.sections.map_sections` / `classify`. No section-mapping logic is
duplicated in the source.

### JSON quirks and how each is handled

| Quirk | Handling |
|---|---|
| Text under `"$"`, attributes under `"@name"` | `_text()` walks a node, following `"$"` when present and skipping any key starting with `"@"`. |
| Any element may be an object or a list | `_as_list()` wraps a bare object. Confirmed both ways in the fixtures: EP `exchange-document` is a list of 2, US is a single object; EP `invention-title` is a list of 3, US is a single object; EP3000001 `description` is a single object while its `claims` is a list of 3. |
| Full text per language, German first | `_english_or_first()` scans for `@lang` in `{en, eng}` (case-insensitively — OPS uses lowercase `en` in biblio and uppercase `EN` in full text) before falling back to the first entry. |
| No English variant at all | The other language is used and a `WARNING` is logged naming it (`"EP3000001A1 has no English description; using FR instead."`). See §6 for why. |
| One reference, several publications | `_select_document()` matches `@kind` against the requested number's kind code, falling back to the first. `EP0000001A1` and `EP0000001B1` yield different English titles. |
| `claim-text` entries are lines, not claims | `_split_claims()` starts a new claim only on a line matching `^\d{1,3}\s*\.\s+`; any other line is appended to the claim above. The space after the dot is required so `"10.5 cm"` opening a continuation line cannot start claim 10. Claims are then renumbered 1..N by position, as the output format requires. |
| Parties repeated once per `@data-format` with different spellings | `_inventors()` takes the `@data-format == "epodoc"` entries alone when any exist, and falls back to all entries otherwise. String deduplication cannot work here: OPS returns `BUSSE CLAUS-ADOLF`, `BUSSE CLAUS ADOLF`, and `BUSSE, CLAUS ADOLF, DR.` for one person. |
| epodoc names carry a country marker | `HU YAZHE [US]` → `HU YAZHE`. It is a database annotation, not part of the name. |
| `[0001]` paragraph markers in description and abstract text | `_clean()` strips a leading `\[\d{3,5}\]`. The renderer regenerates paragraph numbers as a Word list, so leaving them would print the number twice. |
| HTML entities | `html.unescape()` runs **first**, so an escaped marker (`&#91;0003&#93;`) becomes `[0003]` and is then recognized and removed. |
| `<img/>` placeholders for equations | Stripped. A paragraph that held only an image becomes empty and is dropped. Only `<img>` is stripped, not all tags: `T <2>` and `Q <o>` are literal subscript text in text-only full text, and stripping them would corrupt the sentence. |
| Fault bodies are XML regardless of `Accept` | Error mapping is driven by status code; the body is only inspected as a string for `"InvalidCountryCode"`. |

### Error mapping

| Condition | Exception | Message contains |
|---|---|---|
| Auth: non-200 | `SourceUnavailableError` | `authentication returned HTTP <status>` |
| Auth: network/timeout (`httpx.HTTPError`) | `SourceUnavailableError` | `authentication failed` |
| Auth: 200 with no `access_token` | `SourceUnavailableError` | `no access token in the auth response` |
| Auth: 200 with a non-JSON body | `SourceUnavailableError` | `authentication returned a non-JSON response` |
| Service: 404 with `InvalidCountryCode` in the body | `PatentNotFoundError` | `full text is available for EP and WO documents only` |
| Service: any other 404 | `PatentNotFoundError` | `<number> has no <service> in OPS` |
| Service: 403 or 429 | `SourceUnavailableError` | `quota or access denied (HTTP <status>)` |
| Service: any other status ≥ 400 (incl. all 5xx) | `SourceUnavailableError` | `returned HTTP <status>` |
| Service: network/timeout (`httpx.HTTPError`) | `SourceUnavailableError` | `<url> failed` |
| Service: 200 with an unparseable body | `ParseError` | `returned invalid JSON` |
| Response parses but lacks an `exchange-document`, a title, or claims | `ParseError` | `no exchange-document` / `no invention title` / `no claims` / `no text` |
| Constructed without a key or secret | `ValueError` | `requires both a key and a secret` |

All of `PatentNotFoundError`, `SourceUnavailableError`, and `ParseError` derive
from `SourceError`, so every one of them makes the retrieval service move to the
next source. `ValueError` is not a `SourceError` — it is a configuration fault
and is caught at the interface boundary instead.

---

## 3. Test strategy

Parsing is tested as a pure function of saved JSON; the HTTP layer is tested with
`respx` for the only thing it owns, which is error mapping and the token cache.
This mirrors how `test_google_patents.py` is organized. **No test touches the
network.** Fixtures were captured from live OPS by `scripts/check_epo.py`, which
is committed so they can be regenerated rather than edited by hand.

### `tests/test_epo_ops.py` — 48 tests

**Reference normalization (9)** — `to_epodoc` parametrized over EP/WO kind-code
removal, the US publication leading-zero rule (with and without a kind code, plus
a serial with leading zeros), and US grants left intact; `kind_code` reading the
kind back off a number and returning `None` when there is none.

**Biblio parsing (9)** — English title chosen when German comes first; kind code
selecting the A1 vs the B1 out of one response; a single `exchange-document`
object handled like a list; inventors taken from the `epodoc` data format only
(1 person, not 3 spellings); country suffix removed (`HU YAZHE`, 6 inventors);
`[0001]` stripped from the abstract; a document with no abstract reporting
`None`; `ParseError` for a missing `exchange-document` and for a missing title.

**Claims parsing (8)** — English block selected over DE and FR; 21 lines joined
into 12 claims with the correct last claim; renumbering 1..12; no residual claim
numbers in the text; `_split_claims` unit-tested for the continuation rule and
for the `"10.5 cm"` decimal case; `ParseError` for a missing block and for a
block whose text is whitespace.

**Description parsing (5)** — `[0001]` markers stripped; the escaped-marker and
bare-`<img/>` paragraphs producing no empty entries (37 in the response → 35
paragraphs); `T <2>` subscripts left intact; the French fallback returning
sections *and* logging the warning; a missing description returning `[]`.

**Construction and token handling (7)** — credentials required; protocol
conformance; one auth call shared by three endpoint calls; `expires_in: 0`
forcing a refetch per call (3); auth 401, auth without a token, and an
unreachable auth endpoint.

**Error mapping (10)** — happy-path `fetch` producing a document with 12 claims;
US biblio-then-`InvalidCountryCode` raising `PatentNotFoundError` naming EP and
WO; a plain 404; 403 and 429 parametrized; 500, 502, 503 parametrized; a network
error; a 200 with an unparseable body.

### Other test files

- `tests/test_config.py` — 4 added: `epo_ops` builds when both credentials are
  present, and the `ValueError` names `EPO_OPS_KEY`, `EPO_OPS_SECRET`, or both.
- `tests/test_web.py` — 1 added: an unbuildable source returns 500 carrying the
  configuration message.

### Deliberately not tested

- **Live OPS.** Covered by the manual end-to-end runs in §4 instead. Putting the
  network in the suite would make CI depend on credentials and on a third party.
- **`httpx` and `respx` behaviour.** Only this package's mapping of their results.
- **`SectionMapper`.** Already covered by `tests/test_sections.py`; the EPO source
  calls it rather than reimplementing it, so retesting it here would test the
  wrong module.
- **Rendering of EPO-sourced documents.** `test_docx_renderer.py` covers the
  renderer against the domain model; the source's only obligation is to produce a
  valid `PatentDocument`, which the happy-path `fetch` test asserts.
- **Generated dataclass methods**, per the project convention.

### Final count

**200 tests, all passing** (147 before this session; +48 EPO, +4 registry, +1 web).

---

## 4. Verification output

Both commands were run against live OPS after `python -m pip install . -q`.

### `PATENT_SOURCE_ORDER=epo_ops patent-retriever fetch EP0000001A1 -v`

```
INFO patent_retriever.services.retrieval: Trying epo_ops for EP0000001A1
INFO patent_retriever.sources.epo_ops: epo_ops: requesting EP0000001A1 as EP0000001
INFO httpx: HTTP Request: POST https://ops.epo.org/3.2/auth/accesstoken "HTTP/1.1 200 OK"
INFO httpx: HTTP Request: GET https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/EP0000001/biblio "HTTP/1.1 200 OK"
INFO httpx: HTTP Request: GET https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/EP0000001/claims "HTTP/1.1 200 OK"
INFO httpx: HTTP Request: GET https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/EP0000001/description "HTTP/1.1 200 OK"
INFO patent_retriever.services.retrieval: epo_ops returned an incomplete document for EP0000001A1 (missing: detailed_description)
INFO patent_retriever.services.retrieval: Returning best available document for EP0000001A1 from epo_ops
Retrieved EP0000001A1 from epo_ops
Warning: missing detailed_description
  output/EP0000001A1.docx
  output/EP0000001A1.json
exit: 0
```

A document is produced. One auth request serves all three endpoints. The
`detailed_description` warning is expected and explained in §5: the OPS
description has no headings, so everything lands in `BACKGROUND`.

### `PATENT_SOURCE_ORDER=epo_ops,google_patents patent-retriever fetch US20250097171A1 -v`

```
INFO patent_retriever.services.retrieval: Trying epo_ops for US20250097171A1
INFO patent_retriever.sources.epo_ops: epo_ops: requesting US20250097171A1 as US2025097171
INFO httpx: HTTP Request: POST https://ops.epo.org/3.2/auth/accesstoken "HTTP/1.1 200 OK"
INFO httpx: HTTP Request: GET https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/US2025097171/biblio "HTTP/1.1 200 OK"
INFO httpx: HTTP Request: GET https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/US2025097171/claims "HTTP/1.1 404 Not Found"
WARNING patent_retriever.services.retrieval: epo_ops failed for US20250097171A1: epo_ops: OPS does not serve claims for US20250097171A1 - full text is available for EP and WO documents only.
INFO patent_retriever.services.retrieval: Trying google_patents for US20250097171A1
INFO httpx: HTTP Request: GET https://patents.google.com/patent/US20250097171A1/en "HTTP/1.1 200 OK"
INFO patent_retriever.services.retrieval: google_patents returned a complete document for US20250097171A1
Retrieved US20250097171A1 from google_patents
  output/US20250097171A1.docx
  output/US20250097171A1.json
exit: 0
```

The reference is normalized to `US2025097171`, biblio succeeds, claims returns
404 with the country message, and Google Patents picks the patent up and returns
a complete document. The fallback chain works.

### Generated `.docx` validity

Checked three ways, not by eye alone:

```
output/EP0000001A1.docx: 18 parts, all XML parses, 58 paragraphs, custom numFmt present=True, header='PATENT APPLICATION'
output/US20250097171A1.docx: 18 parts, all XML parses, 191 paragraphs, custom numFmt present=True, header='PATENT APPLICATION'
```

1. `zipfile.testzip()` returns `None` and every `.xml`/`.rels` part parses under
   `lxml`.
2. `python-docx` opens both; the injected `<w:numFmt w:format="0001, 0002, 0003, ...">`
   is present in `word/numbering.xml`; the running header carries
   `PATENT APPLICATION`.
3. macOS `textutil -convert txt` — an independent Word reader — renders the file:

```
APPLICATION
FOR
UNITED STATES LETTERS PATENT



TITLE:		METHOD FOR DEFINING FIBRE TRAJECTORIES ON THE BASIS OF A VECTOR FIELD
```

The EP0000001 body reads `APPLICATION` / `FOR` / `UNITED STATES LETTERS PATENT`,
`TITLE:` + two tabs + `Thermal heat pump`, `INVENTOR:` + `BUSSE CLAUS-ADOLF`,
then `BACKGROUND`, `CLAIMS`, `What is claimed:`, and `ABSTRACT` in template
order.

A third document, `EP3000001A1`, was also fetched live with
`--docket ABC-1234567 --client-ref REF-000123` to exercise a modern EP
publication; it produced a 206-paragraph valid `.docx` with the docket and
client reference in the running header.

### Final green check

```
$ python -m pytest -q && mypy && ruff check . && ruff format --check .
........................................................................ [ 36%]
........................................................................ [ 72%]
........................................................                 [100%]
200 passed in 1.42s
Success: no issues found in 21 source files
All checks passed!
40 files already formatted
```

---

## 5. Problems hit, and how they were resolved

### Four defects in the pre-existing `epo_ops.py`

The file existed untracked and never committed. Run against real responses it was
wrong in four ways:

1. **Claim counting.** It treated every `claim-text` entry as one claim. They are
   *lines*: EP0000001's German block has 11 entries for 10 claims because claim 4
   wrapped, and EP3000001 has 21 entries for 12 claims. Fixed by `_split_claims()`,
   which starts a new claim only on a numbered line.
2. **Inventor deduplication.** `_dedupe()` compared cleaned strings, which cannot
   collapse `BUSSE CLAUS-ADOLF` / `BUSSE CLAUS ADOLF` / `BUSSE, CLAUS ADOLF, DR.`
   — the same person under three data formats. EP0000001 would have listed three
   inventors. Replaced by selecting the `epodoc` data format.
3. **Wrong publication.** `parse_biblio` took `documents[0]`. `EP0000001` returns
   the A1 and the B1, whose titles differ (`Thermal heat pump` vs
   `THERMAL HEAT PUMP`) and whose full text differs. Fixed by matching the kind
   code from the requested number.
4. **No text cleanup.** Paragraph text kept its `[0001]` markers (which the
   renderer's numbered list would then duplicate), its HTML entities, and its
   `<img/>` placeholders (producing paragraphs of pure markup). Fixed by
   `_clean()`.

### The global `ValueError` handler in the Flask app

An uncommitted change registered `@app.errorhandler(ValueError)` on the whole
application. That catches *every* `ValueError` raised anywhere in a request, so
an unrelated bug in the renderer or the domain would have been reported to the
user as "Configuration error". Replaced with a `try/except ValueError` around the
`service()` call, which is the only place `build_sources` runs — the same shape
the CLI already uses. Behaviour for the real case is unchanged: still HTTP 500,
still the configuration message, now covered by a test.

### Contradictions and corrections to CLAUDE.md

CLAUDE.md's OPS findings were accurate as far as they went. Everything it stated
was re-confirmed against live OPS this session: the epodoc reference rule, the
US full-text refusal, the `"$"`/`"@"` JSON shape, and German-first ordering. Two
of its statements needed **qualifying** rather than correcting, and one line was
stale:

- **"Claims and description are returned per language with German first for EP"** —
  true, but incomplete in a way that matters. Some EP documents have no English
  variant at all. `EP3000001` serves English claims and a **French-only**
  description; the language list there is DE/FR/EN for claims and FR alone for
  description. "Select English explicitly" is therefore not always satisfiable,
  and the source needs a defined fallback (see §6).
- **"Fixtures saved in `tests/fixtures/epo_EP0000001_*.json`"** — those fixtures
  are unsuitable as the primary test data. **EP0000001's English claims block is
  a corrupt OCR dump**: a single 752-character run of the front-page
  bibliographic data (`..BECH......FRGB........NLSE...` and so on), not claims.
  The German block is fine. This is OPS's data, not a parsing bug — it is a 1978
  document. The consequence is that `fetch EP0000001A1` produces a document whose
  single "claim" is that dump. It is visible in the generated `.docx`. For this
  reason `EP3000001` was captured as an additional fixture and is the one the
  claim tests use; EP0000001 is kept for the quirks it uniquely exhibits.
- **"Not started: … screenshots for the README"** — stale. `docs/images/form.png`
  and `docs/images/result.png` exist and are already referenced. Removed from
  CLAUDE.md.

### Unheaded descriptions

Both EP fixtures — and, as far as the probing went, EP full text generally — have
**no headings at all**. OPS `text-only` full text carries no markup for them, and
neither document uses upper-case heading paragraphs. `SectionMapper` therefore has
nothing to split on, its documented policy sends pre-heading content to
`BACKGROUND`, and the whole description lands there. `detailed_description` comes
back empty and the retrieval service reports the document as incomplete.

This is a genuine limitation, not a defect, and it was left alone deliberately:
guessing at section boundaries with a heuristic over unheaded prose would be
unreliable and would put presentation logic in the source. It is documented in
the README and in CLAUDE.md, and the user sees the warning on every EPO
retrieval.

### Shell environment

`python` is not on `PATH` in a non-interactive shell here; `.venv/bin/python` was
used throughout. The CLI was exercised with `.venv/bin` prepended to `PATH`. As
CLAUDE.md records, the editable install does not work on this machine, so
`python -m pip install . -q` was re-run before each end-to-end verification.

---

## 6. Design decisions

**Non-English full text is used, with a warning, rather than discarded.**
When a document has no English claims or description, the source uses the first
available language and logs at `WARNING` — which is the default log level, so it
shows without `-v`. The alternative was to treat "no English" as absent and
return nothing, which for `EP3000001` would have thrown away all 174 description
paragraphs and produced a nearly empty document. This tool prepares input for a
translation step, so foreign-language text is usable; silently mixing languages
is the real risk, and the warning is what addresses it. `PatentDocument` has no
language field, and adding one would be a domain change beyond this task.

**The US country limitation is discovered from the API, not hard-coded.**
`fetch()` could short-circuit on `country_code(number) == "US"` and skip the
network entirely, saving one request per US patent. It does not. Hard-coding
"OPS serves EP and WO only" would go stale silently if OPS ever adds countries,
and the cost is one wasted `biblio` request on a source that is not first in the
chain for US patents anyway. The live 404 is the authority.

**Inventors come from the `epodoc` data format, not from string deduplication.**
`epodoc` is OPS's canonical normalized form and yields exactly one entry per
person. The fallback to all entries only fires for documents that have no epodoc
parties at all.

**Claim boundaries are found by the number prefix, not by element structure.**
OPS nests all lines of all claims under a single `claim` element for both
fixtures, so structure carries no information. The regex requires a space after
the dot so a continuation line beginning `"10.5 cm"` cannot be mistaken for claim
10 — tested explicitly.

**Only `<img>` is stripped, not all angle-bracket markup.** `T <2>` and `Q <o>`
are literal subscript text in `text-only` full text. A general tag-stripper would
silently delete them and corrupt the physics in the description. Tested by
asserting `Q <2>` survives.

**Claims are fetched before the description.** Both fail identically for a
country OPS will not serve full text for, but the claims response is the smaller
one, so failing there wastes less.

**The registry names the missing variable.** `"epo_ops is configured but
EPO_OPS_SECRET is not set"` rather than listing both, because listing both is
actively unhelpful when one is set and the other is mistyped.

**`_prefer_english` was kept as a thin wrapper over `_english_or_first`.** Biblio
parsing does not care which language it got — a title has no fallback problem
worth reporting — so it keeps the simpler call, and only full-text parsing takes
the language back.

---

## 7. Known limitations and unfinished work

### Limitations of the EPO OPS source

- **No US full text.** OPS serves US bibliographic data but answers
  `CLIENT.InvalidCountryCode` for US claims and description. US patents fail on
  this source by design and rely on Google Patents. Documented in the README.
- **Everything lands in `BACKGROUND`.** OPS text-only full text has no headings,
  so EPO-sourced documents are always reported as missing
  `detailed_description`. See §5.
- **English is not guaranteed.** Some documents have no English claims or
  description; the source substitutes another language and warns.
- **EP0000001's English claims are a corrupt OCR dump in OPS itself.** The
  generated document for that number contains it. Nothing in this codebase can
  fix that, and detecting "this text is not really claims" generically would be
  guesswork.
- **Abstract figure reference is never set.** Google Patents supplies
  `abstract_figure_reference` (the trailing `Fig.1.` the output format wants);
  OPS abstracts do not carry one, so EPO-sourced documents omit it rather than
  invent it.
- **No family or search support.** Only the three `published-data/publication`
  endpoints are used. CLAUDE.md records that `/search` times out at 20 s on the
  non-paying tier; it was not attempted.
- **Free-tier quota is untested under load.** 403 and 429 are mapped to
  `SourceUnavailableError` from mocked responses, not from a real throttling
  event.
- **`fetch` is not retried.** A transient 5xx fails the source and moves the
  chain along. There is no backoff.
- **One token per source instance.** The registry builds a fresh `EpoOpsSource`
  per request in the web interface, so the web UI re-authenticates on every
  retrieval. The CLI, which builds once, does not.

### Unfinished in the project

- **The technical documentation `.docx`** is not started — deliberately out of
  scope for this session, as instructed.
- **The output template remains US-specific.** EP and WO patents render into a
  document headed `UNITED STATES LETTERS PATENT`. Pre-existing; unchanged.
- **The web result cache is in-process.** Pre-existing; unchanged.
