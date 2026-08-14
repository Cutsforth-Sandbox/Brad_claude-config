---
name: differential-diagnosis
description: Test whether a diagnosis is correct and the chosen fix right, by eliminating competing explanations on evidence. Use when asked to challenge a diagnosis, verify a root cause, or judge whether a fix solves the real problem.
---

# Differential diagnosis

Input: a stated problem plus a diagnosis and/or a proposed or implemented
fix — a diff, plan, ticket, or verbal claim. Output: a verdict on the
diagnosis and one on the approach, each with evidence.

Three fresh agents, fixed roles, defined below. Every hand-off between stages
is the **claim table** — claims plus quoted evidence — never conversation
history; that is what keeps this skill cheap. All other work runs inline in
this context.

## 1. State the claim (inline)

Reconstruct from the available intent sources (conversation, commit messages,
PR body, ticket, plan file): the observed **symptom**, the claimed **cause**,
and the chosen **remedy** — three separate statements. Ask for whichever is
missing rather than inferring it.

Done when all three are stated and confirmed.

## 2. Outside view (one `Explore` agent, blinded)

Spawn one `Explore` agent carrying **only the symptom** and pointers to the
repo/logs — never the claimed cause or remedy; a generator that has seen the
suggestion anchors to it. Its brief: name every mechanism that could produce
this symptom, each with the evidence that would distinguish it (a log line, a
repro variation, a code path, a measurement).

Merge its candidates with the claimed cause into one differential table.

Done when every candidate has a distinguishing test.

## 3. Test (inline, cheapest evidence first)

Work the table cheapest-evidence-first. Look facts up in the environment
(code, logs, git history, docs — per the sourcing order in
`~/.claude/CLAUDE.md`) rather than asking; send grep-shaped lookups to haiku
subagents; run a repro or measurement where one settles a candidate.
Eliminate only on evidence, and record the quote in the table.

Done when one candidate survives, or the survivors are named as unresolved
with the missing evidence stated.

## 4. Skeptic (one fresh subagent, session model)

Hand the claim table — nothing else — to a fresh subagent on the session
model (capability floor: it is checking session-model work). Its brief:
attack every claim; for each elimination and each surviving claim return
**holds**, **overturned** (quote the contrary evidence), or **untested**
(name the missing test). An overturned elimination returns to step 3 once; a
second overturn leaves the candidate unresolved.

Done when every table row carries the skeptic's verdict.

## 5. Final assessment (one fresh subagent, session model)

Hand the post-skeptic table to a second fresh subagent. Its brief: render the
**diagnosis verdict** — confirmed / replaced by X / unresolved (naming the
missing evidence) — and the **approach verdict**: does the remedy address the
surviving cause, checked against symptom-fix, wrong-layer,
existing-mechanism, and blast-radius failure modes; recommend keep, adjust
(named), or replace (named), each tied to table evidence.

Done when both verdicts name their evidence.

## 6. Report (inline)

Present the table: candidate cause | distinguishing evidence | verdict. Then
both verdicts and the recommendation. Flag every assumption that survived to
the end.

Done when the table, both verdicts, the recommendation, and every surviving
assumption all appear in the report.
