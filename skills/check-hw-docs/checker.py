#!/usr/bin/env python3
"""Mechanical tiers 0-2 for /check-hw-docs, plus an on-demand tier-3 helper.

This script NEVER writes to context.md or to any document folder. Tier-1 downloads
go to a temp dir that is removed on exit. All judgment (steps 3-6 of SKILL.md)
stays with the model.

Usage:
    checker.py check [--root DIR] [--only SUBSTR] [--json]
    checker.py version <local-path-or-absolute> [--root DIR]

Why the odd-looking details matter (each one is a bug this script exists to prevent):

  * User-Agent must NOT be the urllib default. The raspberrypi.com redirect chain returns 403
    to any UA containing "Python-urllib"; every other string tested passes. (Which hop issues
    the 403 was never established -- it was only ever observed through a followed chain, so
    do not attribute it to a specific host.) No browser impersonation is needed or used.
  * urllib returns only the FINAL response after redirects, so reading a redirect hop's
    "Content-Length: 0" is structurally impossible here. (curl -sIL prints every hop and
    caused 18 false "stale" verdicts when parsed with `tail -1`.)
  * Manifest rows are split with str.split('|'), which preserves empty fields. bash's
    `IFS=$'\t' read` collapses consecutive tabs, silently shifting every field after an
    empty `etag` -- the second cause of those false verdicts.
  * Per-host header habits are DATA, not assumptions: compare only the fields a host
    actually returns. pip-assets never sends Content-Length on HEAD; www.rigol.com never
    sends ETag. A field the host never sends is "not comparable", never "changed".
  * beyondmeasure.rigoltech.com answers HEAD with 403 but honours range requests, so a
    1-byte GET yields the true size via Content-Range.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "check-hw-docs/1.0 (hardware-doc manifest verification)"
COLS = ("local_path", "official_url", "verified", "known_version",
        "etag", "last_modified", "size", "notes")

# Hosts needing special handling. `head=False` means HEAD is refused outright, so the
# size probe must use a ranged GET instead. `referer` is required by the host.
HOST_POLICY = {
    "beyondmeasure.rigoltech.com": {
        "head": False,
        "referer": "https://rigolna.com/support/downloads/",
    },
}


# --------------------------------------------------------------------------- paths

def resolve_root(explicit: str | None = None) -> Path:
    """Locate the HW_Docs root without hardcoding a username or drive."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("HW_DOCS"):
        candidates.append(Path(os.environ["HW_DOCS"]))
    if os.environ.get("OneDrive"):
        candidates.append(Path(os.environ["OneDrive"]) / "Documents" / "HW_Docs")
    candidates.append(Path.home() / "HW_Docs")
    for c in candidates:
        if (c / "context.md").is_file():
            return c
    tried = "\n  ".join(str(c) for c in candidates)
    sys.exit(f"cannot locate HW_Docs (no context.md found). Tried:\n  {tried}\n"
             f"Pass --root DIR or set $HW_DOCS.")


# ------------------------------------------------------------------------ manifest

