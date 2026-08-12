---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
---

## Where to save

Before dispatching anything, determine where the cited notes should live — this decision
happens now, not inside the backgrounded agent below, so it never blocks on a question
mid-run:

1. Check for `docs/research/` in this repo. If it has existing files, follow their
   naming pattern — no need to ask. Treat an empty `docs/research/` the same as it not
   existing (fall through to step 2) — there's no pattern yet to follow.
2. If it doesn't exist (or exists with nothing in it), ask the user directly:
   "Where should this research file be saved? Default: `docs/research/NNNN-<slug>.md`."
   If this repo also has a `docs/adr/` folder, append: "(same numbered pattern as this
   repo's ADRs)" — otherwise leave that clause out; it's a coincidence of convention in
   some repos, not something to assume everywhere. Use their answer, or the default if
   they confirm it.
3. NNNN is a zero-padded sequence number (0001, 0002, ...), continuing from the highest
   existing file in that folder, or starting at 0001 if empty. <slug> is a short
   kebab-case version of the research question.

## Research

With the save path settled, spin up a **background agent** to do the research, so you
keep working while it reads. Its job:

1. Investigate the question against **primary sources** — official docs, source code,
   specs, first-party APIs — not a secondary write-up of them. Follow every claim back to
   the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source, at the path
   already determined above — creating the folder first if it doesn't exist yet.
