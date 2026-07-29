# Output format specification — Aramco Patent Translation tool input

This is the exact structure the generated `.docx` must follow.
Source: format spec provided by the Law/legal solutions team.

Status of this spec: **logical structure is confirmed. Visual formatting
(font family, size, margins, line spacing, heading bold/centering, page
numbering) is NOT specified and remains an open question.**

---

## 1. Header / metadata block

Very top of the document. Fixed labels followed by values, separated by
line breaks. **No paragraph numbering in this block.**

```
PATENT APPLICATION    ATTORNEY DOCKET NO. [Docket Number]    CLIENT REF. NO. [Client Reference]
APPLICATION FOR UNITED STATES LETTERS PATENT

TITLE:

[Full Title]

INVENTOR:

[Full Inventor Name]

[Full Title]
```

The title repeats immediately after the inventor line, preserving exact
capitalization and line breaks.

---

## 2. BACKGROUND

- Heading: `BACKGROUND` — all uppercase, standalone line
- Placement: immediately follows a blank line after the header/title repetition
- Numbering: sequential bracketed IDs starting at `[0001]`
- Format: each paragraph begins with `[XXXX]` (four digits, zero-padded),
  then a single space, then the text
- No bullet points or sub-headers inside this section

---

## 3. SUMMARY

- Heading: `SUMMARY` — all uppercase, standalone line
- Placement: preceded by one blank line
- Numbering: continues sequentially from BACKGROUND (e.g. `[0004]`, `[0005]`)
- Typically contains independent method, system, and apparatus paragraphs,
  each starting a new numbered block

---

## 4. BRIEF DESCRIPTION OF DRAWINGS

- Heading: `BRIEF DESCRIPTION OF DRAWINGS` — all uppercase, standalone line
- Placement: preceded by one blank line
- Numbering: continues sequentially
- Paragraphs describe figure references (e.g. `FIG. 1 shows...`,
  `FIGs. 3A-3E show...`). Each reference gets its own `[XXXX]` block.

---

## 5. DETAILED DESCRIPTION

- Heading: `DETAILED DESCRIPTION` — all uppercase, standalone line
- Placement: preceded by one blank line
- Numbering: continues sequentially
- Largest portion of the document
- References figures using `FIG. X`
- Uses parenthetical reference numerals for components, e.g. `(100)`, `(101)`
- No structural sub-headings — all content flows as sequential numbered paragraphs

---

## 6. CLAIMS

- Heading: `CLAIMS` — all uppercase, standalone line
- Sub-heading: `What is claimed:` — appears immediately after a blank line
  under the heading
- Numbering: **switches from bracketed IDs to standard numeric listing.**
  Starts at `1.`, then `2.`, `3.`, etc.
- Independent claims start with a capital letter and define the core invention
- Dependent claims reference parent claims using the pattern:
  `The [subject] of claim [number], ...`
- Each claim is a single paragraph block, regardless of line breaks used for
  readability
- Numbering is continuous and does not reset or use bracketed IDs

---

## 7. ABSTRACT

- Heading: `ABSTRACT` — all uppercase, standalone line
- Placement: at the very end of the document body, after CLAIMS
- Numbering: none (unnumbered block)
- Single paragraph summarizing the invention, typically 150 words or fewer
- Concludes with a brief figure reference on its own line, formatted exactly
  as `Fig. 1.` — capital "Fig", period after the number, no space before the period

---

## Structural rules

1. **Section splitting** — use the exact heading strings as primary split
   points: `BACKGROUND`, `SUMMARY`, `BRIEF DESCRIPTION OF DRAWINGS`,
   `DETAILED DESCRIPTION`, `CLAIMS`, `ABSTRACT`
2. **Paragraph anchors** — in the body (BACKGROUND through DETAILED
   DESCRIPTION), paragraph blocks match the regex `\[\d{4}\]\s`
3. **Claims parsing** — switch to a numeric list parser once `CLAIMS` and
   `What is claimed:` are detected. Each `N.` prefix is a claim boundary.
4. **Whitespace** — exactly one blank line between sections. Do not insert
   or remove paragraph spacing within blocks.
5. **Case and punctuation** — headings strictly uppercase; paragraph IDs are
   four-digit zero-padded in brackets; the abstract figure reference uses
   `Fig.` in title case followed immediately by the number and a period.

---

## Open questions to resolve with the team

- Font family, size, margins, line spacing, alignment
- Are headings bold? Centered?
- Are `ATTORNEY DOCKET NO.` and `CLIENT REF. NO.` required, or may they be
  left blank? These are internal values — no patent source provides them.
- Multiple inventors: one per line, or comma-separated on the `INVENTOR:` line?
- Non-US patents: does the line `APPLICATION FOR UNITED STATES LETTERS PATENT`
  change, or stay fixed?
- If a source patent has no BRIEF DESCRIPTION OF DRAWINGS section, is the
  heading omitted or emitted empty?
