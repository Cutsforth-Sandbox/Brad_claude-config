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
import functools
import hashlib
import html
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import _thread
import warnings
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEPS_DIR = SKILL_DIR / "_deps"
FONT_DIR_DEFAULT = SKILL_DIR / "fonts"

# Pinned to a compatible range so every synced machine resolves the same majors,
# including reportlab/pypdf/svglib/Pillow: xhtml2pdf pulls them in as transitives
# with only lower bounds of its own, so without an explicit pin here two machines
# installing the same day can still land on different patch versions of each -
# and any of the four is a plausible culprit behind a rendering bug that depends
# on exact internal behaviour. Ranges below match what every synced machine has
# already resolved and been tested against, except Pillow's floor: 12.0 itself
# requires Python >=3.10 (its own dist-info says so), so pinning >=12.0 would
# hard-fail the whole install on an older interpreter that could otherwise get
# a compatible 11.x. >=11.0 still resolves to 12.3.0 on Python >=3.10 - the
# version already tested - and degrades instead of failing on an older one.
# The stamp hashes this list, so editing it forces a rebuild.
DEPS = [
    "markdown>=3.5,<4",
    "xhtml2pdf>=0.2.17,<0.3",
    "reportlab>=4.5,<5",
    "pypdf>=6.0,<7",
    "svglib>=2.0,<3",
    "Pillow>=11.0,<13",
]

# Shared between the initial render and the structural-repair re-render, so the
# two calls can never drift apart from each other.
MARKDOWN_EXTENSIONS = ["tables", "fenced_code", "toc"]

DIAGRAM_EXTENSIONS = (".puml", ".plantuml", ".iuml")

# Top-level packages that must be present for a _deps tree to count as usable.
# pypdf arrives with xhtml2pdf and is what reads back the outline for the
# contents listing; svglib and PIL arrive with xhtml2pdf/reportlab too and are
# what the diagram/image sizing helpers import - all three belong in the check
# for the same reason: each is a transitive dependency never installed for its
# own sake, so nothing else here would notice one going missing.
DEP_PACKAGES = ["markdown", "xhtml2pdf", "reportlab", "pypdf", "svglib", "PIL"]

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


def _content_frame_size(page_size, want_footer):
    """(width, height) of the content frame in points, footer space excluded.

    Shared with the diagram sizers (`_fit_svg_size`, `_fit_png_size`) so a
    diagram is fitted against the exact same rectangle the page layout
    actually uses, rather than a second, potentially drifting, copy of this
    arithmetic.
    """
    width, height = PAGE_SIZES[page_size]
    inner_w = width - 2 * MARGIN
    full_h = height - 2 * MARGIN
    body_h = full_h - (FOOTER_H + FOOTER_GAP) if want_footer else full_h
    return inner_w, body_h


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
    inner_w, body_h = _content_frame_size(page_size, want_footer)
    full_h = height - 2 * MARGIN
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
/* -pdf-keep-with-next moves a heading to the next page as a unit with
   whatever follows it, rather than leaving it stranded alone at the bottom of
   a page. page-break-after:avoid is not enough on its own - xhtml2pdf's
   parser only acts on page-break-after/before values of always/right/left,
   silently ignoring avoid (confirmed against parser.py's handling; the
   declaration is kept here for future engines that do honor it). */
h2 { font-size: 16pt; margin-top: 22pt; page-break-after: avoid; -pdf-keep-with-next: true; }
h3 { font-size: 13pt; margin-top: 16pt; page-break-after: avoid; -pdf-keep-with-next: true; }
/* This shared rule carries no -pdf-keep-with-next: on a large table it forces
   reportlab into a repeated whole-table refitting attempt that is quadratic
   and catastrophic on real documents (measured: >90s on a 60-row table where
   the same document renders in 3.6s without it). A large table may therefore
   split across a page break; page-break-inside:avoid is kept for engines that
   implement it (xhtml2pdf's parser does not act on it either, for the same
   reason noted on h2/h3 above). A small table (TABLE_KEEP_TOGETHER_MAX_ROWS
   or fewer rows) gets the same protection headings have, via an inline
   -pdf-keep-with-next added per-table in _size_table_columns rather than
   here, since the decision depends on that table's own row count. */
