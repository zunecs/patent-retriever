# Output format specification

The exact structure and formatting the generated `.docx` must follow.

Source: measured directly from a real sample document in Word, July 2026.
Values marked *(assumed)* are not yet confirmed.

---

## Page setup

| Property | Value |
|---|---|
| Top margin | 1.2" |
| Bottom margin | 1" |
| Left margin | 1" |
| Right margin | 1" |
| Gutter | 0", position left |
| Orientation | Portrait |

## Default (Normal) style

| Property | Value |
|---|---|
| Font | Times New Roman |
| Size | 13 pt |
| Line spacing | 1.5 lines |
| Space before | 0 pt |
| Space after | 6 pt |
| Body alignment | Justified |

---

## Running page header

Repeats at the top of **every** page. Right-aligned, single-spaced, 0 pt
before and after.

```
PATENT APPLICATION
ATTORNEY DOCKET NO. [Docket Number]
CLIENT REF. NO. [Client Reference]
```

The docket number and client reference are internal values. No patent source
supplies them; they are provided per rendering job.

---

## Page 1 — cover

Four empty paragraphs, then:

```
APPLICATION
FOR
UNITED STATES LETTERS PATENT
```

18 pt, bold, centred, each on its own line. Then three empty paragraphs:

```
TITLE:<tab><tab>[Full Title]

INVENTOR:<tab>[Full Inventor Name]
```

Both label lines are 14 pt bold. Multiple inventors are comma-separated
*(assumed — a sample with several inventors has not been checked)*.

A page break follows.

---

## Page 2 onward — body

The title is repeated, 14 pt bold, centred, followed by one empty paragraph.

### Section headings

`BACKGROUND`, `SUMMARY`, `BRIEF DESCRIPTION OF DRAWINGS`, `DETAILED DESCRIPTION`

All uppercase, centred, 13 pt, not bold. **No empty paragraph separates a
heading from its first paragraph.**

Sections with no content are omitted entirely, heading included.

### Numbered paragraphs

Paragraph IDs are a **genuine Word numbered list**, not literal text.

| Property | Value |
|---|---|
| Number format | Custom, `0001, 0002, 0003, ...` |
| Level text | `[%1]` |
| Start at | 1 |
| Number position | 0.44" |
| Text indent | 1.04" |
| Follow number with | Tab character |

Numbering runs continuously across all four body sections and does not reset.

Word's built-in numbering formats cannot pad to four digits, so the renderer
injects a `<w:numFmt w:val="custom" w:format="0001, 0002, 0003, ..."/>`
definition into `numbering.xml` directly.

---

## CLAIMS

Heading `CLAIMS`, centred, 13 pt. Then:

```
What is claimed:

1. [claim text]
2. [claim text]
```

Claim numbers are **literal text**, not list numbering *(assumed — confirmed
only that the numbers survive plain-text extraction, which list numbering
would not)*. Numbering starts at 1 and does not reset. Each claim is a single
paragraph regardless of internal line breaks.

Dependent claims reference their parent as `The [subject] of claim [number], ...`

---

## ABSTRACT

Heading `ABSTRACT`, centred, **14 pt, bold** — unlike the other section
headings.

A single paragraph, typically 150 words or fewer, closing the document.
The last line is a figure reference written exactly:

```
Fig.1.
```

Capital F, no space after `Fig.`, trailing period.

---

## Still to confirm

- Whether section headings are bold (currently rendered not bold)
- Whether claim numbers are literal text or a second Word list
- Header alignment for documents with a long docket number
- Multiple inventors: comma-separated on one line, or one per line
- Non-US patents: does `UNITED STATES LETTERS PATENT` change