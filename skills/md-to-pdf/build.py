"""Build a PDF from one or more Markdown files.

    python3 build.py OUT.pdf IN.md [IN2.md ...] [options]

Several inputs are concatenated into one document, each starting on a new page.
Run with --help for the full option list.

Pipeline: python-markdown -> HTML -> xhtml2pdf (pisa) -> reportlab. Pure Python;
no pandoc, no LaTeX, no system binaries. Dependencies install on first run into
_deps/ beside this file (see _ensure_deps).

Everything above the "third-party" line uses only the standard library and must
parse on Python 3.8, because this file has to be loadable by whatever interpreter
launches it before it can repair its own import path.
"""

import argparse
import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEPS_DIR = SKILL_DIR / "_deps"
FONT_DIR_DEFAULT = SKILL_DIR / "fonts"

# Pinned to a compatible range so every synced machine resolves the same majors.
# The stamp hashes this list, so editing it forces a rebuild.
DEPS = ["markdown>=3.5,<4", "xhtml2pdf>=0.2.17,<0.3"]

# Top-level packages that must be present for a _deps tree to count as usable.
# pypdf arrives with xhtml2pdf and is what reads back the outline for the
# contents listing, so it belongs in the check.
DEP_PACKAGES = ["markdown", "xhtml2pdf", "reportlab", "pypdf"]

# Points. reportlab's native unit, so all geometry stays in one system.
PAGE_SIZES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
MARGIN = 28.8  # 0.4in
FOOTER_H = 16.0
FOOTER_GAP = 6.0

# Anything but "body", which xhtml2pdf reserves for the first-installed template.
CONTENT_TEMPLATE = "main"

FONT_FILES = {
    "DejaVuSans": "DejaVuSans.ttf",
    "DejaVuSans-Bold": "DejaVuSans-Bold.ttf",
    "DejaVuSans-Oblique": "DejaVuSans-Oblique.ttf",
    "DejaVuSansMono": "DejaVuSansMono.ttf",
}


def _fail(message):
    sys.exit("md-to-pdf: " + message)


# --------------------------------------------------------------------------
# Dependency bootstrap
# --------------------------------------------------------------------------


def _stamp_text():
    """Identity of a usable _deps tree: interpreter ABI, platform, dep list.

    A C extension built for one CPython minor version will not import on
    another, so the interpreter version belongs in the identity rather than
    just the dep list.
    """
    digest = hashlib.sha256("\n".join(DEPS).encode()).hexdigest()[:16]
    return "py{}.{} {} {}\n".format(
        sys.version_info[0], sys.version_info[1], sys.platform, digest
    )


def _swap_in(tmp_dir, dest_dir):
    """Move tmp_dir onto dest_dir.

    os.replace refuses a non-empty destination directory, and on Windows a
    loaded .pyd in the old tree cannot be deleted at all, so the old tree is
    renamed aside first and only then removed - a rename succeeds while the
    files are held open, a delete does not.
    """
    if dest_dir.exists():
        stale = dest_dir.with_name("{}.old.{}".format(dest_dir.name, os.getpid()))
        os.replace(str(dest_dir), str(stale))
        shutil.rmtree(str(stale), ignore_errors=True)
    os.replace(str(tmp_dir), str(dest_dir))


