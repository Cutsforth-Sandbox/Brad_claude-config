#!/usr/bin/env python3
r"""Set hasTrustDialogAccepted: true on every ~/.claude.json project entry where it is false.

WHY THIS EXISTS
---------------
~/.claude.json keys per-project state by the *literal path string*, so one directory can end up
with two entries that differ only in spelling. Two ways that happens, both observed 2026-08-11
(field counts are from the real case; the paths are generalised):

    <drive>:\Users\<user>       8 fields   hasTrustDialogAccepted: True
    <drive>:/Users/<user>      29 fields   hasTrustDialogAccepted: False   <- separator differs
    <drive>:/git/<repo>        31 fields   hasTrustDialogAccepted: True
    <drive>:/git/<repo>        10 fields   hasTrustDialogAccepted: False   <- drive-letter case differs

The trust flag sits under one spelling while the session state sits under the other, so launching
from the "wrong" spelling re-prompts the trust dialog. Flipping the false ones to true makes either
spelling work.

WHY IT ONLY FLIPS AND NEVER DELETES
-----------------------------------
Deleting the duplicate is the obvious fix and it does not hold. A lowercase-drive-letter duplicate
was deleted once before, on 2026-08-06 (projects went 7 keys -> 6), and the application had
recreated it within days: something launches Claude Code with a lowercase drive letter. Worse, the
8-field home-directory entry above is a strict field *subset* of its 29-field sibling, and the only
value differing between them is the trust flag -- so "delete the one with fewer fields" would
destroy the only accepted trust dialog for that directory. Flipping is safe; deleting is not.

RUN IT WITH CLAUDE CODE CLOSED
------------------------------
The application owns this file and rewrites it from memory, so an edit made while it is running can
be silently discarded. Quit Claude Code first, run this, then relaunch.

    python3 ~/.claude/scripts/flip-trust-flags.py          # dry run, changes nothing
    python3 ~/.claude/scripts/flip-trust-flags.py --yes    # apply

Formatting is preserved deliberately: the file is 2-space-indented with LF endings and non-ASCII
written literally, so it is rewritten with indent=2 and ensure_ascii=False. Without that the diff
would cover all ~1,557 lines instead of the two booleans that changed.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

FLAG = "hasTrustDialogAccepted"
TARGET = Path.home() / ".claude.json"
BACKUP_DIR = Path.home() / ".claude" / "backups"


def main() -> int:
    apply = "--yes" in sys.argv[1:]

    if not TARGET.is_file():
        print(f"error: {TARGET} not found", file=sys.stderr)
        return 1

    raw = TARGET.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: {TARGET} is not valid JSON ({exc}); refusing to touch it", file=sys.stderr)
        return 1

    projects = data.get("projects")
    if not isinstance(projects, dict):
        print("error: no 'projects' object; refusing to guess at the structure", file=sys.stderr)
        return 1

    todo = [k for k, v in projects.items() if isinstance(v, dict) and v.get(FLAG) is False]

    print(f"{TARGET}  ({len(raw):,} bytes, {len(projects)} project entries)\n")
    for key, val in projects.items():
        state = val.get(FLAG) if isinstance(val, dict) else "<not an object>"
        mark = "  -> will set True" if key in todo else ""
        print(f"  {FLAG}={str(state):<5}  fields={len(val) if isinstance(val, dict) else '?':<3}  {key!r}{mark}")

    if not todo:
        print("\nNothing to do: no entry has the flag set to false.")
        return 0

    if not apply:
        print(f"\nDry run. {len(todo)} entr{'y' if len(todo) == 1 else 'ies'} would change.")
        print("Re-run with --yes to apply. Quit Claude Code first -- it owns this file.")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"claude.json.{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(TARGET, backup)
    print(f"\nBacked up to {backup}")

    for key in todo:
        projects[key][FLAG] = True

    trailing = "\n" if raw.endswith("\n") else ""
    TARGET.write_text(json.dumps(data, indent=2, ensure_ascii=False) + trailing, encoding="utf-8")

    # Verify the write rather than assuming it.
    check = json.loads(TARGET.read_text(encoding="utf-8"))
    bad = [k for k in todo if check["projects"][k].get(FLAG) is not True]
    if bad:
        print(f"error: flag still not true for {bad}; restore from {backup}", file=sys.stderr)
        return 1
    if len(check.get("projects", {})) != len(projects):
        print("error: project count changed; restore from the backup", file=sys.stderr)
        return 1

    print(f"Set {FLAG}=true on {len(todo)} entr{'y' if len(todo) == 1 else 'ies'}; deleted nothing.")
    print(f"Project entries still {len(check['projects'])}. Relaunch Claude Code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
