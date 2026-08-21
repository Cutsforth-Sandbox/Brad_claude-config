---
name: style-check
description: Check code comments, documentation, plans, or git commit messages against the user's personal style rules in CLAUDE.md, and report violations — the offending text plus the exact rule it breaks. Use when asked to check or review one of those four against "my style guide" or "CLAUDE.md rules," or before finalizing a plan, doc, or commit. Not for chat-response tone or fact-sourcing checks (Communication style / Evidence and sourcing) — those need live judgment, not a text scan.
---

# Style check

Compare a piece of text against the user's own style rules and report where it
breaks them. This is a single read-and-compare pass — no exploration, no
tool loop, no subagent — because the rules are prose-shape checks, not
factual verification.

## Rule source

The four rule sets live in `CLAUDE.md`'s `## Writing style — comments, docs,
plans` section (covers comments/docs/plans) and its `## Git commits` section.
That file is normally already loaded into context automatically. If it isn't
visible (e.g. running headless without the user's CLAUDE.md), read
`~/.claude/CLAUDE.md` and pull those two sections before checking
anything — don't check against the summaries below, they're a
quick-reference, not the authoritative wording.

## Pick the category

| Input looks like | Category |
|---|---|
| File under a `plans/` directory, or opens with a `## Context` section | Plans |
| A source code file | Code comments — check only comment lines/blocks, ignore the code itself |
| A commit message, `git log` output, or `.git/COMMIT_EDITMSG` | Git commits |
| Any other prose/markdown/doc text | Documentation |

If the user names the category explicitly, use that instead of guessing.

## What each category forbids

**Code comments**
- Narrating how the code got there instead of describing it as it now
  stands. Flag: "used to be X", "changed for Y", "added for the Z fix",
  "previously…", any comment answering "what happened" instead of "what is."

**Documentation**
- Adjectives/qualifiers that don't carry meaning ("simply", "just", "very").
- Development-process narrative: "a review found…", dates, "we decided to…".
- "Was X, changed because Y, now Z" phrasing — should collapse to "Z, because
  [reason]."
- Paragraphs where the content is really a list of distinct items — should
  be bullets.
- (Short Jira ticket references are fine — not a violation.)

**Plans**
- Missing or misplaced **Context** section (must be first).
- Missing **Outline** section immediately after Context: a table (Section |
  Summary) naming every later section with a 1–2 sentence summary. Check
  that summaries name their own gating dependency inline (not collected in a
  separate blockers list) and that the outline distinguishes sections that
  can proceed immediately from ones waiting on something.
- "Phase 1/2/3" framing describing the *planning process itself* (not a
  legitimate technical rollout phase).
- Revision history / "Version N" framing instead of current-state-only
  content.
- Quoted code blocks where a `file:line` citation + summary would do.
- Verbose or hedgy prose where terse, plain language would do.

**Git commit messages**
- Message doesn't lead with what changed, briefly how.
- Extra context/backstory that isn't strictly necessary to understand the
  change. A short "why" for a non-obvious design choice IS necessary context
  — don't flag that; only flag backstory the reader doesn't need at all.
- A body covering more than one unrelated change with no lead naming all of
  them.

## Report format

For each category checked, report:

- **Clean**: one line — "No violations found."
- **Violation**: quote the offending text (short excerpt, not the whole
  file), name the specific rule broken, and give a one-line fix.

Check the text against every rule listed for its category before reporting
— a rule you don't check against silently passes. Don't stop at the first
violation found, and don't rewrite the whole document — flag and suggest,
let the user decide.

Group violations by category if more than one input/category was checked in
the same pass.