def parse_manifest(root: Path) -> tuple[list[dict], list[str]]:
    """Parse the pipe table. Only rows naming a .pdf are manifest entries, which excludes
    the separator row and the prose tables under ## Notes.

    Returns (rows, warnings). A line that clearly *means* to be a manifest row -- it names a
    .pdf -- but does not split into exactly len(COLS) fields is reported as a warning rather
    than skipped in silence. A literal '|' in the notes column would otherwise delete a
    document from every future check with no trace: no verdict, no error, no coverage.
    """
    rows: list[dict] = []
    warnings: list[str] = []
    text = (root / "context.md").read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        parts = [c.strip() for c in s.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        looks_like_row = ".pdf" in s.lower()
        if len(parts) != len(COLS):
            if looks_like_row:
                warnings.append(
                    f"context.md line {lineno}: names a .pdf but split into {len(parts)} "
                    f"fields, expected {len(COLS)} -- row IGNORED. A literal '|' in a cell "
                    f"(usually notes) is the usual cause.")
            continue
        if ".pdf" not in parts[0].lower():
            # Right field count, but the local-path cell isn't a document. A blank or garbled
            # path cell would otherwise drop the row as silently as a stray '|' once did.
            if looks_like_row:
                warnings.append(
                    f"context.md line {lineno}: has {len(COLS)} fields and mentions a .pdf, "
                    f"but its local-path cell is {parts[0]!r} -- row IGNORED.")
            continue
        row = dict(zip(COLS, parts))
        row["lineno"] = lineno
        rows.append(row)

    # One physical file must not carry two verdicts. Grouping is by official_url, so a repeated
    # local_path under two different URLs would be probed twice with no cross-check.
    seen: dict[str, int] = {}
    for r in rows:
        if r["local_path"] in seen:
            warnings.append(
                f"context.md line {r['lineno']}: local path {r['local_path']} also appears on "
                f"line {seen[r['local_path']]} -- one file cannot have two verdicts.")
        seen[r["local_path"]] = r["lineno"]
    return rows, warnings


# ---------------------------------------------------------------------------- http

def _request(url: str, method: str, extra: dict | None = None, timeout: int = 90):
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", UA)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=timeout)


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def probe(url: str) -> tuple[dict, str, str | None]:
    """Fetch the official file's validators as cheaply as the host allows.

    Returns (fields, how, error). `fields` values may be None where the host is silent.
    """
    policy = HOST_POLICY.get(_host(url), {})
    referer = policy.get("referer")

    if policy.get("head", True):
        try:
            with _request(url, "HEAD") as r:
                h = r.headers
                return ({"etag": h.get("ETag"),
                         "last_modified": h.get("Last-Modified"),
                         "size": h.get("Content-Length")},
                        "HEAD", None)
        except urllib.error.HTTPError as e:
            if e.code not in (403, 405, 501):
                return ({}, "HEAD", f"HTTP {e.code}")
            # fall through to the ranged GET below
        except Exception as e:  # noqa: BLE001 - report, never crash the whole run
            return ({}, "HEAD", f"{type(e).__name__}: {e}")

    extra = {"Range": "bytes=0-0"}
    if referer:
        extra["Referer"] = referer
    try:
        with _request(url, "GET", extra) as r:
            cr = r.headers.get("Content-Range")
            total = cr.rsplit("/", 1)[-1].strip() if cr else None
            return ({"etag": r.headers.get("ETag"),
                     "last_modified": r.headers.get("Last-Modified"),
                     "size": total},
                    "range", None)
    except urllib.error.HTTPError as e:
        return ({}, "range", f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return ({}, "range", f"{type(e).__name__}: {e}")


def download(url: str, dest: Path) -> tuple[bool, str]:
    """GET the whole file and prove it arrived intact. Returns (usable, detail).

    Completeness matters more than it looks: a truncated body still starts with %PDF-, and
    MuPDF silently self-repairs such a file rather than raising -- which made a corrupt
    download compare as "identical text, 1 page" and report `re-export`, i.e. "not stale,
    nothing to do". A wrong verdict, not an error. Hence three checks, not one.
    """
    extra = {}
    referer = HOST_POLICY.get(_host(url), {}).get("referer")
    if referer:
        extra["Referer"] = referer
    try:
        with _request(url, "GET", extra, timeout=600) as r:
            declared = r.headers.get("Content-Length")
            with open(dest, "wb") as f:
                shutil.copyfileobj(r, f, length=1 << 20)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"

    got = dest.stat().st_size
    with open(dest, "rb") as f:
        magic = f.read(5)
    if magic != b"%PDF-":
        return False, f"body is not a PDF (starts {magic!r})"
    if declared is None:
        # Chunked response: no declared length, so size alone cannot prove completeness. This
        # matters because an incrementally-saved PDF truncated at a revision boundary is itself
        # a valid earlier revision ending in a legitimate %%EOF -- every other check here would
        # pass it, and if it equals the stale local copy, tier 1 would report "current".
        # Recover a length from the range probe already used for HEAD-hostile hosts.
        probed, _how, _err = probe(url)
        declared = (probed or {}).get("size")
    if declared is not None and str(declared).isdigit() and int(declared) != got:
        return False, f"incomplete transfer: got {got} B, expected {declared}"
    with open(dest, "rb") as f:
        f.seek(max(0, got - 2048))
        if b"%%EOF" not in f.read():
            return False, f"truncated PDF: no %%EOF trailer in last 2 KB ({got} B)"
    return True, f"{got} B"


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------- tier 0 compare

def compare(stored: dict, fresh: dict) -> tuple[str, list[str]]:
    """current | changed | incomparable, with human-readable reasons.

    Only fields with BOTH a stored value and a fresh value take part. A stored field the
    host does not return is reported as not-comparable rather than treated as a change --
    the manifest legitimately records GET-derived sizes for hosts that omit
    Content-Length on HEAD.
    """
    diffs, notes, compared = [], [], 0
    for field in ("etag", "last_modified", "size"):
        s = (stored.get(field) or "").strip()
        v = (fresh.get(field) or "").strip()
        if not s:
            continue
        if not v:
            notes.append(f"{field}: stored but host does not return it (not comparable)")
            continue
        compared += 1
        if s != v:
            diffs.append(f"{field}: {s} -> {v}")
    if diffs:
        return "changed", diffs + notes      # keep not-comparable notes for diagnosis
    if compared == 0:
        return "incomparable", notes or ["no stored field is comparable"]
    return "current", notes


# ------------------------------------------------------------------- tier 2 content

def content_compare(local: Path, remote: Path) -> tuple[str, str]:
    """stale | re-export, distinguishing a real revision from a cosmetic re-export."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "unknown", "PyMuPDF not available; cannot run tier 2"
    # ExitStack rather than two bare opens: if the second open raises, the first must still be
    # closed. Opening both on one line before the try left the first handle dangling.
    with contextlib.ExitStack() as stack:
        a = stack.enter_context(fitz.open(local))
        b = stack.enter_context(fitz.open(remote))
        # MuPDF repairs damaged files instead of refusing them, so a corrupt input would
        # otherwise be compared as if it were sound. Refuse to draw a conclusion from one.
        for label, doc in (("local", a), ("downloaded", b)):
            if getattr(doc, "is_repaired", False):
                return "corrupt", f"{label} PDF required repair by MuPDF; comparison unsafe"
        pa, pb = a.page_count, b.page_count
        ta = "\n".join(p.get_text() for p in a)
        tb = "\n".join(p.get_text() for p in b)
    if pa != pb:
        return "stale", f"page count {pa} -> {pb}"
    if ta != tb:
        n = sum(1 for ln in difflib.unified_diff(ta.splitlines(), tb.splitlines())
                if ln[:1] in "+-" and not ln.startswith(("---", "+++")))
        return "stale", f"text differs (~{n} changed lines) at {pa} pages"
    return "re-export", f"identical text and page count ({pa} pages)"


# ------------------------------------------------------------------- tier 3 version

DOC_CODE = re.compile(r"\b[A-Z]{2,4}\s?\d{5,6}\s?-\s?\d{4}(?:\s?-\s?\d{2})?\b")
RELEASE = re.compile(r"\bRelease\s+(\d+)\b", re.I)
BUILD_DATE = re.compile(r"build[-\s]?date[:\s]+([0-9]{2,4}[-/][0-9]{2}[-/][0-9]{2,4})", re.I)
COVER_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s?20\d{2}\b")
PUBLISHED = re.compile(r"Published\s+(?:in\s+)?([A-Z][a-z]+\s+20\d{2})")


def _norm(s: str) -> str:
    """Collapse whitespace. Regexes may span a newline between label and value."""
    return " ".join(s.split())


# Identifiers that share a doc code's shape but are not editions. Matched against the text
# immediately LEFT of a candidate.
_NOT_DOC_CODE = re.compile(
    # `Serial[A-Za-z\s]{0,20}` so "Serial Number Range:" is caught, not just "Serial No."
    r"(?:FCC\s*ID|\bS/?N\b|\bP/?N\b|\bIMEI\b|\bMAC\b|Serial[A-Za-z\s]{0,20})"
    r"[^A-Za-z0-9]{0,12}$", re.I)
# Prefixes that are never edition codes, whatever their left context happens to be.
_BAD_PREFIX = frozenset({"SN", "PN", "FCC", "IMEI", "MAC", "ID"})
_IS_DOC_CODE = re.compile(r"(?:Publication|Document|Doc\.?|Number|No\.)[^A-Za-z0-9]{0,12}$",
                          re.I)


def known_code_prefixes(rows: list[dict]) -> frozenset[str]:
    """Publication-code prefixes already recorded in the manifest's `known version` column.

    The strongest signal available: a candidate sharing a prefix with a code this library has
    already recorded is almost certainly the same kind of identifier. Self-maintaining -- a new
    vendor's prefix is learned the first time it lands in `known version`. Verified 2026-08-10
    to yield {DSB, PCX, PGA, PVA, QGA, UGA} from 6 of 39 rows.
    """
    out = set()
    for r in rows:
        for m in DOC_CODE.finditer(r.get("known_version", "")):
            out.add(re.match(r"[A-Z]{2,4}", m.group(0)).group(0))
    return frozenset(out)


def _doc_code(text: str, known: frozenset[str] = frozenset()) -> str | None:
    """Publication code, ignoring identifiers that merely share its shape.

    re.search returns the LEFTMOST match, so an FCC ID or part number earlier on the same legal
    page silently beat the real code: "complies with FCC ID TEST12345-0001. See Publication
    PCX01100-2022-09." returned TEST12345-0001. Collect every candidate, drop the ones whose
    left context marks them as something else, then rank by known prefix, then explicit label.
    """
    cands = []
    for m in DOC_CODE.finditer(text):
        left = text[max(0, m.start() - 24):m.start()]
        if _NOT_DOC_CODE.search(left):
            continue
        code = _norm(m.group(0))
        prefix = re.match(r"[A-Z]{2,4}", code).group(0)
        if prefix.upper() in _BAD_PREFIX:
            continue
        cands.append((prefix in known, bool(_IS_DOC_CODE.search(left)), code))
    if not cands:
        return None
    cands.sort(key=lambda c: (not c[0], not c[1]))   # known prefix > labelled > document order
    return cands[0][2]


# (kind, regex, which capture group holds the VALUE rather than the label).
# doc_code is special-cased in _extract -- it needs candidate ranking, not a plain search.
_KINDS = (
    ("doc_code", DOC_CODE, 0),
    ("release", RELEASE, 0),
    ("build", BUILD_DATE, 1),
    ("published", PUBLISHED, 1),
    ("cover", COVER_DATE, 0),
)


def _extract(pages: list[tuple[int, str]],
             known: frozenset[str] = frozenset()) -> tuple[str | None, int | None]:
    """Best printed edition string across ALL candidate pages.

    Preference is applied across pages, not within one: a precise doc code on page 8 must
    beat a vague cover date on page 1. Searching page-by-page instead returns whatever the
    earliest page happens to carry, which is how UGA27102-1110 lost to "Mar. 2020".
    """
    found: dict[str, tuple[str, int]] = {}
    for kind, rx, grp in _KINDS:
        for pno, text in pages:
            if kind == "doc_code":
                code = _doc_code(text, known)
                if code:
                    found[kind] = (code, pno)
                    break
                continue
            m = rx.search(text)
            if m:
                found[kind] = (_norm(m.group(grp)), pno)
                break

    if "doc_code" in found:
        return found["doc_code"]
    # Raspberry Pi convention: "Release 4, build 30/06/2026" -- matches the manifest.
    if "release" in found and "build" in found:
        return f"{found['release'][0]}, build {found['build'][0]}", found["release"][1]
    if "published" in found:
        val, pno = found["published"]
        return f"Published {val}", pno          # manifest writes "Published July 2026"
    for kind in ("build", "release", "cover"):
        if kind in found:
            return found[kind]
    return None, None


def setup_ocr_env() -> str | None:
    """Put tesseract on PATH and set TESSDATA_PREFIX. Returns an error string or None."""
    exe = shutil.which("tesseract")
    if not exe:
        guess = Path.home() / "AppData/Local/Programs/Tesseract-OCR"
        if (guess / "tesseract.exe").is_file():
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + str(guess)
            exe = str(guess / "tesseract.exe")
    if not exe:
        return "tesseract not found on PATH"
    if not os.environ.get("TESSDATA_PREFIX"):
        base = Path(exe).parent / "tessdata"
        if base.is_dir():
            os.environ["TESSDATA_PREFIX"] = str(base)
    return None


def find_version(path: Path, known: frozenset[str] = frozenset()) -> dict:
    """Tier 3: printed edition string, plus where it came from."""
    try:
        import fitz
    except ImportError:
        return {"version": None, "source": None, "error": "PyMuPDF not available"}

    doc = fitz.open(path)
    try:
        n = doc.page_count
        # Front matter often carries the doc code a page or two past the cover (Rigol puts
        # UGA/PGA codes on the legal page), and Raspberry Pi puts the release table at the
        # back. Cover-only windows miss both.
        order = []
        for i in (0, 1, 2, 3, n - 2, n - 1):
            if 0 <= i < n and i not in order:
                order.append(i)

        pages = [(i, doc[i].get_text()) for i in order]
        v, pno = _extract(pages, known)
        if v:
            return {"version": v, "source": f"page {pno + 1} (text)", "error": None}

        # Image-only covers yield no text at all -- OCR is the documented fallback.
        ocr_err = setup_ocr_env()
        if ocr_err:
            return {"version": None, "source": None,
                    "error": f"no text version found and OCR unavailable: {ocr_err}"}
        ocr_pages = []
        for i in order:
            try:
                # Hold the page in a local: doc[i] returns a NEW object each call, and the
                # textpage only weakly references its owner, so re-indexing mid-sequence
                # raises "weakly-referenced object no longer exists".
                page = doc[i]
                tp = page.get_textpage_ocr(flags=0, dpi=300, full=True)
                ocr_pages.append((i, page.get_text(textpage=tp)))
            except Exception as e:  # noqa: BLE001
                return {"version": None, "source": None,
                        "error": f"OCR failed on page {i + 1}: {type(e).__name__}: {e}"}
        v, pno = _extract(ocr_pages, known)
        if v:
            return {"version": v, "source": f"page {pno + 1} (OCR)", "error": None}

        meta = (doc.metadata or {}).get("creationDate")
        if meta:
            return {"version": meta, "source": "PDF creationDate", "error": None}
    finally:
        doc.close()

    # Nothing printed in the document yielded a version. mtime is a last resort and is NOT
    # a published edition, so flag it as inconclusive: step 6 archives these as
    # `_unknown-<mtime>` rather than pretending the date is an edition.
    ts = path.stat().st_mtime
    import datetime
    return {"version": datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
            "source": "file mtime", "inconclusive": True, "error": None}


# --------------------------------------------------------------------------- check

def run_check(root: Path, only: str | None, as_json: bool) -> int:
    rows, warnings = parse_manifest(root)
    for w in warnings:
        print(f"WARNING  {w}", file=sys.stderr)
    if only:
        rows = [r for r in rows if only.lower() in r["local_path"].lower()]
    if not rows:
        sys.exit("no manifest rows matched")

    # Shared documents: rows sharing one official url are one unit -- fetch once.
    groups: dict[str, list[dict]] = {}
    no_url = []
    for r in rows:
        if not r["official_url"]:
            no_url.append(r)
        else:
            groups.setdefault(r["official_url"], []).append(r)

    # With --json, stdout must be parseable on its own; commentary goes to stderr.
    chatter = sys.stderr if as_json else sys.stdout
    print(f"{len(rows)} rows, {len(groups)} unique URLs, {len(no_url)} without a URL\n",
          file=chatter)

    results: list[dict] = []

    def tier0(url: str, members: list[dict]) -> dict:
        # Every path returns a dict; nothing escapes as an exception. HW_Docs is OneDrive-
        # synced, where a Files-On-Demand placeholder reports is_file() == True but can raise
        # on open() when offline or throttled -- and an exception here would propagate through
        # fut.result() and discard all 39 already-computed verdicts.
        try:
            # Existence is checked for EVERY row, before any comparison. Matching validators
            # say the remote is unchanged; they say nothing about the local copy still being
            # on disk, so comparing first would report "current" for a deleted document.
            missing = [m["local_path"] for m in members
                       if not (root / m["local_path"]).is_file()]
            if missing:
                return {"url": url, "members": members, "verdict": "LOCAL-MISSING",
                        "how": "-", "detail": "not on disk: " + ", ".join(missing),
                        "fresh": {}}

            # Shared-URL rows are physically duplicated copies of one document. The group
            # verdict is applied to all of them, so prove they really are identical first --
            # otherwise a sibling that diverged (e.g. a half-finished step 6) is invisible.
            if len(members) > 1:
                digests = {m["local_path"]: md5(root / m["local_path"]) for m in members}
                if len(set(digests.values())) > 1:
                    detail = "; ".join(f"{p}={d[:8]}" for p, d in digests.items())
                    return {"url": url, "members": members, "verdict": "SHARED-DIVERGED",
                            "how": "-", "detail": f"copies sharing this URL differ: {detail}",
                            "fresh": {}}

            fields, how, err = probe(url)
            stored = members[0]
            if err:
                return {"url": url, "members": members, "verdict": "PROBE-FAILED",
                        "how": how, "detail": err, "fresh": fields}
            verdict, reasons = compare(stored, fields)
            return {"url": url, "members": members, "verdict": verdict, "how": how,
                    "detail": "; ".join(reasons), "fresh": fields}
        except Exception as e:  # noqa: BLE001
            return {"url": url, "members": members, "verdict": "PROBE-FAILED",
                    "how": "-", "detail": f"tier0 error: {type(e).__name__}: {e}",
                    "fresh": {}}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(tier0, u, m): u for u, m in groups.items()}
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())

    # Tiers 1 and 2 for anything tier 0 could not settle.
    escalate = [r for r in results if r["verdict"] in ("changed", "incomparable", "PROBE-FAILED")]
    tmp = Path(tempfile.mkdtemp(prefix="hwcheck-"))
    try:
        for res in escalate:
            rep = res["members"][0]
            local = root / rep["local_path"]
            # One row's failure must never abort the run: 38 already-computed verdicts
            # would be discarded and the user would get a traceback instead of a report.
            try:
                dest = tmp / (hashlib.md5(res["url"].encode()).hexdigest() + ".pdf")
                ok, detail = download(res["url"], dest)
                if not ok:
                    res["verdict"] = "LINK-BROKEN"
                    res["detail"] = detail
                    continue
                if md5(local) == md5(dest):
                    res["verdict"] = "current"
                    res["detail"] = f"tier1 md5 match ({detail})"
                    continue
                # A truncated body can still start with %PDF-, so tier 2 may hit a
                # structurally broken file here.
                verdict, why = content_compare(local, dest)
                if verdict in ("corrupt", "unknown"):
                    res["verdict"] = "DOWNLOAD-CORRUPT"
                else:
                    res["verdict"] = "stale" if verdict == "stale" else "re-export"
                res["detail"] = f"tier2 {why}"
            except Exception as e:  # noqa: BLE001
                res["verdict"] = "PROBE-FAILED"
                res["detail"] = f"tier1/2 error: {type(e).__name__}: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    order = {"stale": 0, "SHARED-DIVERGED": 1, "DOWNLOAD-CORRUPT": 2, "LINK-BROKEN": 3,
             "LOCAL-MISSING": 4, "PROBE-FAILED": 5, "re-export": 6, "current": 7}
    flat = []
    for res in results:
        for m in res["members"]:
            flat.append({"local_path": m["local_path"], "verdict": res["verdict"],
                         "how": res["how"], "detail": res["detail"],
                         "known_version": m["known_version"], "url": res["url"],
                         "fresh": res.get("fresh", {})})
    for m in no_url:
        flat.append({"local_path": m["local_path"], "verdict": "NO-URL", "how": "-",
                     "detail": "no official url in manifest",
                     "known_version": m["known_version"], "url": "", "fresh": {}})
    flat.sort(key=lambda r: (order.get(r["verdict"], 9), r["local_path"]))

    if as_json:
        print(json.dumps(flat, indent=2))
    else:
        width = max(len(r["local_path"]) for r in flat)
        for r in flat:
            print(f"{r['verdict']:<14} {r['local_path']:<{width}}  "
                  f"[{r['how']}] {r['detail']}")

    counts: dict[str, int] = {}
    for r in flat:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("\n=== summary", file=chatter)
    for k in sorted(counts, key=lambda k: order.get(k, 9)):
        print(f"  {k:<14} {counts[k]}", file=chatter)
    print(f"  {'TOTAL':<14} {len(flat)}", file=chatter)

    # Non-zero exit only for things needing a human decision.
    bad = sum(counts.get(k, 0) for k in
              ("stale", "SHARED-DIVERGED", "DOWNLOAD-CORRUPT", "LINK-BROKEN",
               "LOCAL-MISSING", "PROBE-FAILED"))
    return 1 if bad or warnings else 0


# ---------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="tiers 0-2 across the manifest (writes nothing)")
    c.add_argument("--root")
    c.add_argument("--only", help="substring filter on local path")
    c.add_argument("--json", action="store_true")

    v = sub.add_parser("version", help="tier 3: printed edition string for one file")
    v.add_argument("path")
    v.add_argument("--root")

    args = ap.parse_args()
    root = resolve_root(args.root)

    if args.cmd == "check":
        return run_check(root, args.only, args.json)

    p = Path(args.path)
    if not p.is_absolute():
        p = root / args.path
    if not p.is_file():
        sys.exit(f"not a file: {p}")
    # Seed the doc-code ranker with prefixes this library already knows.
    res = find_version(p, known_code_prefixes(parse_manifest(root)[0]))
    if res["error"]:
        print(f"ERROR  {res['error']}")
        return 1
    if not res["version"]:
        print("inconclusive   (no printed version found)")
        return 1
    if res.get("inconclusive"):
        # ASCII only: Windows consoles still default to a locale codepage, which mojibakes
        # an em-dash here (and can raise UnicodeEncodeError under some configurations).
        print(f"INCONCLUSIVE - no printed version found; {res['source']} "
              f"gives {res['version']} (archive as _unknown-{res['version']})")
        return 1
    print(f"{res['version']}   ({res['source']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
