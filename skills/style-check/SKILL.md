---
name: style-check
description: Check code comments, documentation, plans, PR comments, customer-facing documents, or git commit messages against the user's personal style rules in CLAUDE.md, and report violations — the offending text plus the exact rule it breaks. Use when asked to check or review one of those six against "my style guide" or "CLAUDE.md rules," or before finalizing a plan, doc, PR comment, or commit. Not for chat-response tone or fact-sourcing checks (Communication style / Evidence and sourcing) — those need live judgment, not a text scan.
---

# Style check

Compare a piece of text against the user's own style rules and report where it
breaks them. This is a single read-and-compare pass — no exploration, no
tool loop, no subagent — because the rules are prose-shape checks, not
factual verification.

## Rule source

The five rule sets live in `CLAUDE.md`'s `## Writing style — comments, docs,
plans, PR comments` section (covers comments/docs/plans/PR comments) and its
`## Git commits` section. That section opens with an "All categories"
preamble that applies to every category below it, including Git commits' spirit.
That file is normally already loaded into context automatically. If it isn't
visible (e.g. running headless without the user's CLAUDE.md), read
`~/.claude/CLAUDE.md` and pull those two sections before checking
anything — don't check against the summaries below, they're a
quick-reference, not the authoritative wording.

Customer-facing documents are the exception: their rules live in the **Rules** section of
the `customer-docs` skill (`~/.claude/skills/customer-docs/SKILL.md`). Read that file when
checking this category.

## Pick the category

| Input looks like | Category |
|---|---|
| File under a `plans/` directory, or opens with a `## Context` section | Plans |
| A source code file | Code comments — check only comment lines/blocks, ignore the code itself |
| A commit message, `git log` output, or `.git/COMMIT_EDITMSG` | Git commits |
| A PR/review comment, drafted or posted | PR comments |
| Release notes, a customer communication, or a customer-facing deck's text | Customer-facing |
| Any other prose/markdown/doc text | Documentation |

If the user names the category explicitly, use that instead of guessing.

## What each category forbids

**All categories**
- Off-topic or tangential content that doesn't change what the reader
  thinks or does.
- A code excerpt where a `file:line` citation + prose explanation of the
  mechanism would do.
- A paragraph that's really a list of distinct items, left as prose instead
  of bullets.
- A sentence the reader must re-read to parse: it stacks distinct items or
  nests clauses.
- A bullet holding two separate changes, findings or decisions. Inline
  supporting detail (a reason, a consequence, a prior value) is not a second
  point.
- A stated range or condition that omits a case the text elsewhere shows the
  behaviour covers.

**Code comments**
- Narrating how the code got there instead of describing it as it now
  stands. Flag: "used to be X", "changed for Y", "added for the Z fix",
  "previously…", any comment answering "what happened" instead of "what is."

**Documentation**
- Adjectives/qualifiers that don't carry meaning ("simply", "just", "very").
- Development-process narrative: "a review found…", dates, "we decided to…".
- "Was X, changed because Y, now Z" phrasing — should collapse to "Z, because
  [reason]."
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
- Verbose or hedgy prose where terse, plain language would do.

**PR comments**
- More than one distinct defect blended into a single paragraph — should
  split into bullets or separate comments.
- No mechanism or concrete consequence stated (e.g. "this looks wrong" with
  nothing explaining why or what breaks).
- Evidence that doesn't change the verdict (a repro or line reference
  included even though it settles nothing).
- Contrastive reframing ("it's not X, it's Y") where the PR/author didn't
  claim X, or Y isn't actually in tension with it.
- Epigram-shaped prose — slogans, slide-title sentences, bolded
  pseudo-principles in place of the plain observation.

**Git commit messages**
- Message doesn't lead with what changed, briefly how.
- Extra context/backstory that isn't strictly necessary to understand the
  change. A short "why" for a non-obvious design choice IS necessary context
  — don't flag that; only flag backstory the reader doesn't need at all.
- A body covering more than one unrelated change with no lead naming all of
  them.

**Customer-facing**
- The `customer-docs` **Rules** and the All-categories rules, checked against
  the text and any supplied predecessor. Skip a rule that needs product facts
  the text doesn't give (real scale, scope, which terms the reader meets,
  whether a figure is a field finding) unless the text contradicts itself;
  list skipped rules once under "Not checkable from text". Skip the Slides
  rules for text-only input.
- A predecessor section or label dropped or renamed without evident reason.
  Check only when the predecessor is supplied; otherwise report "Predecessor
  not checked." Length and tone differences are not violations.

## Report format

For each category checked, report:

- **Clean**: one line — "No violations found."
- **Violation**: quote the offending text (short excerpt, not the whole
  file), name the specific rule broken, and give a one-line fix.

A flag quotes text that clearly breaches a named rule's wording. Borderline
cases, constructions a rule permits, and word order no rule names pass; most
rules produce no flag. A flag that rests on an assumption about the product is
reported as a question for the author.

Check the text against every rule listed for its category before reporting
— a rule you don't check against silently passes. Don't stop at the first
violation found, and don't rewrite the whole document — flag and suggest,
let the user decide.
Group violations by category if more than one input/category was checked in
the same pass.
