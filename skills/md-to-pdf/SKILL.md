---
name: md-to-pdf
description: Build a PDF from Markdown — one file, or several combined into one manual with a cover page, contents, numbered sections, and page numbers. Use when asked to convert Markdown to PDF, regenerate a user guide, or produce a manual or printable document from .md files.
---

Convert one or more Markdown files to a PDF. Several inputs become one document,
each starting on a new page, in the order given.

## Tooling

    python3 ~/.claude/skills/md-to-pdf/build.py OUT.pdf IN.md [IN2.md ...] [options]

`--help` lists every flag and is the source of truth for them; it runs without
installing anything.

Invoke it exactly as spelled above — the form is load-bearing. `settings.json`
carries an allow rule per command name, and Bash permission rules are literal
string matches: `~` is **not** expanded for them (home-relative expansion is
documented only for Read/Edit/Cd path patterns). An absolute path, `$HOME/…`, or
a `cd`-then-relative form all stop matching and turn a silent run into a
permission prompt.

If `python3` prints a Microsoft Store advert instead of running, that is
Windows' app-execution-alias stub standing in for a Python that isn't there — use
`python`, or `py`. Both have their own allow rule.

## First run

The first run on a given interpreter installs `markdown` and `xhtml2pdf` into
`_deps/` beside the script: roughly a minute and 70 MB, announced before it
starts. Later runs take about three seconds. The tree is rebuilt automatically
if the interpreter changes or a package goes missing, so a failed install is
never cached — nothing needs installing by hand, and `_deps/` is gitignored.

## What the defaults decide

- **Contents** — on for several inputs, off for one. `--toc`/`--no-toc` override.
  Built from the rendered PDF's outline over repeated renders, because a page
  number is only known once the page exists. The numbers are right once those
  renders agree; if they don't, a warning says so on stderr and some may be off
  by a page. A long contents flows onto a second page. A document with no
  headings gets no contents, with a note on stderr.
- **Cover page** — appears only if `--title`, `--subtitle`, or `--date` is given.
  It carries no footer.
- **Section numbering** — `--number-sections` numbers from the shallowest
  heading level present, or one level deeper when that level occurs exactly
  once. So a document whose single H1 is its title gets its H2s numbered `1`,
  `2`, `3` and its title left alone, while several files each with an H1 get
  numbered at H1. `--number-from-level N` forces the level and implies
  `--number-sections`.
- **Page size** — Letter. `--page-size a4` recomputes all frame geometry.
- **Render timeout** — 120 seconds per render pass (the document is rendered up
  to 4 times to settle contents page numbers). `--timeout N` raises or lowers it.
  On expiry the build fails naming the flag, with no partial output file left
  behind. This is a wall-clock ceiling on the whole render, not a per-element
  one — it cannot interrupt a hang inside a C extension, only inside Python.
- **Structural repair** — a list written with no blank line before it renders,
  in GitHub and most other Markdown tools, as a list; python-markdown instead
  renders it as one run-on paragraph, with no error. The build detects this
  from its own rendered output and inserts the missing blank line in memory
  (never touching the source file on disk), reporting each fix on stderr with
  file and line. `--no-fix-structure` reports without repairing. A fenced code
  block glued to preceding text is reported the same way but never repaired —
  inserting a blank line there is at least as likely to be splitting a fence
  that is really just mis-indented inside a list item, which would corrupt the
  list's numbering instead of fixing anything.

## Diagrams from source

A Markdown image reference to a `.puml`, `.plantuml`, or `.iuml` file is
treated as a diagram, not a picture:

- If `plantuml` is on `PATH` and new enough to enforce
  `PLANTUML_SECURITY_PROFILE=SANDBOX` (see below), the diagram is rendered from
  that source on every build (cached by content hash, so an unchanged diagram
  costs nothing on a rebuild). This path needs a `plantuml` install to
  exercise at all.
