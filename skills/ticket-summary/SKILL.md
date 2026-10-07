---
name: ticket-summary
description: Ticket summary PDF for a delivered Jira ticket, read by outsiders to the work. Use when asked for a ticket or task summary, or to regenerate one.
---

# Ticket summary

An internal PDF that explains one delivered ticket to an **outsider**: a manager or a
colleague from another team, without the technical background, who never saw the work. The
user presents it and retells it from the page.

## Format

**File:** `~/Documents/Ticket_Summaries/Sprint-<NN>_<start>_<end>/<KEY>_Summary.pdf`, with its
Markdown sources in `~/Documents/Ticket_Summaries/Sprint-<NN>_<start>_<end>/<KEY>/`. `<NN>`,
`<start>` and `<end>` come from the ticket's Jira sprint (field `customfield_10020`: the number
from the sprint's name, zero-padded to two digits, and `startDate`/`endDate` as YYYY-MM-DD in
the user's local time). No parentheses: every shell command would have to quote them. A
ticket carried across sprints goes in the sprint it was delivered in. Example:
`Sprint-07_2026-01-05_2026-01-16/`.

**Headings:** the parts 1–2 file opens with the title as its H1:
`<KEY>: <the ticket's subject in plain words>`. Parts 1 and 2 are H2 headings, and part 2's
subsections are H3. Each output file opens with the output's title as its H1. Headings
carry no numbers.

The three parts below come in this order. Part 1's items and each "How to read this" list
are fixed, except where marked "Present only when". Part 2's subsections are the default
shape; a ticket's own work may add, merge or drop one.

**1. Jira ticket**
- A metadata table:
  - the ticket key, linked, with its Jira title;
  - type and priority;
  - the assignee;
  - the deliverable: one row per PR, with its merge date, commit and approver, or the form
    and date of a deliverable that isn't a PR.
- **Problem:** one plain sentence saying what was wrong or missing, with its impact
  quantified where it can be.
- **Goal:** one sentence.
- An "Acceptance criterion | Outcome" table. Each criterion is paraphrased plainly, and one
  derived because the ticket has none is labelled as derived. Each outcome is short and
  names its evidence (a test, run or document). A partly met criterion says what is still
  open and its priority.
- **Changes from the ticket's plan:** bullets, each stated as the end state. Present only
  when the work deviated from the plan.

**2. Summary of work done**, written for the outsider:
- plain language;
- an analogy where a mechanism is abstract;
- short bullets with bold lead-ins;
- outcomes and their evidence.

Its subsections:
1. **The problem:** what was wrong and why it mattered, then the causes in a few bullets.
2. **What we changed:** one numbered item per change. Each says who made it and whether it
   is part of the deliverable, gives the mechanism in plain words, and states its effect.
3. **What the outputs show**, titled for the outputs it covers: what they mean for the
   work, in plain words, then one bold line stating the overall result. Present only when
   part 3 exists.
4. **What changes going forward:** workflow changes (or "none"), one-time costs, behaviour
   when something fails, limits, and caveats with their ticket references.

**3. Outputs**
- The material this ticket's work produced that explains it: tables, charts, diagrams,
  test results, before/after comparisons, screenshots. Each output earns its place by
  explaining a named part of the work.
- Each output is its own page (its own Markdown file): its title, the output, then a short
  list under an H2 "How to read this" heading, covering:
  - what it shows;
  - how to interpret it;
  - its sources;
  - a worked example: present only when the reading isn't obvious;
  - how its derived values were computed: present only when it has any;
  - how it relates to current behaviour: present only when that changed after it was
    produced.
- Refer to another output by its title; the PDF has no page numbers.

## Rules

**Overrides**
- These Rules replace `CLAUDE.md`'s inline-derivation rule (in *Evidence and sourcing*)
  and two of its *Documentation* rules: the one on development-process narrative, and
  "Was X, changed because Y, now Z".

**Content**
- **Evidence:** every claim and figure traces to its evidence (a test, run, log,
  measurement or document). A figure no output shows has its source and derivation in the
  message that presents the draft. Totals and shares agree with each other.
- **Conditions:** state the conditions a result depends on (environment, hardware,
  configuration, inputs), so the reader can tell whether it applies to their case.
- **Names and terms:** use the real repo, product and component names. Define each, and any
  other technical term, at its first use unless the reader already knows it.
- **Context:** a change carries its context alongside its outcome: what the outsider will
  notice differently, or what it follows from. An outcome alone, such as "X no longer
  happens", has neither.
- **Scale:** describe each change at its real scale. A minor change gets a brief line that
  gives its typical size. A cost is stated plainly, with its size.
- **Tense:** the problem's symptoms take unambiguous past tense (*took*, *showed*); a cause
  that is still true takes present tense. The work's actions and measurements take past
  tense (*upgraded*, *ran*), and the state it leaves takes present tense (*is kept*). A
  modal (*could*) or a verb spelled the same in both tenses (*read*) blurs the two.

## Workflow

To regenerate a summary, run steps 1 and 3–6 on its existing sources, adding step 2 when the
change affects which outputs it needs. With no sources in its folder, run every step.

1. Confirm delivery and gather the facts:
   - the ticket's fields, verbatim, through a subagent making sequential Atlassian MCP
     calls: key, browse URL, title, type, priority, assignee, sprint
     (`customfield_10020`), description or plan, acceptance criteria, linked issues, and the
     comments bearing on the outcome;
   - each PR's merge date, merge commit and approver, from `gh`, or another deliverable's
     form and date;
   - the evidence: test results, run IDs, logs, measurements.

   The summary describes what was delivered: while any deliverable is unmerged or
   unshipped, stop and tell the user what is pending. With no acceptance criteria on the
   ticket, derive them from its goal or description and confirm them with the user. Ask
   the user where any missing evidence is.

   Done when every deliverable has merged or shipped, every metadata row is filled, and
   every acceptance criterion has an outcome with its evidence.
2. Propose part 3's outputs and let the user pick. Each candidate names the part of the
   work it explains and the evidence it draws on. Each change the work made that has
   measured results has a candidate. Done when the user has confirmed the set and its
   order, or that there are none.
3. Draft the Markdown sources: one file for parts 1–2, and one per output. Done when every
   Format item is present or excused by its "Present only when" condition, and every Rule
   is met.
4. Run `style-check` on the drafts with category Documentation, skipping the rules named
   under Overrides and adding this skill's Names and terms, Context, Scale and Tense rules.
   A rule that needs facts the text lacks goes under "Not checkable from text". Done when
   each flag is applied or shown to the user with the reason it was not, and the drafts
   are presented to the user with the source of each figure no output shows.
5. After the user approves the text, invoke the `md-to-pdf` skill to build the PDF with
   `--no-toc --no-page-numbers` and no `--title`: the parts 1–2 file first, then the
   outputs in their confirmed order. Done when every page has been rendered and viewed,
   and every title the text refers to matches an output's title.
6. Add or update the ticket's entry in the sprint folder's `Sprint-<NN>_Summary.md`. Create
   that file if it is missing: an H1 "Sprint N: ticket summaries", one line giving the
   sprint's dates, then one H2 per ticket in delivery order. The entry is the ticket key and
   its summary title as an H2, two or three plain-language bullets (the problem, what
   changed, the result or the caveat a reader needs), then an italic line giving the PDF's
   name and the PR with its merge date. Rebuild `Sprint-<NN>_Summary.pdf` with `md-to-pdf
   --no-toc --no-page-numbers`. Done when the entry matches the ticket summary's figures and
   the rebuilt page has been viewed.
