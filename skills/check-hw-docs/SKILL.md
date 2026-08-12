---
name: check-hw-docs
description: Check whether the HW_Docs PDFs are the current manufacturer versions, and replace any that are stale.
disable-model-invocation: true
---

Verify every document in `HW_Docs` against its manufacturer's published version, then
replace the stale ones — archiving what they replaced.

Manifest: `HW_Docs/context.md` — the cached official URL and last-seen signature per file.
It is the reason this skill is cheap; keep it current (steps 5-6).

The mechanical work (tiers 0-2, and version extraction on demand) lives in `checker.py`
beside this file. **Do not re-derive it in shell.** It was extracted precisely because
hand-rolling the tier-0 loop produced 18 false "stale" verdicts on 2026-08-10; the script
encodes the per-host header quirks and parsing traps that caused them.

## Tooling

    python3 ~/.claude/skills/check-hw-docs/checker.py check
    python3 ~/.claude/skills/check-hw-docs/checker.py version "<path relative to HW_Docs>"

`check` runs tiers 0-2 over every manifest row and prints a verdict table. It **writes
nothing** — not to `context.md`, not to any document. Tier-1 downloads go to a temp dir it
removes on exit. Exit status is defined once in step 2 — do not infer it from this section.

Useful flags: `--only SUBSTR` to filter by path, `--json` for machine-readable output,
`--root DIR` to override root detection.

Invoke it exactly as spelled above — the form is load-bearing. `settings.json` carries the allow
rule `Bash(python3 ~/.claude/skills/check-hw-docs/checker.py:*)`, and Bash permission rules are
literal string matches: `~` is **not** expanded for them (home-relative expansion is documented
only for Read/Edit/Cd path patterns). So `python`, `py`, `$HOME/…`, an absolute path, or a
`cd`-then-relative form all stop matching the rule and turn a silent run into a permission prompt.

The script finds the HW_Docs root itself, in order: `--root` → `$HW_DOCS` →
`$OneDrive/Documents/HW_Docs` → `$HOME/HW_Docs`, taking the first containing a
`context.md`. Nothing is hardcoded, so this works on the Linux copy of the library too.

For any PDF work outside the script, prefer PyMuPDF (`import fitz`) — it needs no PATH
setup and no subprocess. Only OCR needs external tooling; `checker.py` handles that
itself. If you do need Poppler's binaries directly, try the bare command first and fall
back to a glob, never a hardcoded version:

    command -v pdftotext || POPPLER=$(ls -d ~/AppData/Local/Microsoft/WinGet/Packages/oschwartz10612.Poppler_*/poppler-*/Library/bin | sort -V | tail -1)

Note the Read tool's PDF path depends on `pdftoppm`; if that is absent the tool cannot
render PDFs at all. Use PyMuPDF via Bash instead.

## Host behaviour (already handled by the script — context for interpreting output)

| Host | HEAD | Returns | Notes |
|---|---|---|---|
| `pip-assets.raspberrypi.com` | 200 | `etag`, `last-modified` | **Never** sends `Content-Length` on HEAD. A stored `size` there came from a GET and is for validating downloads, not comparison. The raspberrypi.com redirect chain rejects any UA containing `Python-urllib` with 403 — which hop issues it was never established, since it was only ever observed through a followed chain. |
| `download.rigol.com` | 200 | all three | |
| `www.rigol.com` | 200 | `last-modified`, `content-length` | Never sends `etag`. |
| `beyondmeasure.rigoltech.com` | **403** | — | Honours ranged GET: a 1-byte request returns the true size in `Content-Range`. Needs `Referer: https://rigolna.com/support/downloads/`. Redirects onward to an Act-On CDN. |

A field a host never returns is **not comparable** — never treat its absence as a change.

## Shared documents

Some manifest rows intentionally share one `official url` — a document the manufacturer
publishes once but that this folder keeps as physically duplicated copies across product
folders (e.g. a combined DG800/DG900 Pro Programming Guide). `checker.py` groups rows by
URL and fetches each once, then md5-compares **all** the group's local copies against each
other before comparing anything to the remote — so a sibling that drifted out of step is
reported as `SHARED-DIVERGED` rather than inheriting the first member's verdict.

