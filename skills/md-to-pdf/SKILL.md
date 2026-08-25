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

## Limits worth knowing before you build

- **`--css` cannot set `@page`.** Any `@page` rule in the file is dropped with a
  note, because a second one replaces the built-in template rather than merging
  with it, taking the footer frame with it. Element rules work normally and
  override the built-in stylesheet. Use `--page-size` for page geometry.
- **Images are resolved per source file**, against that file's own directory, so
  inputs from different folders each keep their own relative paths working. A
  missing image is a hard error naming both the reference and the resolved path;
  an unreadable one fails the build rather than vanishing from the page.
- **`http(s)` image URLs are fetched at build time.** Local files are the norm;
  a remote one means the build makes a network request.
- **Tables using `colspan` or `rowspan` keep xhtml2pdf's equal column widths.**
  Every other table gets widths sized to its own content.
- SVG images work, via svglib's vector path.
- Headings become PDF bookmarks automatically.

`result.err`, xhtml2pdf's nominal error count, is **always zero** in 0.2.17 — it
never increments, so it is not a failure signal. Content loss is reported only
to the `xhtml2pdf` logger, and at WARNING level: a dropped image logs "Cannot
identify image file" and is otherwise silent. `build.py` captures that logger and
fails on anything it emits, which is why a healthy build prints nothing but
`Wrote …`. Any other code driving xhtml2pdf needs the same treatment.