def _ensure_deps():
    """Make DEPS importable, installing them on first run.

    Installs to a temp directory and moves it into place only after the packages
    import cleanly, so an interrupted or partial install cannot leave behind a
    tree that looks complete and then fails on every later run.
    """
    stamp = DEPS_DIR / ".stamp"
    if stamp.is_file() and stamp.read_text() == _stamp_text():
        # The stamp records what was installed; it says nothing about what is
        # still there. Checking the packages exist costs a few stats and turns a
        # later ModuleNotFoundError into a rebuild.
        gone = [p for p in DEP_PACKAGES if not (DEPS_DIR / p).is_dir()]
        if not gone:
            sys.path.insert(0, str(DEPS_DIR))
            return
        print("md-to-pdf: dependency tree is incomplete ({} missing) - rebuilding".format(
            ", ".join(gone)
        ))

    # Per-process temp name so two concurrent first runs cannot delete each
    # other's in-flight install.
    tmp_dir = SKILL_DIR / "_deps.tmp.{}".format(os.getpid())
    shutil.rmtree(str(tmp_dir), ignore_errors=True)

    # ASCII only, and flushed: some consoles cannot encode non-ASCII, and pip
    # writes straight to the terminal, so an unflushed banner lands after it.
    print("md-to-pdf: first run on this interpreter - installing dependencies")
    print("  target: {}".format(DEPS_DIR))
    print("  this downloads roughly 70 MB and takes a minute.\n", flush=True)

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", str(tmp_dir),
        "--disable-pip-version-check",
        "--no-warn-script-location",
    ] + DEPS
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        _fail(
            "this Python has no pip.\n"
            "  Install it (Debian/Ubuntu: apt install python3-pip; otherwise:\n"
            "  {} -m ensurepip --upgrade) and re-run.".format(sys.executable)
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        _fail(
            "dependency install failed (pip exit {}). pip's own output is above.\n"
            "  To install by hand:\n    {}".format(exc.returncode, " ".join(cmd))
        )

    # Verify in a subprocess, not in-process: importing here would leave
    # sys.modules holding packages whose __path__ points into the temp
    # directory, which the move below then invalidates.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_dir)
    # PYTHONHOME would send the child to a different stdlib and make this fail
    # for reasons that have nothing to do with the install.
    env.pop("PYTHONHOME", None)
    check = subprocess.run(
        [sys.executable, "-c", "import " + ", ".join(DEP_PACKAGES) + ", xhtml2pdf.pisa"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if check.returncode:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        _fail(
            "install completed but packages will not import:\n{}".format(
                check.stdout.decode("utf-8", "replace")
            )
        )

    (tmp_dir / ".stamp").write_text(_stamp_text())
    try:
        _swap_in(tmp_dir, DEPS_DIR)
    except OSError as exc:
        _fail(
            "could not replace {}: {}\n"
            "  Another build may be running. Remove the directory and re-run.".format(
                DEPS_DIR, exc
            )
        )
    sys.path.insert(0, str(DEPS_DIR))
    print("\nmd-to-pdf: dependencies ready.\n")


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------


def _page_css(page_size, want_cover, want_footer):
    """@page templates with explicit frames.

    A repeating footer requires -pdf-frame-content, which only exists inside an
    @frame, so page numbers force the whole document onto explicit frames rather
    than a plain margin. Every rectangle derives from the page box, so a
    different --page-size needs no other change.

    Template naming is load-bearing, not cosmetic. An unnamed @page is stored
    under the name "body" (`context.py`, `name = name or "body"`), and
    `document.py` always installs the template called "body" first, which makes
    it page 1's. So the page the document opens on must be the unnamed rule, and
    the other template needs a name that is not "body" - naming both leaves one
    silently overwriting the other.
    """
    width, height = PAGE_SIZES[page_size]
    inner_w = width - 2 * MARGIN
    full_h = height - 2 * MARGIN
    body_h = full_h - (FOOTER_H + FOOTER_GAP) if want_footer else full_h
    size = "{:.2f}pt {:.2f}pt".format(width, height)

    footer_frame = ""
    if want_footer:
        footer_frame = """
    @frame footer_frame {{
        -pdf-frame-content: footer_content;
        left: {m:.2f}pt; top: {top:.2f}pt; width: {w:.2f}pt; height: {fh:.2f}pt;
    }}""".format(m=MARGIN, top=MARGIN + body_h + FOOTER_GAP, w=inner_w, fh=FOOTER_H)

    body = """
@page {name} {{
    size: {size};
    @frame content_frame {{ left: {m:.2f}pt; top: {m:.2f}pt; width: {w:.2f}pt; height: {h:.2f}pt; }}{footer}
}}""".format(
        name=CONTENT_TEMPLATE if want_cover else "",
        size=size, m=MARGIN, w=inner_w, h=body_h, footer=footer_frame,
    )

    if not want_cover:
        return body

    cover = """
@page {{
    size: {size};
    @frame cover_frame {{ left: {m:.2f}pt; top: {m:.2f}pt; width: {w:.2f}pt; height: {h:.2f}pt; }}
}}""".format(size=size, m=MARGIN, w=inner_w, h=full_h)
    return cover + body


BASE_CSS = """
body { font-family: "DejaVuSans", sans-serif; font-size: 10pt; line-height: 1.4; }
h1, h2, h3 { font-weight: normal; }
h1 { font-size: 26pt; margin-top: 0; border-bottom: 2px solid #000; padding-bottom: 10pt; }
/* -pdf-keep-with-next avoids orphaning a heading at the bottom of a page when
   the content right after it (often a screenshot) doesn't fit and flows to
   the next page instead. */
h2 { font-size: 16pt; margin-top: 22pt; page-break-after: avoid; -pdf-keep-with-next: true; }
h3 { font-size: 13pt; margin-top: 16pt; page-break-after: avoid; -pdf-keep-with-next: true; }
/* page-break-inside:avoid alone isn't enough for xhtml2pdf to keep a table
   from splitting once it's underway — -pdf-keep-with-next is what actually
   forces the whole table to move to the next page as one unit. */
table { border-collapse: collapse; table-layout: fixed; width: 100%; margin: 10pt 0; page-break-inside: avoid; -pdf-keep-with-next: true; }
th, td { border: none; border-bottom: 1px solid #999; padding: 4pt 10pt; text-align: left; font-size: 10pt; word-wrap: break-word; }
th { font-weight: bold; border-bottom: 2px solid #000; }
code { color: #c8ae74; font-family: "DejaVuSansMono", monospace; font-size: 11pt; }
pre { background-color: #f2f2f2; padding: 6pt; font-family: "DejaVuSansMono", monospace; font-size: 8pt; }
img { max-width: 100%; margin: 8pt 0; }
hr { border: none; border-top: 2px solid #000; margin: 20pt 0; }

#footer_content { text-align: center; font-size: 8pt; color: #666; }

.cover { text-align: center; }
.cover-title { font-size: 32pt; margin-top: 220pt; }
.cover-subtitle { font-size: 18pt; color: #444; margin-top: 12pt; }
.cover-date { font-size: 11pt; color: #666; margin-top: 30pt; }

.toc-head { font-size: 20pt; margin-bottom: 14pt; border-bottom: 2px solid #000; padding-bottom: 8pt; }
/* The shared table rules keep a table whole on one page; a contents listing is
   the one table that must be free to run over as many pages as it needs. */
table.toc { page-break-inside: auto; -pdf-keep-with-next: false; margin: 0; }
table.toc td { border-bottom: none; padding: 2pt 0; }
td.toc-p { width: 8%; text-align: right; }
td.toc-t { width: 92%; }
td.toc-l0 { font-size: 11pt; padding-top: 7pt; }
td.toc-l1 { font-size: 10pt; padding-left: 18pt; }
td.toc-l2 { font-size: 9pt; padding-left: 36pt; color: #444; }
"""


def _strip_at_page(css, source):
    """Remove @page blocks from user CSS, brace-matched.

    A second @page is not merged with the built-in one, it replaces it: the
    unnamed rule collides on the name "body", the surviving rule declares no
    frames, and the footer disappears from a document that asked for page
    numbers. Element rules are unaffected and still override, which is what
    --css is for.

    Comments are blanked (kept as same-length whitespace, so later offsets
    still line up with the original string) before hunting for "@page" -
    otherwise the literal text "@page" inside a comment is found, and the
    brace matcher then grabs the *next* real rule's braces and deletes it
    instead of the nonexistent at-rule the comment merely mentioned.
    """
    masked = re.sub(
        r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), css, flags=re.S
    )
    out, i, dropped = [], 0, 0
    while True:
        m = re.compile(r"@page\b", re.I).search(masked, i)
        if not m:
            out.append(css[i:])
            break
        out.append(css[i:m.start()])
        brace = masked.find("{", m.end())
        if brace < 0:
            out.append(css[m.start():])
            break
        depth, j = 0, brace
        while j < len(masked):
            if masked[j] == "{":
                depth += 1
            elif masked[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1
        dropped += 1
    if dropped:
        print(
            "md-to-pdf: ignoring {} @page rule(s) in {} - they would replace the "
            "page template and drop the footer. Use --page-size instead.".format(
                dropped, source
            ),
            file=sys.stderr,
        )
    return "".join(out)


# --------------------------------------------------------------------------
# HTML transforms
# --------------------------------------------------------------------------

_HEADING_RE = re.compile(r"<h([1-6])(?:\s[^>]*)?>", re.I)


def _heading_levels(html):
    return [int(m) for m in _HEADING_RE.findall(html)]


def _pick_number_level(all_levels):
    """Shallowest heading level worth numbering.

    A level appearing exactly once is a document or section title, not a
    numbered peer, so numbering starts one level deeper. Without that, a guide
    whose single H1 is its title would number that title "1".
    """
    if not all_levels:
        return 1
    present = sorted(set(all_levels))
    shallowest = present[0]
    if all_levels.count(shallowest) == 1 and len(present) > 1:
        return present[1]
    return shallowest


def _number_headings(html, start_level, counters):
    """Prefix each heading at or below start_level with a dotted number.

    `counters` is carried across files so numbering runs continuously through a
    multi-file document. xhtml2pdf builds the outline from heading text at
    render time, so numbering the text here is all the contents listing needs.
    """

    def repl(match):
        level = int(match.group(1))
        if level < start_level:
            return match.group(0)
        idx = level - start_level
        # Levels the document skipped still need a component. They start at 1,
        # not 0, so a jump from H1 straight to H4 reads "1.1.1" rather than
        # "0.0.1".
        while len(counters) < idx:
            counters.append(1)
        if len(counters) == idx:
            counters.append(0)
        counters[idx] += 1
        del counters[idx + 1:]
        label = ".".join(str(c) for c in counters[: idx + 1])
        return "{}{} ".format(match.group(0), label)

    return _HEADING_RE.sub(repl, html)


_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
# The lookbehind keeps this off data-src and similar; `-` is a word boundary,
# so a bare \b would match them.
_SRC_ATTR_RE = re.compile(
    r"(?<![-\w])(src\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I
)
_REMOTE_RE = re.compile(r"^(https?:|data:)", re.I)


def _map_images(html, base_dir, assets):
    """Route every local <img src> through an opaque key served by link_callback.

    xhtml2pdf resolves a callback's return value as a filesystem path and skips
    URI parsing, which is the only reliable way to name a Windows path: put
    `C:\\...` straight into src and `C:` is read as a URI scheme. Keys are unique
    per document so inputs from different directories can each resolve their own
    relative paths.
    """
    from urllib.parse import unquote

    def fix_tag(tag_match):
        def fix_src(attr_match):
            lead, raw = attr_match.group(1), attr_match.group(2)
            quote = raw[0] if raw[:1] in ("\"", "'") else ""
            uri = raw[1:-1] if quote else raw
            if _REMOTE_RE.match(uri):
                return attr_match.group(0)
            # A percent-escaped space is the normal Markdown spelling of a path
            # with a space in it, and never a literal '%20' on disk.
            path = Path(unquote(uri))
            resolved = (path if path.is_absolute() else base_dir / path).resolve()
            if not resolved.is_file():
                _fail("image not found: {}\n  referenced as: {}".format(resolved, uri))
            key = "mdpdf-asset-{}".format(len(assets))
            assets[key] = str(resolved)
            return "{}{}{}{}".format(lead, quote or '"', key, quote or '"')

        return _SRC_ATTR_RE.sub(fix_src, tag_match.group(0), count=1)

    return _IMG_TAG_RE.sub(fix_tag, html)


MIN_COL_PCT = 15.0
_CODE_WEIGHT = 1.15
_TAG_RE = re.compile(r"<[^>]+>")


def _cell_text_width(cell_html):
    """Rough relative width of a cell's content, in "character units".

    Monospace inline code renders noticeably wider per character than the
    proportional body font at the same point size, so it is weighted up before
    being compared to plain text.
    """
    text = _TAG_RE.sub("", cell_html).strip()
    weight = _CODE_WEIGHT if "<code>" in cell_html else 1.0
    return len(text) * weight


def _distribute(widths):
    """Column percentages summing to 100, with a floor no column drops below.

    The floor is half the equal share, so it protects a narrow column without
    pinning every column to the same width once a table has enough of them.
    Raising a narrow column to the floor is paid for by scaling the columns
    above it, repeated until every column clears the floor.
    """
    n = len(widths)
    if n == 0:
        return []
    floor = min(MIN_COL_PCT, 100.0 / n * 0.5)
    total = sum(widths)
    if total <= 0:
        return [100.0 / n] * n
    pct = [w / total * 100.0 for w in widths]

    for _ in range(n):
        below = [i for i, p in enumerate(pct) if p < floor]
        if not below:
            break
        above = [i for i, p in enumerate(pct) if p > floor]
        headroom = sum(pct[i] - floor for i in above)
        deficit = sum(floor - pct[i] for i in below)
        if headroom <= 0 or deficit > headroom:
            return [100.0 / n] * n
        for i in below:
            pct[i] = floor
        for i in above:
            pct[i] -= deficit * (pct[i] - floor) / headroom
    return pct


_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<(th|td)(\b[^>]*)?>(.*?)</\1>", re.S | re.I)
_STYLE_RE = re.compile(r"(\bstyle\s*=\s*[\"'])", re.I)
_SPAN_RE = re.compile(r"\b(?:col|row)span\s*=", re.I)


def _size_table_columns(html):
    """Give every table's columns widths sized to their own contents.

    xhtml2pdf renders all columns equal-width unless the table is
    `table-layout: fixed` *and* carries explicit widths, so without this each
    table splits evenly regardless of how narrow its first column really is.
    Widths go on the cells: colgroup/col are ignored by xhtml2pdf's table
    layout, and `table-layout: fixed` sizes from the first row.

    Tables using colspan or rowspan are left alone - a per-cell width means
    nothing once cells span columns.
    """

    def size_table(table_match):
        table_html = table_match.group(0)
        # A non-greedy <table>...</table> stops at the *inner* closing tag of a
        # nested table, which would mix two tables' cells into one width
        # calculation.
        if "<table" in table_html[6:].lower() or _SPAN_RE.search(table_html):
            return table_html
        rows = [(m, _CELL_RE.findall(m.group(1))) for m in _ROW_RE.finditer(table_html)]
        rows = [(m, cells) for m, cells in rows if cells]
        if not rows:
            return table_html
        ncols = max(len(cells) for _, cells in rows)
        if ncols < 2:
            return table_html

        widths = []
        for col in range(ncols):
            widths.append(
                max(
                    (_cell_text_width(cells[col][2]) for _, cells in rows if len(cells) > col),
                    default=0.0,
                )
            )
        pct = _distribute(widths)

        def rewrite_row(row_match):
            inner = row_match.group(1)
            col = [0]

            def rewrite_cell(cell_match):
                tag, attrs, body = cell_match.group(1), cell_match.group(2) or "", cell_match.group(3)
                i = col[0]
                col[0] += 1
                if i >= ncols:
                    return cell_match.group(0)
                width = "width:{:.1f}%".format(pct[i])
                # Merge into an existing style rather than adding a second
                # attribute, which the parser would ignore. Either quote style
                # counts as existing.
                if _STYLE_RE.search(attrs):
                    attrs = _STYLE_RE.sub(r"\1" + width + ";", attrs, count=1)
                else:
                    attrs = '{} style="{}"'.format(attrs, width)
                return "<{}{}>{}</{}>".format(tag, attrs, body, tag)

            return row_match.group(0).replace(inner, _CELL_RE.sub(rewrite_cell, inner), 1)

        return _ROW_RE.sub(rewrite_row, table_html)

    return re.sub(r"<table\b.*?</table>", size_table, html, flags=re.S | re.I)


# --------------------------------------------------------------------------
# Document assembly
# --------------------------------------------------------------------------


# Warnings xhtml2pdf emits for input that is unusual but not broken - the
# resulting page just shows less than a "real" failure would suppress:
#   - spooling a remote or inline asset through a temp file (routine).
#   - a <table> with zero rows (raw HTML passthrough; a Markdown-syntax table
#     always synthesizes a row, so this is not reachable from ordinary
#     markdown.tables output, but raw HTML in the source can hit it).
_BENIGN_LOG = (
    "Created temporary file",
    "<table> is empty",
    "<table> rows seem to be inconsistent",
)


class _RenderErrors(logging.Handler):
    """Collects xhtml2pdf's WARNING-and-above records.

    xhtml2pdf 0.2.17 never calls `pisaContext.error`, so `result.err` is always
    0 - it is not a usable failure signal. Real content loss is reported only to
    the logger, and at WARNING: an unreadable image gives "Cannot identify image
    file" from xhtml2pdf.tags and is otherwise dropped in silence, leaving a
    "Wrote ..." for a PDF missing a figure. A healthy build logs nothing, so
    anything not on the benign list is treated as a failure.
    """

    def __init__(self):
        logging.Handler.__init__(self, level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        message = record.getMessage()
        if not any(b in message for b in _BENIGN_LOG):
            self.messages.append("{}: {}".format(record.name, message))


def _register_fonts(font_dir):
    """Make DejaVu usable from CSS.

    reportlab's built-in fonts are WinAnsi-only and lack both the Omega used in
    transfer-impedance units and the bullet character markdown lists render
    with; DejaVu covers both.

    Fonts are registered directly with reportlab instead of via CSS @font-face
    because xhtml2pdf's @font-face loader writes the font to a
    NamedTemporaryFile and hands reportlab the *path* while its own handle is
    still open - which Windows refuses, failing deep inside reportlab. And
    reportlab's registry is not the one xhtml2pdf consults for `font-family`:
    it keeps a separate CSS-name table (xhtml2pdf.default.DEFAULT_FONT), so the
    aliases have to be added there too.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from xhtml2pdf import default as pisa_default

    missing = [f for f in FONT_FILES.values() if not (font_dir / f).is_file()]
    if missing:
        _fail("missing font file(s) in {}: {}".format(font_dir, ", ".join(missing)))

    for name, filename in FONT_FILES.items():
        pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    pdfmetrics.registerFontFamily(
        "DejaVuSans",
        normal="DejaVuSans",
        bold="DejaVuSans-Bold",
        italic="DejaVuSans-Oblique",
        boldItalic="DejaVuSans-Bold",
    )
    pisa_default.DEFAULT_FONT.update(
        {
            "dejavusans": "DejaVuSans",
            "dejavusans-bold": "DejaVuSans-Bold",
            "dejavusans-oblique": "DejaVuSans-Oblique",
            "dejavusansmono": "DejaVuSansMono",
        }
    )


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_HEADING_FULL_RE = re.compile(r"<h([1-6])(?:\s[^>]*)?>(.*?)</h\1>", re.S | re.I)


def _extract_headings(html):
    """(outline-level, inner HTML) for every heading, in document order.

    outline-level is h-number minus 1 (h1->0 ... h6->5) - xhtml2pdf's own
    default UA stylesheet assigns exactly this via -pdf-outline-level
    (`default.py`, the h1..h6 block), and nothing in this pipeline overrides it.
    Knowing that mapping up front is what makes the contents listing exact
    rather than a heuristic guess at the rendered PDF's outline.
    """
    return [(int(m.group(1)) - 1, m.group(2)) for m in _HEADING_FULL_RE.finditer(html)]


def _outline_pages(pdf_path):
    """Page number of every PDF outline entry, in emission order.

    Titles and nesting depth are not read here - only order and page. Title
    text is unusable as a structural signal: when a document skips an outline
    level, xhtml2pdf back-fills the gap with entries that copy the *current*
    heading's own text (`xhtml2pdf_reportlab.py`, PmlParagraph.draw), so a
    filler and a genuine heading that happens to repeat the same title one
    level down are indistinguishable by text, depth, or page alone. Order is
    not ambiguous, though: pypdf's nested-list outline representation lists a
    parent immediately before its own children, which matches emission order,
    and _toc_entries replays xhtml2pdf's exact filler-counting rule over that
    order to know which entries are real.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = []

    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                try:
                    pages.append(reader.get_destination_page_number(item) + 1)
                except Exception:
                    continue

    walk(reader.outline)
    return pages


def _toc_entries(headings, raw_pages):
    """Pair source headings with their rendered page, filler-free.

    Replays xhtml2pdf's own backfill rule (`xhtml2pdf_reportlab.py`,
    PmlParagraph.draw: `last = canv.outlineLast + 1; while last < level: emit
    filler; last += 1`) using the *known* source heading levels rather than
    guessing from the rendered outline's text. Each heading consumes exactly as
    many raw outline entries as xhtml2pdf would have emitted for it - 1 plus one
    per skipped level - and only the last of those (the real entry) carries a
    page number worth keeping.
    """
    entries = []
    prev_last, idx = -1, 0
    for level, text in headings:
        n = 1 + max(0, level - (prev_last + 1))
        page = raw_pages[idx + n - 1] if idx + n <= len(raw_pages) else (raw_pages[-1] if raw_pages else 1)
        idx += n
        entries.append((level, text, page))
        prev_last = level
    if idx != len(raw_pages):
        print(
            "md-to-pdf: warning - outline entry count did not match the source "
            "heading structure; contents page numbers may be inaccurate",
            file=sys.stderr,
        )
    if entries:
        shallow = min(level for level, _, _ in entries)
        entries = [(level - shallow, text, page) for level, text, page in entries]
    return entries


def _toc_html(entries):
    rows = []
    for depth, text, page in entries:
        # text is a heading's inner HTML, already escaped by python-markdown -
        # re-escaping it here would double-encode any "&".
        rows.append(
            '<tr><td class="toc-t toc-l{d}">{t}</td><td class="toc-p">{p}</td></tr>'.format(
                d=min(depth, 2), t=text, p=page
            )
        )
    return '<div class="toc-head">Contents</div><table class="toc">{}</table>'.format(
        "".join(rows)
    )


def _cover_html(title, subtitle, date):
    parts = ['<div class="cover">']
    if title:
        parts.append('<div class="cover-title">{}</div>'.format(_escape(title)))
    if subtitle:
        parts.append('<div class="cover-subtitle">{}</div>'.format(_escape(subtitle)))
    if date:
        parts.append('<div class="cover-date">{}</div>'.format(_escape(date)))
    parts.append("</div>")
    return "\n".join(parts)


def build(args):
    import markdown
    from xhtml2pdf import pisa

    font_dir = Path(args.font_dir) if args.font_dir else FONT_DIR_DEFAULT
    _register_fonts(font_dir)

    extra_css = ""
    if args.css:
        css_path = Path(args.css)
        if not css_path.is_file():
            _fail("stylesheet not found: {}".format(css_path.resolve()))
        extra_css = _strip_at_page(css_path.read_text(encoding="utf-8-sig"), css_path)

    sources = [Path(p).resolve() for p in args.inputs]
    for src in sources:
        if not src.is_file():
            _fail("input not found: {}".format(src))

    # utf-8-sig: a byte-order mark left on the front of the text would stop the
    # first heading being a heading at all, silently demoting it to a paragraph.
    raw = [s.read_text(encoding="utf-8-sig") for s in sources]
    fragments = [
        markdown.markdown(text, extensions=["tables", "fenced_code", "toc"]) for text in raw
    ]

    number_level = None
    if args.number_sections:
        levels = []
        for frag in fragments:
            levels.extend(_heading_levels(frag))
        number_level = args.number_from_level or _pick_number_level(levels)

    assets = {}
    counters = []
    processed = []
    for src, frag in zip(sources, fragments):
        if number_level:
            frag = _number_headings(frag, number_level, counters)
        frag = _map_images(frag, src.parent, assets)
        frag = _size_table_columns(frag)
        processed.append(frag)

    all_headings = [h for frag in processed for h in _extract_headings(frag)]

    want_cover = bool(args.title or args.subtitle or args.date)
    want_toc = args.toc if args.toc is not None else len(sources) > 1
    want_footer = args.page_numbers

    if want_toc and not all_headings:
        print(
            "md-to-pdf: no headings found, so no contents page is produced",
            file=sys.stderr,
        )
        want_toc = False

    css = _page_css(args.page_size, want_cover, want_footer) + BASE_CSS + "\n" + extra_css

    def assemble(toc_entries):
        body = []
        if want_cover:
            body.append(_cover_html(args.title, args.subtitle, args.date))
            body.append('<pdf:nexttemplate name="{}" />'.format(CONTENT_TEMPLATE))
            body.append('<div style="page-break-before: always"></div>')
        if toc_entries:
            body.append(_toc_html(toc_entries))
            body.append('<div style="page-break-before: always"></div>')
        for i, frag in enumerate(processed):
            if i:
                body.append('<div style="page-break-before: always"></div>')
            body.append(frag)
        if want_footer:
            body.append(
                '<div id="footer_content">Page <pdf:pagenumber> of <pdf:pagecount></div>'
            )
        return "<html><head><style>{}</style></head><body>{}</body></html>".format(
            css, "\n".join(body)
        )

    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Render to a sibling temp file and move it into place at the very end, so a
    # failure part-way through cannot leave a truncated PDF - least of all by
    # destroying a good one already at that path.
    tmp_out = out.with_name(out.name + ".part{}".format(os.getpid()))

    collector = _RenderErrors()
    log = logging.getLogger("xhtml2pdf")
    # Child loggers (xhtml2pdf.tags and friends) propagate here, but the level
    # has to be lowered or the records never reach the handler.
    previous_level = log.level
    log.setLevel(logging.WARNING)
    log.addHandler(collector)

    def render(html):
        del collector.messages[:]
        with tmp_out.open("wb") as fh:
            result = pisa.CreatePDF(
                html, dest=fh, link_callback=lambda uri, rel: assets.get(uri, uri)
            )
        # result.err is a count, but xhtml2pdf 0.2.17 never increments it; the
        # collector is the signal that actually fires.
        if result.err or collector.messages:
            detail = "\n".join("  " + m for m in collector.messages[:10])
            tmp_out.unlink()
            _fail("PDF generation failed:\n{}".format(detail or "  (no detail)"))

    try:
        # Inserting the contents listing shifts every page it lists, so the
        # numbers printed in it come from the previous render and are only
        # correct once the outline stops moving. The listing's own length is
        # fixed after the first pass, so this settles in three renders; the loop
        # just proves it.
        entries = None
        settled = not want_toc
        for _ in range(4):
            render(assemble(entries))
            if not want_toc:
                break
            found = _toc_entries(all_headings, _outline_pages(tmp_out))
            if entries == found:
                settled = True
                break
            entries = found
        if not settled:
            print(
                "md-to-pdf: warning - contents page numbers did not settle; some may "
                "be off by a page",
                file=sys.stderr,
            )
        os.replace(str(tmp_out), str(out))
    finally:
        log.removeHandler(collector)
        log.setLevel(previous_level)
        if tmp_out.exists():
            tmp_out.unlink()

    print("Wrote {}".format(out))


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="build.py",
        description="Build a PDF from one or more Markdown files.",
    )
    p.add_argument("output", metavar="OUT.pdf", help="output PDF path")
    p.add_argument("inputs", metavar="IN.md", nargs="+", help="Markdown input(s), in order")
    p.add_argument("--title", help="cover page title")
    p.add_argument("--subtitle", help="cover page subtitle")
    p.add_argument("--date", help="cover page date line")
    p.add_argument(
        "--toc", dest="toc", action="store_true", default=None,
        help="include a table of contents (default: on for multiple inputs)",
    )
    p.add_argument(
        "--no-toc", dest="toc", action="store_false", help="omit the table of contents"
    )
    p.add_argument(
        "--page-numbers", dest="page_numbers", action="store_true", default=True,
        help="footer page numbers (default: on)",
    )
    p.add_argument(
        "--no-page-numbers", dest="page_numbers", action="store_false",
        help="omit footer page numbers",
    )
    p.add_argument(
        "--number-sections", action="store_true", help="number headings 1, 1.1, 1.1.1"
    )
    p.add_argument(
        "--number-from-level", type=int, choices=range(1, 7), metavar="N",
        help="heading level numbering starts at; implies --number-sections",
    )
    p.add_argument(
        "--page-size", choices=sorted(PAGE_SIZES), default="letter", help="default: letter"
    )
    p.add_argument("--css", help="extra stylesheet, appended after the built-in CSS")
    p.add_argument("--font-dir", help="directory holding the DejaVu TTFs")
    args = p.parse_args(argv)
    if args.number_from_level:
        args.number_sections = True
    return args


def main():
    # A PDF path or an error message can hold characters the console's default
    # encoding cannot represent, which would otherwise turn a successful build
    # into a UnicodeEncodeError traceback.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")

    # Args first so --help costs nothing, then dependencies, then the build,
    # whose third-party imports are function-local for that reason.
    args = _parse_args(sys.argv[1:])
    _ensure_deps()
    build(args)


if __name__ == "__main__":
    main()