When acting on a group verdict, route **each** member file through step 6's full procedure
(archive → verify the archive → overwrite → update `known version`) — never overwrite a
shared-group member directly from this section. Replace **every** copy sharing the URL and
update **every** one of their `known version` fields identically in the same pass. Never let
two rows sharing an `official url` diverge.

## 1. Reconcile

Run `checker.py check`. Then list the PDFs on disk and confirm every one is either a
manifest row or an unlisted file (step 4). `Outdated_Docs/` is the archive, not a product
folder — exclude it.

Done when every PDF on disk is classed as listed or unlisted.

## 2. Read the verdicts

The escalation is already done. Each tier costs about ten times the one above it, which is
why the script stops at the first conclusive signal:

| Verdict | Meaning |
|---|---|
| `current` | Validators match (tier 0), or bytes match (tier 1). Nothing to do. |
| `re-export` | Bytes differ but page count and full extracted text are identical — the publisher re-exported the same document. **Not stale.** Leave the file alone; report it in its own group so a skipped file is never mistaken for an unexamined one. |
| `stale` | Content genuinely differs — page count or text changed. Go to step 3. |
| `SHARED-DIVERGED` | Rows sharing one `official url` have local copies that are **not** byte-identical. Fix the duplication before trusting any verdict for that group — via step 6 per member file, never by direct overwrite. See Shared documents. |
| `DOWNLOAD-CORRUPT` | Either the downloaded copy or the existing local file needed MuPDF repair, so no comparison is safe — read `detail` to see which. If it's the download, retry; if it persists, the published file is damaged. If it's the **local** file, that copy is already known-bad: proceed with step 6 to replace it. |
| `LINK-BROKEN` | Body was not a PDF, the transfer was short of its `Content-Length`, or the PDF had no `%%EOF` trailer. Handle as an unlisted file (step 4). |
| `PROBE-FAILED` | Network or HTTP error, or an error during tier 1/2. Investigate before drawing any conclusion — this is not evidence about the document. |
| `LOCAL-MISSING` | Manifest names a file that is not on disk. Checked for **every** row before any network call. |
| `NO-URL` | No `official url` in the manifest. Handle in step 4. |

Exit status is non-zero exactly when `stale`, `SHARED-DIVERGED`, `DOWNLOAD-CORRUPT`,
`LINK-BROKEN`, `LOCAL-MISSING`, or `PROBE-FAILED` appears, or a parse warning fired.
`NO-URL`, `current`, and `re-export` never affect it — the exit code answers "did anything
about a *document* change or fail", and a permanently unobtainable document would otherwise
pin every future run at non-zero. **So always scan the table for `NO-URL` rows regardless of
the exit code.**

Two things that are never merely cosmetic:

- **A `WARNING` on stderr about a row being ignored.** A cell containing a literal `|`
  (usually `notes`) makes the row unparseable, and an ignored row is a document that is
  silently no longer checked at all. Fix the manifest before trusting the run's coverage.
- **A large fraction of rows suddenly reporting `stale`.** Distrust the run before
  distrusting the documents — that pattern is what a checker bug looks like. On 2026-08-10 a
  hand-rolled version of this check reported 18 of the 28 URLs it checked as stale; every one
  was a parsing artefact.

## 3. Version strings for stale files only

Two things are needed per stale file: what the version moved from and to (for the report),
and the old version string (for the archive filename in step 6).

    python3 ~/.claude/skills/check-hw-docs/checker.py version "<path>"

This runs inline: text extraction across the first four and last two pages, preferring a
publication code (`PCX01100-2022-09`) → `Release N, build <date>` → `Published <Month
Year>` → cover date, then OCR of the same pages for image-only covers, then the PDF
creation timestamp, then mtime. It reports where it found the value, or `inconclusive`, or
an explicit OCR **tooling** error — a tooling failure is not `inconclusive`.

Escalate to a subagent (`model: haiku`, one file each) **only** when more than two large
multi-hundred-page PDFs need OCR in the same run; that batching failure is the reason the
rule exists. For one or two files, inline is cheaper than spawning anything.

Known limitation: some Rigol manuals carry their doc code only on Rigol's download page,
not in the PDF — `DHO1000_UserGuide.pdf` yields just `Dec. 2024`, though the manifest
records `UGA32103-1110 (2024-12-30)`. When the manifest already holds a code, keep that
format rather than downgrading the row to a bare date.

