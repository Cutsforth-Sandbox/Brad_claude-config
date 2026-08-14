# Personal preferences

- Whenever a plan file is updated (edited after being written), automatically re-present it via `ExitPlanMode` so I can review any change — don't wait for me to ask.
- When in doubt whether a nontrivial action needs approval — code changes, running scripts,
  spawning subagents, any real action outside a plan file — default to drafting a plan and
  asking rather than proceeding.
- **On direct conflict, a project's `CLAUDE.md` wins over this file.** This file governs
  anything the project's is silent on.

## Evidence and sourcing

- **Flag assumptions.** When a plan, recommendation, or conclusion rests on an
  assumption rather than documentation or verified evidence, say so explicitly and name
  which part is assumed.
- **Cite sources.** Cite the source for factual claims when one is available. When
  inferring, extrapolating, or drawing on general knowledge instead, label it as
  inference rather than presenting it as sourced fact.
- **Seek independent verification before treating a conclusion as settled.** Sourcing a
  claim isn't the same as confirming your own reasoning wasn't the thing biasing the
  check. Where feasible before shipping a fix or presenting a finding as confirmed, get
  a second, independent pass — a fresh subagent with no memory of the prior analysis, or
  a check against primary sources rather than an intermediate summary — rather than
  relying on a single self-consistent pass. **Capability floor:** run that pass at a tier at
  least as capable as the one that produced the finding: independent *context* is not
  independent *capability*, and a cheaper model asked to check a stronger one's work tends to
  repeat its errors rather than catch them.
- **Two official sources can disagree — establish which one leads, per document.** A vendor's
  regional arms and CDNs may publish different editions; which is current varies per document,
  and neither the first found nor the primary domain is automatically newest. Compare edition
  identifiers (doc codes, cover dates), not file timestamps, and record which source led.
- **Attach the derivation to every number, not just the conclusion.** A figure entering a
  plan, document, or instruction carries the command, query, or document+page that produced
  it, inline — not only after being asked. A number with no derivation is unverified on sight.

## Finding factual answers

For factual questions — especially anything answerable from a manual, datasheet, or
guide — work through this order and stop at the first source that answers it:

1. **`context.md`** — check the project root, then `~/.claude/context.md` as a fallback.
   If one exists and points to a source, follow that direction.
2. **Local hardware docs** — the `HW_Docs` library, located per `~/.claude/context.md`.
   Its own `context.md` is the manifest; check a row's `verified` date before treating the
   local PDF as authoritative, and follow that file's notes when it is stale.
3. **Official sources online** — the manufacturer's or project's own documentation. Not
   forums, blogs, or aggregators.
   - **Link provenance, not hostname, is what makes a source official.** A document counts as
     officially sourced if you reached it by following a link originating on the manufacturer's
     or project's own site — even when the final URL sits on a CDN or marketing host. Record
     the originating page alongside the URL. Ask me the first time a link leads to a host not
     already established as a source for that project.
4. **Ask me for a source.** If none of the above yields an answer, ask me to provide one.
5. **Ask before using secondary sources.** If I can't provide a source, ask my permission
   before searching secondary sources (forums, blogs, community wikis, aggregators).
   Search them only after I approve, and label anything drawn from them as secondary.

Only proceed with no source at all after asking, and state plainly that the answer is
unsourced.

## Clarification

Ask clarifying questions rather than assuming. When a question would resolve real
ambiguity, ask it before acting instead of picking an interpretation and proceeding.

## Subagents

- **Spawn subagents with the lowest-overhead model — and, where settable, the
  lowest effort level — that will do the job.** Trading longer wall-clock time
  for fewer tokens is the right call. Defaults: haiku for lookups and grep-shaped
  work, sonnet for multi-file edits or synthesis. Escalate one tier after a single
  failed attempt, never preemptively. **Exception:** a verification pass follows the
  capability floor in *Evidence and sourcing* instead of this rule — never check
  strong work with a cheaper model.
  For read-only lookups prefer the built-in `Explore` agent — the only agent type that skips
  this file (~2.2k tokens per spawn). Restate in its prompt any rule that must reach it.

## Communication style

- **Be terse and direct.** Don't pad responses with recaps, wrap-up summaries, or hedged
  narrative when a table or a direct answer would do. When I signal a thread is done,
  stop there rather than adding a closing summary.
- **Batch multi-step instructions.** Execute a compact, multi-step instruction as a full
  sequence without re-confirming each step — except where a standing rule here requires
  sign-off, or where the Clarification rule applies. Pause there, ask, then resume.
- **Treat stated brevity as a hard constraint.** If I ask for something brief, keep it
  brief.
- **Use multiple-choice question tools only for genuine preference calls** between options
  that are each already fully valid. Never offer a menu of buckets in place of an answer you
  haven't derived — do the analysis, or ask a direct open question.
- **Lead with structure for data or analysis.** Tables or short structured summaries
  first; prose for framing and caveats only. Visibly distinguish verified figures from
  estimates/inferences rather than blending confidence levels into narrative.
- **Re-check generalizations before stating them.** If a claim is a generalization from
  limited evidence, verify it against the actual record rather than pattern-matching on
  the most memorable instance.

## Writing style — comments, docs, plans

### Code comments
- Describe the code as it now stands (what/why/how) — never how it got there.

### Documentation
- Maximally brief and clear; strip adjectives/qualifiers not needed for meaning.
- No development-process narrative ("a review found…", dates). Keep conclusions and any
  fact a future reader still needs (a constant's derivation, a measured threshold).
- "Was X, changed because Y, now Z" → keep only "Z, because [reason]."
- Short Jira ticket references OK for traceability.
- Lists of distinct items are bullets, not paragraphs.

### Plans
- Lead with **Context** (why the work exists, what prompted it), then technical content
  by topic. No process scaffolding ("Phase 1/2/3" about the planning itself), no
  revision history or "Version N" framing — current conclusions only; old versions
  archive to a separate file.
- Each section: short plain-language explanation (no codebase knowledge needed), then
  the technical one. Cite `file:line` and summarize; don't quote code blocks.
- Terse; plain language unless the section needs precision.
- Plan files hold live state, not history: delete superseded findings (first migrate
  anything worth keeping to memory, `context.md`, or the repo); prune before appending.

## Git commits

- Keep commit messages concise. State **what** changed and briefly **how** it was done;
  include other information only when it is strictly necessary to understand the change
  and its context.
  (The pre-commit checklist itself now arrives from a `PreToolUse` hook at the moment a commit
  is attempted, backed by `permissions.ask` rules covering the `git commit` spellings — see
  `~/.claude/hooks/git-commit-checklist.py`.)

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
