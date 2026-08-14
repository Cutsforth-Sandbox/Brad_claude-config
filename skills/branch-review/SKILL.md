---
name: branch-review
description: Multi-reviewer review of a branch, diff, or uncommitted changes — finds the branch's real parent, dispatches fresh reviewers against fixed briefs, verifies each finding, and labels what the branch introduced versus inherited. Use when asked to review a branch, a diff, or pending changes.
---

# Branch review

A run dispatches **fresh** reviewers against **briefs** — the prompts in
[`REVIEWERS.md`](REVIEWERS.md), pasted verbatim into each subagent rather than
paraphrased.

## 1. Parent

Name the branch's **parent** before diffing. List candidate refs, run
`git log --oneline <candidate>..HEAD` for each, and take the candidate whose
remaining commits are this branch's alone.

`@{upstream}...HEAD` goes empty on a pushed branch and `main...HEAD` credits
this branch with its parent's work, so neither substitutes for finding the
parent.

Reviewing pending work instead: `git diff HEAD`. A named PR, ref range, or path
overrides all of this.

**Done when** the parent is named and the stated diff command returns a
non-empty diff.

## 2. Triage

Run the diff once and hold its text. Read [`REVIEWERS.md`](REVIEWERS.md) and
triage each brief against what the diff touches, per its trigger line.

If `memory/<repo-slug>.md` exists (repo-slug = the repo's folder name), read
it first — a standing note there ("no external I/O in this repo") is a
triage reason exactly like a fresh trigger check, and can also surface a
suggested default for step 3's per-agent question.

Derive the **blast radius** here, once, for brief 3: the repo's shared surface
(files referenced from two or more entry points or top-level packages), and
every symbol the diff renamed, removed, or changed behaviorally.

**Done when** every one of the seven briefs is marked run or triaged-out with a
one-line reason naming what the diff lacks.

## 3. Confirm

Ask the user, in one `AskUserQuestion` call, before dispatching anything:

- **Sources** — which of these each reviewer receives. Default on: the full
  text of every applicable `CLAUDE.md`; the tests covering changed code, plus
  permission to run the suite; the `context.md` chain (repo, then
  `~/.claude/context.md`, then any document manifest it names). Default off:
  commit messages, PR body, and linked Jira issues. Brief 7 gathers the intent
  sources itself; they go to no other brief, and never through this context.
- **Roster** — the triage result from step 2, so the user can restore a
  triaged-out brief or drop a running one.
- **Repo agents** — one line per agent found under `.claude/agents/`, not one
  blanket toggle. Read each agent's own frontmatter/description and classify
  it: **narrow-angle** (built for one specific concern, shaped like a review
  brief) defaults on; **broad-persona** (a general domain expert, its own
  voice and format) defaults off. If step 2's memory named a prior answer for
  this agent, show it as the suggested default and ask anyway — never apply
  it silently. An approved persona agent's dispatch prompt in step 4 gets one
  added line: return findings as `file:line` + one-line summary + concrete
  failure scenario, not its native format.

State what reviewers will not receive.

**Done when** the user has answered.

## 4. Dispatch

Launch one **fresh** `general-purpose` subagent per brief on the roster, in
parallel. Each gets: the shared preamble from [`REVIEWERS.md`](REVIEWERS.md),
its own brief verbatim, the diff text from step 2 (or the diff command if the
text exceeds ~50 KB), the approved sources, and the parent from step 1. Brief 3
runs on Sonnet; the rest (including brief 6) inherit the session model.

**Exception — brief 7** dispatches as an `Explore` agent on Sonnet, carrying
only the shared preamble, its brief verbatim, the parent from step 1, and
`git diff --stat` output for the same range — never the full diff text or any
pasted sources. It gathers the intent sources and reads the hunks they point
at itself.

Fresh means no memory of any earlier review in this conversation. Where an
earlier pass reached a conclusion, hand it over as a claim to test.

Where subagent dispatch is unavailable, work each brief on the roster yourself,
sequentially, in this context, and name that in step 6.

**Done when** every brief on the roster has returned candidates or `(none)`.

## 5. Verify

Group candidates by `file:line`; send each location to one reviewer that did not
produce it, returning per candidate: **confirmed** (name the inputs and the
wrong output, quote the line), **plausible** (mechanism real, trigger
uncertain — say what would settle it), or **refuted**. A candidate already
backed by a **repro** is confirmed and skips this step.

Reach for **plausible** whenever the triggering state is realistic — a
concurrency race, nil on a rare-but-reachable path (error handler, cold cache,
absent optional field), falsy-zero read as missing, off-by-one on a boundary the
code does not exclude, a retry storm, a partial failure, a regex or allowlist
that lost an anchor. Reserve **refuted** for what the code itself settles:
quote the line that contradicts the claim, show the type or constant that makes
it impossible, cite the guard in this diff that handles it, or state that the
effect is unobservable.

**Done when** every candidate carries a verdict.

## 6. Report

Before assembling: check whether any brief triaged out in step 2 on a genuinely
borderline call, and note it in one line if so. Check whether any surviving
finding rests on an assumption about runtime behavior nothing in this review
actually exercised — a claim verified by reading rather than by repro — and
mark that distinction on the finding rather than presenting every verified
finding as equally certain.

Rank confirmed above plausible, and correctness above cleanup. Tag each
finding's **origin**: introduced by this branch, inherited from the parent, or a
gap worth flagging regardless. Name the refuted candidates in one line.

**Done when** every candidate appears in the report or in that refuted line,
every brief that returned `(none)` is listed as having found nothing, and any
brief worked in-context rather than by subagent is named as such.

Then write or update `memory/<repo-slug>.md` (create the file if it doesn't
exist yet — every repo starts with none): briefs that triaged out and why (if
that reason is a standing repo fact, not a one-off diff shape), a recurring
defect location if this run's finding lands in the same module as a prior
one, a false-positive pattern this run's verifier refuted that has been
refuted before, and any repo-agent choice made in step 3. Keep it short — a
calibration note for the next run, not a review log. This step is best-effort:
the report in this step is already complete without it, so a write failure
here is worth a one-line mention, never a reason to redo the report.