## 4. Unlisted, NO-URL, and link-broken files

For each, tell the user the filename and what is missing, then ask whether to research its
official URL now. Research only the ones they approve.

**Link provenance is what makes a source official, not the hostname.** A URL qualifies if
you reached it by following a link that originates on the manufacturer's own site — even
when the final URL sits on a CDN or marketing platform. This is how the six portal-only
Rigol files were resolved: `rigolna.com/support/downloads/` links out to Act-On assets on
`beyondmeasure.rigoltech.com`. Record the originating page in the row's `notes` so the
provenance stays auditable.

**Confirm with the user the first time a link leads to a source host not already present
in the manifest**, naming the host. Transparent onward redirects from an already-approved
host do not need re-confirmation, but record the final delivering host in `notes`.

Where the manifest names a portal page but no direct asset URL, that portal is the place to
start. Files the user declines stay unlisted and are reported as **not checked** — never
silently as current.

**Two official sources can disagree.** A vendor's regional arms may publish different
editions of the same document, and which one leads varies per document. Compare printed
edition identifiers, not file dates, before repointing a row. Verified 2026-08-10: all four
DS1000Z-E docs on Rigol NA are byte-identical to editions already superseded in
`Outdated_Docs/`, so repointing those rows there would be a downgrade.

Done when the user has answered for each one.

## 5. Report, then ask

Present one table: file | local version | official version | verdict. Group by verdict so
stale reads first, and state the counts. Re-exports and not-checked files each get their
own group.

Then ask whether to update the stale files.

Refresh the manifest for every entry checked, regardless of the answer: current `etag`,
`last-modified`, `size`, and today's date as `verified`. These describe the official file,
not the local one, so they update no matter what the user decides — this is what keeps the
next run on tier 0. **Do not touch `known version` here.** It describes what is actually on
disk, which only step 6 changes, and only for files it replaces.

After editing, diff the manifest to confirm the columns you must NOT touch really did not
move — `local_path` ($2), `official_url` ($3), `known_version` ($5) and `notes` ($9):

    diff <(awk -F'|' '/^\| .*\.pdf/{print $2"|"$3"|"$5"|"$9}' context.md.bak) \
         <(awk -F'|' '/^\| .*\.pdf/{print $2"|"$3"|"$5"|"$9}' context.md)

Identical output proves only `verified`/`etag`/`last-modified`/`size` changed. The pattern must
stay anchored to `^| `: an unanchored `/\.pdf/` also matches prose bullets under `## Notes` that
merely name a PDF (40 lines instead of 39), which is harmless only until one of them contains a
literal `|`.

Await an answer. Proceed to step 6 only on approval; otherwise the run ends here — the
declined file's `known version` stays exactly as it was, since the file didn't move.

## 6. Update on approval

Per approved file, in this order:

1. Copy the local file to `HW_Docs/Outdated_Docs/`, appending its own version to the name:
   `DS1000Z-E_UserGuide_EN.pdf` (Mar 2020) → `DS1000Z-E_UserGuide_EN_2020-03.pdf`; with a
   publication code, `DHO1000_QuickGuide_en_QGA32103-1110.pdf`. Where step 3 was
   inconclusive, fall back to `_unknown-<mtime>`.
2. `stat` the original local file and the archive copy and confirm the byte sizes match,
   **before** overwriting anything. Compare against the original file on disk — *not* the
   manifest's `size` column, which after step 5 describes the new official file and will
   therefore differ for every genuinely stale document.
3. Re-download the official file and copy it over the original, keeping the existing
   filename. (`checker.py` deletes its temp dir, so the tier-1 copy is gone by now.)
4. Only now, with the new file confirmed on disk, update that entry's `known version` in
   the manifest. This is the only step that ever writes `known version` — write it here and
   nowhere else, so it can never describe a file state that hasn't happened yet.

Existing contents of `Outdated_Docs` are left as they are — version-suffixed names make
collisions impossible.

Report each archived path and each replaced path.

Done when every approved file has an archive copy, a replaced original, and an updated
`known version` in the manifest — all three confirmed, not assumed.
