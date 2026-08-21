#!/usr/bin/env python3
"""PostToolUse hook: flag a plan file missing its required Outline section.

Fires after Write/Edit to a file under plans/. Reads the file back from disk
(not tool_input) so Edit's partial old_string/new_string doesn't matter --
only the resulting file does. Structural check only: heading order and
Outline-table coverage. Never blocks the save; this is advisory context for
the next turn, same division of labour as git-commit-checklist.py.
"""
import json
import re
import sys
from pathlib import Path

try:
    data = json.load(sys.stdin)
    file_path = Path(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    sys.exit(0)

# settings.json's `if` prefilter (Write/Edit `**/plans/*.md`) is best-effort --
# it can still fire on an unrelated "plans" directory in another project -- so
# this is the real, precise scope check: only ~/.claude/plans/*.md.
plans_root = Path.home() / ".claude" / "plans"
try:
    file_path.resolve().relative_to(plans_root.resolve())
except (ValueError, OSError):
    sys.exit(0)
if file_path.suffix != ".md":
    sys.exit(0)

try:
    # utf-8-sig: a BOM would survive plain utf-8 and glue itself onto the
    # first line, making a leading "## Context" heading unmatchable.
    text = file_path.read_text(encoding="utf-8-sig")
except Exception:
    sys.exit(0)

# Strip fenced code blocks first -- a plan that shows example markdown (a
# sample SKILL.md, a sample plan) can contain "## " lines that are quoted
# text, not real headings of this document. Splitting on the fence marker
# keeps the even-indexed (outside-fence) chunks; an unterminated fence drops
# its trailing chunk instead of leaking quoted headings into the check.
text_no_fences = "".join(text.split("```")[::2])

# Match objects, not just captured text, so the table slice below uses real
# character positions instead of re-searching for a hardcoded "## Outline"
# string -- which broke on any casing/spacing the opening regex itself
# already tolerated (e.g. "## outline").
matches = list(re.finditer(r"^##\s+(.+)$", text_no_fences, re.MULTILINE))
if not matches:
    sys.exit(0)
headings = [m.group(1).strip() for m in matches]
# A heading may be written as "N. Name" (CLAUDE.md's own "numbered Outline
# section" convention, also used elsewhere for numbered steps) -- compare on
# the name only, so numbering doesn't make a compliant heading look wrong.
norm = [re.sub(r"^\d+\.\s*", "", h).lower() for h in headings]

problems = []
if norm[0] != "context":
    problems.append("first section isn't Context")
elif len(norm) < 2 or norm[1] != "outline":
    problems.append("no Outline section immediately after Context")
else:
    table_end = matches[2].start() if len(matches) > 2 else len(text_no_fences)
    table = text_no_fences[matches[1].end():table_end].lower()
    missing = [h for h, n in zip(headings[2:], norm[2:]) if n not in table]
    if missing:
        problems.append(f"Outline table doesn't list: {', '.join(missing)}")

if problems:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            f"{file_path.name} was just saved under plans/. The user's plan "
            f"format requires Context first, then an Outline table naming "
            f"every later section. This file: {'; '.join(problems)}."
        ),
    }}))