- Otherwise — no `plantuml` on `PATH`, or one too old to sandbox — the build
  looks for a pre-rendered `<name>.svg` or `<name>.png` next to the source and
  uses it, but only if it carries a recorded hash of the source it was
  rendered from, checked against the source's current content. A missing or
  mismatched hash fails the build, naming both files. This is what keeps a
  diagram from silently drifting out of sync with its source, since a diagram
  exported once and never regenerated is easy to forget about.
- A pre-existing `.svg` that predates this check has no hash yet. Confirm by
  eye that it currently matches its `.puml`, then bless it once:
  `python3 build.py --stamp-diagram SIBLING.svg SOURCE.puml` (a standalone mode,
  not a build — it does not appear in `--help` and takes no other flags).
  Re-run it whenever the source changes and the sibling is manually
  regenerated to match.
- Either way, the diagram is wrapped in a captioned figure using the Markdown
  alt text (`![Sample pipeline](...)`  →  a "Sample pipeline" caption below
  it), and sized to fill the page's content frame. An SVG diagram renders as
  native vector content — confirmed by inspecting the produced PDF's own
  content stream, not assumed — so there is no resolution to run out of at any
  fitted size; only a raster PNG sibling has a real ceiling, at its own pixel
  count.
- `plantuml` is invoked with `PLANTUML_SECURITY_PROFILE=SANDBOX` (as an
  environment variable — PlantUML's `-D` system-property form of this flag is a
  known no-op, plantuml/plantuml#1450), since a `.puml` can otherwise use
  `!include`/`!includeurl` to read local files or reach the network at render
  time. Support for the env var itself was added in PlantUML 1.2020.11; an
  older `plantuml` accepts it and enforces nothing, so the build checks
  `plantuml -version` first and, if it's too old, falls back to the
  hash-verified sibling path above rather than rendering unsandboxed — a
  sibling never executes the `.puml`, so this can't reopen what the check
  exists to close. Only when there's no usable sibling either does the build
  fail, naming the reason. Upgrading `plantuml` is the only way to render
  from source on a machine whose install is this old.
- The render cache lives in `_diagrams/` beside `_deps/` and is gitignored,
  same as `_deps/`.

## Limits worth knowing before you build

- **`--css` cannot set `@page`.** Any `@page` rule in the file is dropped with a
  note, because a second one replaces the built-in template rather than merging
  with it, taking the footer frame with it. Element rules work normally and
  override the built-in stylesheet. Use `--page-size` for page geometry.
- **A table over 10 rows may split across a page break.** xhtml2pdf does not
  actually implement `page-break-after`/`page-break-before: avoid` (only
  `always`, `right`, `left` — confirmed by reading its parser) or
  `page-break-inside`, so the only real page-break control it has is
  `-pdf-keep-with-next`, used here on headings, on a figure's image (to hold
  it with its caption), and per-table on a table of 10 rows or fewer. A larger
  table carries no such protection: forcing it on any table hangs for minutes
  on a real document (measured: over 90 seconds on a 60-row table, where the
  same document renders in under 4 seconds without it) — a rare split table on
  a large one is a far smaller cost than that.
- **Images are resolved per source file**, against that file's own directory, so
  inputs from different folders each keep their own relative paths working. A
  missing image is a hard error naming both the reference and the resolved path;
  an unreadable one fails the build rather than vanishing from the page.
- **`http(s)` image URLs are fetched at build time.** Local files are the norm;
  a remote one means the build makes a network request.
- **Tables using `colspan` or `rowspan` keep xhtml2pdf's equal column widths.**
  Every other table gets widths sized to its own content.
- Headings become PDF bookmarks automatically.

`result.err`, xhtml2pdf's nominal error count, is **always zero** in 0.2.17 — it
never increments, so it is not a failure signal. Content loss is reported only
to the logger, and at WARNING level: a dropped image logs "Cannot
identify image file" and is otherwise silent. `build.py` captures the
`xhtml2pdf`, `svglib.svglib`, and `reportlab` loggers and fails on anything any
of them emits, which is why a healthy build prints nothing but `Wrote …`. Any
other code driving xhtml2pdf needs the same treatment.