table { border-collapse: collapse; table-layout: fixed; width: 100%; margin: 10pt 0; page-break-inside: avoid; }
th, td { border: none; border-bottom: 1px solid #999; padding: 4pt 10pt; text-align: left; font-size: 10pt; word-wrap: break-word; }
th { font-weight: bold; border-bottom: 2px solid #000; }
code { color: #c8ae74; font-family: "DejaVuSansMono", monospace; font-size: 11pt; }
pre { background-color: #f2f2f2; padding: 6pt; font-family: "DejaVuSansMono", monospace; font-size: 8pt; }
img { max-width: 100%; margin: 8pt 0; }
hr { border: none; border-top: 2px solid #000; margin: 20pt 0; }

/* -pdf-keep-with-next on the image, not the wrapping div, is what actually
   keeps a rendered diagram with its caption - the div isn't itself a
   flowable xhtml2pdf tracks for this purpose. Scoped to one image rather
   than a long table, this is cheap: see the table rule above for why the
   same property is not used there. */
.figure { text-align: center; margin: 10pt 0; }
.figure img { -pdf-keep-with-next: true; }
.figure-caption { font-size: 9pt; color: #444; margin-top: 4pt; }

#footer_content { text-align: center; font-size: 8pt; color: #666; }

.cover { text-align: center; }
.cover-title { font-size: 32pt; margin-top: 220pt; }
.cover-subtitle { font-size: 18pt; color: #444; margin-top: 12pt; }
.cover-date { font-size: 11pt; color: #666; margin-top: 30pt; }

.toc-head { font-size: 20pt; margin-bottom: 14pt; border-bottom: 2px solid #000; padding-bottom: 8pt; }
/* page-break-inside:auto overrides the shared rule's avoid, since a contents
   listing must be free to run over as many pages as it needs. This table
   never receives the small-table -pdf-keep-with-next either: it is built by
   _toc_html and assembled straight into the body, never passing through the
   per-file _size_table_columns pass that adds it. */
table.toc { page-break-inside: auto; margin: 0; }
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
_ALT_ATTR_RE = re.compile(r"(?<![-\w])alt\s*=\s*(\"([^\"]*)\"|'([^']*)'|(\S+))", re.I)
_REMOTE_RE = re.compile(r"^(https?:|data:)", re.I)

# A diagram's rendered PNG or SVG carries this beside the source hash it was
# produced from, so a pre-rendered sibling can be checked for drift without
# trusting mtime - which OneDrive sync, `git checkout`, and a plain copy all
# rewrite regardless of whether the content actually changed.
_DIAGRAM_HASH_RE = re.compile(rb"md-to-pdf:source-sha256:([0-9a-f]{64})")
# The whole comment, in str form for _stamp_diagram (which reads/rewrites the
# .svg as text, to avoid disturbing its encoding) - removes a stale stamp
# cleanly before writing a new one, rather than leaving an emptied <!-- --> .
_DIAGRAM_HASH_COMMENT_RE = re.compile(
    r"[ \t]*<!--\s*md-to-pdf:source-sha256:[0-9a-f]{64}\s*-->\s*\n?"
)
_DIAGRAM_SIBLING_EXTS = (".svg", ".png")


def _diagram_source_hash(source_path):
    return hashlib.sha256(source_path.read_bytes()).hexdigest()


def _fit_svg_size(svg_path, frame_w_pt, frame_h_pt):
    """(width_pt, height_pt) fitting an SVG's own intrinsic size into a
    frame_w_pt x frame_h_pt box, preserving aspect ratio.

    xhtml2pdf renders an inline <img src="....svg"> as native vector content
    (real path/text operators in the page's own content stream - confirmed by
    inspecting the produced PDF, not by reading xhtml2pdf's source, which
    documents a *different*, rasterizing method as the only path and turns out
    not to be the one actually used for an ordinary inline image). Vector
    output has no pixel resolution to run out of, so fitting it into the frame
    is purely a layout question, not a legibility one - unlike a raster PNG.
    """
    from svglib.svglib import svg2rlg

    drawing = svg2rlg(str(svg_path))
    if drawing.width <= 0 or drawing.height <= 0:
        # An <svg> root with no width/height/viewBox parses fine (svglib
        # returns a real, usually-empty Drawing) but gives a 0x0 size - not a
        # contrived case, this is what any hand-authored or non-PlantUML SVG
        # missing those attributes produces.
        _fail(
            "diagram has no usable size (width or height is 0): {}\n"
            "  add an explicit width/height or viewBox to its <svg> root".format(
                svg_path
            )
        )
    scale = min(frame_w_pt / drawing.width, frame_h_pt / drawing.height)
    return drawing.width * scale, drawing.height * scale


def _fit_png_size(png_path, frame_w_pt, frame_h_pt):
    """(width_pt, height_pt) fitting a PNG's pixel size into a frame,
    treating its pixels as points (72dpi) - matching what xhtml2pdf itself
    assumes for a raster image with no explicit width/height."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(png_path) as im:
            px_w, px_h = im.size
    except UnidentifiedImageError:
        _fail("diagram sibling is not a readable image: {}".format(png_path))
    if px_w <= 0 or px_h <= 0:
        _fail("diagram has no usable size (width or height is 0): {}".format(png_path))
    scale = min(frame_w_pt / px_w, frame_h_pt / px_h)
    return px_w * scale, px_h * scale


# Bounds the best-effort kill/drain steps below, so a taskkill that itself
# hangs (blocked by endpoint-protection software) or a grandchild that
# survives the kill and never closes its end of the pipe can't turn a bounded
# timeout back into an unbounded hang - the exact failure mode this whole
# helper exists to close.
_KILL_CLEANUP_TIMEOUT = 10


def _run_killing_tree(argv, timeout, text=False, env=None):
    """Like subprocess.run(argv, timeout=timeout, capture_output=True, ...),
    but a timeout kills the whole process tree, not just the immediate child.

    subprocess.run's own kill-on-timeout only signals the direct child. A
    real `plantuml` install is normally a wrapper script (.bat on Windows,
    a shell script elsewhere) launching `java` as a grandchild; killing just
    the wrapper leaves that grandchild running, still holding the captured
    stdout/stderr pipes open, so the parent build still blocks well past
    `timeout` waiting to drain them. Launching into a new process
    group/session and killing that whole group on timeout closes the pipes
    immediately instead.
    """
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=text, env=env, **popen_kwargs,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=_KILL_CLEANUP_TIMEOUT,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            proc.communicate(timeout=_KILL_CLEANUP_TIMEOUT)
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


_PLANTUML_SANDBOX_MIN = (1, 2020, 11)
_PLANTUML_VERSION_RE = re.compile(r"PlantUML version (\d+)\.(\d+)\.(\d+)")

# Matches the render call's own budget below: both are dominated by the same
# JVM cold start (AV scanning java.exe, a network-mounted profile), and a
# tighter default here would fail this check on a slow-but-working JVM that
# the render itself would have tolerated fine.
_PLANTUML_RENDER_TIMEOUT = 60
_PLANTUML_PROBE_TIMEOUT = _PLANTUML_RENDER_TIMEOUT

# Both of the above are also capped by --timeout when the user asks for
# something tighter (see build()'s probe_timeout/render_timeout), so an
# explicit fast-failure request bounds the whole diagram pipeline, not just
# one half of it.


@functools.lru_cache(maxsize=None)
def _check_plantuml_sandbox(plantuml_exe, timeout):
    """(ok, detail): whether this plantuml build enforces PLANTUML_SECURITY_PROFILE,
    and - when it doesn't - why, specifically enough to tell a broken install
    from a merely old one and to name the actual version threshold.

    Support for the env var was added in 1.2020.11 (plantuml/plantuml#1450's
    fix). Confirmed on 1.2020.02: the env var is accepted and silently
    enforces nothing - a real `!include` resolves identically with or without
    it set. Below that version there is no way to sandbox a `.puml` at all.
    Memoized per (plantuml_exe, timeout): called once per distinct pair, not
    once per diagram.
    """
    try:
        result = _run_killing_tree([plantuml_exe, "-version"], timeout, text=True)
    except OSError as exc:
        return False, "could not run `{} -version`: {}".format(plantuml_exe, exc)
    except subprocess.TimeoutExpired:
        return False, "`{} -version` did not respond within {}s".format(
            plantuml_exe, timeout
        )
    output = result.stdout + result.stderr
    m = _PLANTUML_VERSION_RE.search(output)
    if not m:
        detail = "`{} -version` did not report a usable version".format(plantuml_exe)
        if result.returncode:
            snippet = (result.stderr or result.stdout).strip()[:200]
            detail += " (exited {}: {})".format(result.returncode, snippet)
        return False, detail
    version = tuple(int(g) for g in m.groups())
    if version < _PLANTUML_SANDBOX_MIN:
        # Displayed from the regex's own raw groups, not the int-converted
        # `version` tuple: PlantUML's real version strings are zero-padded
        # ("1.2020.02"), and int("02") -> 2 silently drops that in display.
        return False, "PlantUML {} predates {} (SANDBOX support) - upgrade to render from source".format(
            ".".join(m.groups()), ".".join(map(str, _PLANTUML_SANDBOX_MIN))
        )
    return True, ""


def _render_diagram(source_path, plantuml_exe, cache_dir, timeout):
    """Render a PlantUML source to SVG via a locally installed `plantuml`,
    cached by source content so a rebuild only re-invokes the binary when the
    source actually changed.

    SVG, not PNG: xhtml2pdf renders it as vector content (see _fit_svg_size),
    which is simpler and has no resolution ceiling to manage - and it is what
    the sibling-fallback path below already produces for every diagram this
    skill ships against.

    Runs under a subprocess timeout (capped by --timeout, same as the version
    probe) and PLANTUML_SECURITY_PROFILE=SANDBOX so a `.puml` from any cloned
    repo cannot use `!include`/`!includeurl` to read local files or reach the
    network at render time. The env var form is required - PlantUML's `-D`
    system-property form of this flag is a known, filed no-op
    (plantuml/plantuml#1450): it accepts the flag and enforces nothing.
    Callers must already have confirmed _check_plantuml_sandbox(plantuml_exe,
    ...) is ok - the only call site (_map_images) does, and duplicating that
    check here would just be unreachable dead code repeating a stale message.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = _diagram_source_hash(source_path)
    out_svg = cache_dir / "{}.svg".format(digest)
    if out_svg.is_file():
        return out_svg

    env = dict(os.environ)
    env["PLANTUML_SECURITY_PROFILE"] = "SANDBOX"
    tmp_dir = cache_dir / "tmp-{}".format(os.getpid())
    tmp_dir.mkdir(exist_ok=True)
    try:
        try:
            result = _run_killing_tree(
                [
                    plantuml_exe, "-tsvg", "--ignore-startuml-filename",
                    "-o", str(tmp_dir.resolve()), str(source_path),
                ],
                timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            _fail(
                "diagram render timed out after {}s for {}".format(timeout, source_path)
            )
        except OSError as exc:
            _fail("could not run `{}` to render {}: {}".format(
                plantuml_exe, source_path, exc
            ))
        # --ignore-startuml-filename: without it, a source starting with
        # `@startuml Name` makes PlantUML write Name.svg instead of
        # <source_path.stem>.svg, and the check below would report a
        # successful render as a failure for not finding the file it expects.
        rendered = tmp_dir / (source_path.stem + ".svg")
        if result.returncode or not rendered.is_file():
            _fail(
                "diagram render failed for {}:\n{}".format(
                    source_path, result.stderr.decode("utf-8", "replace")
                )
            )
        os.replace(str(rendered), str(out_svg))
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
    return out_svg


def _find_diagram_sibling(source_path):
    for ext in _DIAGRAM_SIBLING_EXTS:
        candidate = source_path.with_suffix(ext)
        if candidate.is_file():
            return candidate
    return None


def _verify_diagram_sibling(sibling_path, source_path, plantuml_note=None):
    """_fail unless `sibling_path` carries a hash matching `source_path`'s
    current content - so a pre-rendered diagram can never silently drift from
    the source it depicts.

    plantuml_note, when given, names why a `plantuml` on PATH was skipped in
    favor of this sibling - otherwise a user with an old or broken install
    and an unstamped sibling sees a message that never mentions plantuml was
    involved at all, with no way to know upgrading it is an alternative to
    the manual blessing step below.
    """
    data = sibling_path.read_bytes()
    m = _DIAGRAM_HASH_RE.search(data)
    stamp_cmd = "python3 build.py --stamp-diagram {} {}".format(
        sibling_path, source_path
    )
    note = "\n  (`plantuml` on PATH was skipped: {})".format(plantuml_note) if plantuml_note else ""
    if not m:
        _fail(
            "diagram sibling carries no recorded source hash, so it cannot be "
            "verified against its source and is treated as stale:\n"
            "  sibling: {}\n  source:  {}\n"
            "  once you have confirmed by eye that the sibling matches its "
            "current source, bless it with:\n    {}{}".format(
                sibling_path, source_path, stamp_cmd, note
            )
        )
    if m.group(1).decode() != _diagram_source_hash(source_path):
        _fail(
            "diagram sibling is stale - its recorded source hash does not "
            "match the current source:\n  sibling: {}\n  source:  {}\n"
            "  regenerate it (with `plantuml` on PATH) or, once you have "
            "confirmed by eye that the sibling now matches, re-bless it "
            "with:\n    {}{}".format(sibling_path, source_path, stamp_cmd, note)
        )


def _stamp_diagram(sibling_path, source_path):
    """Record `source_path`'s current hash into `sibling_path`, for a
    pre-existing diagram image that predates this hash check and has been
    manually confirmed (by a human, not by this tool) to already match its
    source. Only .svg is supported: a trailing XML comment is invisible to
    every SVG viewer and renderer, which is not true of PNG without writing a
    text chunk into the image itself."""
    sibling_path = Path(sibling_path)
    source_path = Path(source_path)
    if sibling_path.suffix.lower() != ".svg":
        _fail("--stamp-diagram only supports an .svg sibling, got: {}".format(sibling_path))
    if not sibling_path.is_file():
        _fail("no such sibling file: {}".format(sibling_path))
    if not source_path.is_file():
        _fail("no such diagram source: {}".format(source_path))
    text = sibling_path.read_text(encoding="utf-8")
    text = _DIAGRAM_HASH_COMMENT_RE.sub("", text)
    digest = _diagram_source_hash(source_path)
    text = text.rstrip() + "\n<!-- md-to-pdf:source-sha256:{} -->\n".format(digest)
    sibling_path.write_text(text, encoding="utf-8")
    print("md-to-pdf: stamped {} with {}'s current hash".format(sibling_path, source_path))


def _map_images(html, base_dir, assets, frame_size, diagram_cache_dir, probe_timeout, render_timeout):
    """Route every local <img src> through an opaque key served by link_callback.

    xhtml2pdf resolves a callback's return value as a filesystem path and skips
    URI parsing, which is the only reliable way to name a Windows path: put
    `C:\\...` straight into src and `C:` is read as a URI scheme. Keys are unique
    per document so inputs from different directories can each resolve their own
    relative paths.

    A reference to a PlantUML source (.puml/.plantuml/.iuml) is rendered from
    that source through a locally installed `plantuml`, or - lacking one -
    resolved to a pre-rendered sibling image whose recorded hash is checked
    against the source, so a diagram can never silently drift from what it
    depicts. Either way the result is wrapped in a captioned figure, using the
    Markdown alt text as the caption.
    """
    from urllib.parse import unquote

    frame_w, frame_h = frame_size
    plantuml_exe = shutil.which("plantuml")

    def fix_tag(tag_match):
        tag = tag_match.group(0)
        src_match = _SRC_ATTR_RE.search(tag)
        if not src_match:
            return tag
        raw = src_match.group(2)
        quote = raw[0] if raw[:1] in ("\"", "'") else ""
        uri = raw[1:-1] if quote else raw
        if _REMOTE_RE.match(uri):
            return tag
        # A percent-escaped space is the normal Markdown spelling of a path
        # with a space in it, and never a literal '%20' on disk.
        path = Path(unquote(uri))
        resolved = (path if path.is_absolute() else base_dir / path).resolve()

        if resolved.suffix.lower() in DIAGRAM_EXTENSIONS:
            if not resolved.is_file():
                _fail(
                    "diagram source not found: {}\n  referenced as: {}".format(
                        resolved, uri
                    )
                )
            # Checked here, not once up front for the whole file: a document
            # with no diagram reference should never pay this subprocess cost
            # at all. _check_plantuml_sandbox is memoized, so a second diagram
            # in the same build reuses the first check's result.
            plantuml_ok, plantuml_detail = (
                _check_plantuml_sandbox(plantuml_exe, probe_timeout)
                if plantuml_exe else (False, "")
            )
            # A plantuml too old or broken to enforce PLANTUML_SECURITY_PROFILE=
            # SANDBOX is treated the same as no plantuml at all, falling back
            # to the sibling path rather than _fail-ing outright - a
            # hash-verified sibling never executes the untrusted `.puml`, so
            # this doesn't reopen what the check exists to close.
            if plantuml_exe and plantuml_ok:
                asset_path = _render_diagram(
                    resolved, plantuml_exe, diagram_cache_dir, render_timeout
                )
                width_pt, height_pt = _fit_svg_size(asset_path, frame_w, frame_h)
            else:
                sibling = _find_diagram_sibling(resolved)
                if sibling is None:
                    candidates = ", ".join(
                        str(resolved.with_suffix(ext)) for ext in _DIAGRAM_SIBLING_EXTS
                    )
                    reason = (
                        "`plantuml` on PATH cannot enforce sandboxing ({})".format(
                            plantuml_detail
                        )
                        if plantuml_exe else "no `plantuml` on PATH"
                    )
                    _fail(
                        "{} and no pre-rendered sibling image for: {}\n"
                        "  looked for: {}".format(reason, resolved, candidates)
                    )
                _verify_diagram_sibling(
                    sibling, resolved,
                    plantuml_note=plantuml_detail if plantuml_exe else None,
                )
                asset_path = sibling
                if sibling.suffix.lower() == ".svg":
                    width_pt, height_pt = _fit_svg_size(sibling, frame_w, frame_h)
                else:
                    width_pt, height_pt = _fit_png_size(sibling, frame_w, frame_h)

            key = "mdpdf-asset-{}".format(len(assets))
            assets[key] = str(asset_path)
            alt_match = _ALT_ATTR_RE.search(tag)
            caption = ""
            if alt_match:
                caption = alt_match.group(2) or alt_match.group(3) or alt_match.group(4) or ""
            caption_html = (
                '<div class="figure-caption">{}</div>'.format(_escape(caption))
                if caption
                else ""
            )
            return (
                '<div class="figure"><img src="{key}" width="{w:.1f}pt" '
                'height="{h:.1f}pt" />{cap}</div>'
            ).format(key=key, w=width_pt, h=height_pt, cap=caption_html)

        if not resolved.is_file():
            _fail("image not found: {}\n  referenced as: {}".format(resolved, uri))
        key = "mdpdf-asset-{}".format(len(assets))
        assets[key] = str(resolved)
        new_src = "{}{}{}{}".format(src_match.group(1), quote or '"', key, quote or '"')
        return tag[: src_match.start()] + new_src + tag[src_match.end() :]

    return _IMG_TAG_RE.sub(fix_tag, html)


MIN_COL_PCT = 15.0
_CODE_WEIGHT = 1.15
_TAG_RE = re.compile(r"<[^>]+>")

# -pdf-keep-with-next on a table forces reportlab into a repeated whole-table
# refitting attempt that is quadratic in row count. Measured directly against
# this file's own generated markup (table-layout:fixed plus the per-cell
# widths _size_table_columns adds - a plainer table is far more forgiving, so
# calibrating against anything less than the real output understates the
# cost): a 20-table document renders in 1.35s per table at 12 rows, and does
# not finish in 15s at 13. This threshold sits with a solid margin below that
# cliff - confirmed safe even at 40 tables (double the calibration load) - so
# a small table still gets the same header-orphan protection headings have,
# while a large one accepts a rare mid-table split rather than the
# catastrophic refit.
TABLE_KEEP_TOGETHER_MAX_ROWS = 10
_TABLE_OPEN_RE = re.compile(r"^<table([^>]*)>", re.I)


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

        if len(rows) <= TABLE_KEEP_TOGETHER_MAX_ROWS:
            def add_keep_with_next(open_match):
                attrs = open_match.group(1)
                decl = "-pdf-keep-with-next:true"
                if _STYLE_RE.search(attrs):
                    attrs = _STYLE_RE.sub(r"\1" + decl + ";", attrs, count=1)
                else:
                    attrs = '{} style="{}"'.format(attrs, decl)
                return "<table{}>".format(attrs)

            table_html = _TABLE_OPEN_RE.sub(add_keep_with_next, table_html, count=1)

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
# Structural lint: rendered-output mismatch with likely source intent
# --------------------------------------------------------------------------

# A list marker (or a fence) starting a line inside a block that cannot
# legitimately contain one. Detected from python-markdown's own OUTPUT, not a
# source-level guess: a source regex loose enough to catch a glued list also
# fires on correctly blank-line-separated Markdown (measured at thousands of
# false positives per hundred files), because the real question - does this
# line start a new block or continue the current one - is exactly what the
# block parser already answered when it produced this HTML.
_STRUCT_OPEN_RE = re.compile(r"<(p|li|td|blockquote)(?:\s[^>]*)?>", re.I)


def _iter_struct_containers(html):
    """Yield (tag, inner_html) for each top-level p/li/td/blockquote in html.

    Tracks nesting depth rather than matching a bare non-greedy backreference
    (<(p|li|td|blockquote)...>(.*?)</\\1>) - that stops at the *first*
    same-name close tag, which for a nested <li> (a sub-list inside a list
    item) or a nested <blockquote> silently drops everything in the outer
    container that follows the nested one's own close: confirmed directly,
    that content ends up in no captured group at all, not even a separate
    later match, because finditer resumes past the truncated span.
    """
    pos, n = 0, len(html)
    while pos < n:
        m = _STRUCT_OPEN_RE.search(html, pos)
        if not m:
            return
        tag = m.group(1).lower()
        open_re = re.compile(r"<{}(?:\s[^>]*)?>".format(tag), re.I)
        close_re = re.compile(r"</{}>".format(tag), re.I)
        depth, scan, end = 1, m.end(), None
        while scan < n:
            nxt_close = close_re.search(html, scan)
            if not nxt_close:
                break
            nxt_open = open_re.search(html, scan, nxt_close.start())
            if nxt_open:
                depth += 1
                scan = nxt_open.end()
                continue
            depth -= 1
            scan = nxt_close.end()
            if depth == 0:
                end = nxt_close.start()
                break
        if end is None:
            # Unbalanced (shouldn't happen against real python-markdown
            # output) - skip past the opening tag rather than loop forever.
            pos = m.end()
            continue
        yield tag, html[m.end():end]
        pos = scan


_STRUCT_LIST_RE = re.compile(r"\n[ \t]{0,3}(?:[-*+]|\d{1,2}[.)])[ \t]")
_STRUCT_FENCE_RE = re.compile(r"(?:^|\n)[ \t]{0,3}(?:```|~~~)")

# The source line's own marker (and any blockquote nesting before it), kept
# separate from the text that follows so the marker can be stripped before
# comparing and the leading part can be copied onto an inserted blank line -
# a bare blank line inside a blockquote would push the list out of the quote.
_SRC_MARKER_RE = re.compile(r"^((?:[ \t]*>)*[ \t]*)((?:[-*+]|\d{1,2}[.)])[ \t])")

_DECLUTTER_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_DECLUTTER_BOLD = re.compile(r"(\*\*|__)(.*?)\1")
_DECLUTTER_ITALIC = re.compile(r"(\*|_)(.*?)\1")
_DECLUTTER_CODE = re.compile(r"`([^`]*)`")

# Chars of decluttered text compared per line - short enough to survive a
# formatting difference past this point, long enough that two distinct list
# items rarely share a prefix.
_STRUCT_PREFIX_LEN = 12


def _declutter(text):
    """Strip inline Markdown syntax so a source line can be text-compared
    against rendered output, which has already lost that syntax."""
    text = _DECLUTTER_LINK.sub(r"\1", text)
    text = _DECLUTTER_BOLD.sub(r"\2", text)
    text = _DECLUTTER_ITALIC.sub(r"\2", text)
    text = _DECLUTTER_CODE.sub(r"\1", text)
    return text


def _repair_structure(frag_html, text, source_name, fix):
    """Find and (for a list) repair a block that rendered as something other
    than what its source almost certainly meant.

    Two shapes reach here, both caused by python-markdown requiring a blank
    line before a list or a fence that other renderers (GitHub, CommonMark)
    do not require: a list glued to the preceding line renders as one run-on
    paragraph, and a fence glued to preceding text never opens. Only the list
    shape is repaired - inserting a blank line before a fence that is
    actually mis-indented inside a list item splits the list and restarts its
    numbering (verified directly), which is worse than leaving it alone - so
    a glued fence is reported and left for a human to fix.

    Returns (new_text, new_html, messages). new_text/new_html equal the inputs
    when fix is False or nothing was repaired.
    """
    lines = text.split("\n")
    cursor = 0
    inserts = []  # (source_line_index, container_prefix)
    messages = []

    def locate(plain_after_marker):
        nonlocal cursor
        key = _declutter(plain_after_marker).strip()[:_STRUCT_PREFIX_LEN]
        for i in range(cursor, len(lines)):
            m = _SRC_MARKER_RE.match(lines[i])
            if not m:
                continue
            rest = _declutter(lines[i][m.end():]).strip()[:_STRUCT_PREFIX_LEN]
            if rest == key:
                cursor = i + 1
                return i, m.group(1)
        return None, None

    for _tag, inner in _iter_struct_containers(frag_html):
        lm = _STRUCT_LIST_RE.search(inner)
        if lm:
            frag = inner[lm.start() + 1 :].split("\n")[0]
            plain = html.unescape(_TAG_RE.sub("", frag)).strip()
            mk = re.match(r"(?:[-*+]|\d{1,2}[.)])[ \t]", plain)
            after_marker = plain[mk.end() :] if mk else plain
            line_no, prefix = locate(after_marker)
            if line_no is None:
                messages.append(
                    "{}: a list would render as plain text, but its source line "
                    "could not be located precisely - no fix applied.".format(
                        source_name
                    )
                )
            elif fix:
                inserts.append((line_no, prefix or ""))
                messages.append(
                    "{}:{}: list would have rendered as plain text - inserted a "
                    "blank line before it.".format(source_name, line_no + 1)
                )
            else:
                messages.append(
                    "{}:{}: list would render as plain text for lack of a blank "
                    "line before it.".format(source_name, line_no + 1)
                )
        if _STRUCT_FENCE_RE.search(inner):
            messages.append(
                "{}: a fenced code block runs into surrounding text - check for "
                "a missing blank line or an unbalanced fence (not auto-fixed: "
                "this shape is usually a fence mis-indented inside a list, and "
                "inserting a blank line would split the list instead).".format(
                    source_name
                )
            )

    if not inserts:
        return text, frag_html, messages

    for line_no, prefix in sorted(inserts, reverse=True):
        lines.insert(line_no, prefix.rstrip())
    new_text = "\n".join(lines)
    import markdown

    new_html = markdown.markdown(new_text, extensions=MARKDOWN_EXTENSIONS)
    return new_text, new_html, messages


# --------------------------------------------------------------------------
# Document assembly
# --------------------------------------------------------------------------


# Warnings xhtml2pdf/svglib emit for input that is unusual but not broken -
# the resulting page just shows less than a "real" failure would suppress:
#   - spooling a remote or inline asset through a temp file (routine).
#   - a <table> with zero rows (raw HTML passthrough; a Markdown-syntax table
#     always synthesizes a row, so this is not reachable from ordinary
#     markdown.tables output, but raw HTML in the source can hit it).
#   - an SVG exported by Inkscape before 0.92: svglib's note about its 90dpi
#     assumption is informational: nothing is dropped from the page.
_BENIGN_LOG = (
    "Created temporary file",
    "<table> is empty",
    "<table> rows seem to be inconsistent",
    "This SVG was created with Inkscape",
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

    Reads the whole file into memory first rather than handing PdfReader the
    path: PdfReader never closes a path-opened file, so a timeout interrupting
    `walk` below would otherwise leave a handle open on the caller's temp file,
    and unlinking it while open raises WinError 32 in place of the real error.
    """
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(Path(pdf_path).read_bytes()))
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
    fragments = []
    for src, text in zip(sources, raw):
        frag = markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS)
        _, frag, messages = _repair_structure(
            frag, text, str(src), fix=args.fix_structure
        )
        for message in messages:
            print("md-to-pdf: {}".format(message), file=sys.stderr)
        fragments.append(frag)

    number_level = None
    if args.number_sections:
        levels = []
        for frag in fragments:
            levels.extend(_heading_levels(frag))
        number_level = args.number_from_level or _pick_number_level(levels)

    frame_size = _content_frame_size(args.page_size, args.page_numbers)
    diagram_cache_dir = SKILL_DIR / "_diagrams"

    assets = {}
    counters = []
    processed = []
    # Both capped at --timeout too, so a hung `plantuml` - whether the hang is
    # in the version probe or the render itself - can't wait out a fixed
    # ceiling regardless of what the user asked for.
    probe_timeout = min(_PLANTUML_PROBE_TIMEOUT, args.timeout)
    render_timeout = min(_PLANTUML_RENDER_TIMEOUT, args.timeout)
    for src, frag in zip(sources, fragments):
        if number_level:
            frag = _number_headings(frag, number_level, counters)
        frag = _map_images(
            frag, src.parent, assets, frame_size, diagram_cache_dir,
            probe_timeout, render_timeout,
        )
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
    # xhtml2pdf's own logger catches its content-loss warnings; svglib's and
    # reportlab's are separate loggers, and a diagram that silently drops an
    # element there (an unreadable embedded image, an unresolved clip path)
    # would otherwise still end in "Wrote ..." and exit 0 - exactly the class
    # of bug this collector exists to catch.
    watched_loggers = [
        logging.getLogger(name)
        for name in ("xhtml2pdf", "svglib.svglib", "reportlab")
    ]
    previous_levels = [log.level for log in watched_loggers]
    for log in watched_loggers:
        log.setLevel(logging.WARNING)
        log.addHandler(collector)

    def render(html):
        del collector.messages[:]
        # reportlab's own content-loss signals (a table cell/flowable that
        # doesn't fit, an unsupported text direction) mostly go through
        # `warnings.warn`, not `logging` - the `reportlab` entry in
        # watched_loggers above catches only the small part of reportlab that
        # does use logging (currently nothing above DEBUG). This capture is
        # what actually reaches the warnings.warn path. It still cannot reach
        # a missing font glyph, which reportlab reports by writing straight to
        # stderr through its own pre-logging warnOnce mechanism - no Python
        # hook observes that path.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with tmp_out.open("wb") as fh:
                result = pisa.CreatePDF(
                    html, dest=fh, link_callback=lambda uri, rel: assets.get(uri, uri)
                )
        # reportlab's warn() always defaults to UserWarning (verified: both call
        # sites pass no category). Restricting to that excludes ResourceWarning -
        # e.g. an unclosed temp file finalized mid-render by GC, which depends on
        # allocation volume rather than content loss and produced a spurious
        # failure on one real multi-file document.
        warning_messages = [
            str(w.message) for w in caught
            if issubclass(w.category, UserWarning)
            and not any(b in str(w.message) for b in _BENIGN_LOG)
        ]
        # result.err is a count, but xhtml2pdf 0.2.17 never increments it; the
        # collector (and now warning_messages) is the signal that actually fires.
        if result.err or collector.messages or warning_messages:
            detail = "\n".join(
                "  " + m for m in (collector.messages + warning_messages)[:10]
            )
            tmp_out.unlink()
            _fail("PDF generation failed:\n{}".format(detail or "  (no detail)"))

    # signal.SIGALRM does not exist on Windows, so a daemon Timer firing
    # interrupt_main is the only cross-platform wall-clock ceiling available.
    # daemon=True matters: a non-daemon Timer makes interpreter shutdown join
    # it, so an unrelated failure at t=0 would otherwise sit out the whole
    # budget before its own error is even reported (measured: 4.13s for a 4s
    # timer around an immediate sys.exit). The fired flag is what lets a
    # real Ctrl-C during the window still read as Ctrl-C rather than a timeout.
    #
    # Once set, timer_fired is never reset until the whole settling loop below
    # exits - not per pass. _thread.interrupt_main() only schedules the
    # interrupt; Python's own docs give no guarantee it lands before the next
    # pass's try block, and Timer.cancel() cannot retract one already in
    # flight (confirmed: an interrupt fired just as a pass's guarded code
    # finishes can still be delivered after that pass's own except clause has
    # been passed, landing in the between-pass bookkeeping instead). Since
    # nothing but this timer ever sets the flag, catching KeyboardInterrupt
    # once for the whole loop - rather than once per pass - closes that gap
    # without risking a real Ctrl-C being misreported as a timeout.
    timer_fired = [False]

    def _trip():
        timer_fired[0] = True
        _thread.interrupt_main()

    try:
        try:
            # Inserting the contents listing shifts every page it lists, so the
            # numbers printed in it come from the previous render and are only
            # correct once the outline stops moving. The listing's own length is
            # fixed after the first pass, so this settles in three renders; the
            # loop just proves it.
            entries = None
            settled = not want_toc
            for _ in range(4):
                timer = threading.Timer(args.timeout, _trip)
                timer.daemon = True
                try:
                    # timer.start() itself blocks briefly on the new thread's
                    # startup handshake, which is long enough for a near-zero
                    # timeout to fire before this line returns - so arming it
                    # has to be inside the same try as the render it guards,
                    # or that race raises past this function as a bare
                    # KeyboardInterrupt.
                    timer.start()
                    render(assemble(entries))
                    if want_toc:
                        found = _toc_entries(all_headings, _outline_pages(tmp_out))
                finally:
                    timer.cancel()
                if not want_toc:
                    break
                if entries == found:
                    settled = True
                    break
                entries = found
        except KeyboardInterrupt:
            if timer_fired[0]:
                _fail(
                    "render exceeded --timeout {}s; raise it if the "
                    "document is just large, not stuck".format(args.timeout)
                )
            raise
        if not settled:
            print(
                "md-to-pdf: warning - contents page numbers did not settle; some may "
                "be off by a page",
                file=sys.stderr,
            )
        os.replace(str(tmp_out), str(out))
    finally:
        for log, level in zip(watched_loggers, previous_levels):
            log.removeHandler(collector)
            log.setLevel(level)
        try:
            if tmp_out.exists():
                tmp_out.unlink()
        except OSError:
            # A reader left open across an interrupt (or another process)
            # can hold the handle a moment longer; losing the cleanup race
            # is not worth turning into the reported error.
            pass

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
    p.add_argument(
        "--fix-structure", dest="fix_structure", action="store_true", default=True,
        help="repair a list rendered as plain text for lack of a blank line (default: on)",
    )
    p.add_argument(
        "--no-fix-structure", dest="fix_structure", action="store_false",
        help="report structural mismatches (lists, fences) without repairing them",
    )
    p.add_argument(
        "--timeout", type=int, default=120, metavar="SECONDS",
        help="wall-clock ceiling per render pass (default: 120)",
    )
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

    # A separate utility mode, checked before the OUT.pdf/IN.md positional
    # parser below since it takes a different shape of arguments and needs
    # neither python-markdown nor xhtml2pdf.
    argv = sys.argv[1:]
    if argv[:1] == ["--stamp-diagram"]:
        if len(argv) != 3:
            _fail("--stamp-diagram needs exactly two paths: SVG_SIBLING PUML_SOURCE")
        _stamp_diagram(argv[1], argv[2])
        return

    # Args first so --help costs nothing, then dependencies, then the build,
    # whose third-party imports are function-local for that reason.
    args = _parse_args(argv)
    _ensure_deps()
    build(args)


if __name__ == "__main__":
    main()
