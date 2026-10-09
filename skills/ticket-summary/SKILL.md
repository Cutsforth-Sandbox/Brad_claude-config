---
name: ticket-summary
description: Ticket summary PDF for a delivered Jira ticket, and the sprint summary that indexes them, read by outsiders to the work. Use when asked for a ticket, task or sprint summary, or to regenerate one.
---

# Ticket summary

An internal PDF that explains one delivered ticket to an **outsider**: a manager or a
colleague from another team, without the technical background, who never saw the work. The
user presents it and retells it from the page. A sprint summary (step 6) indexes a sprint's
ticket summaries.

## Format

**Folder:** each ticket summary lives in its sprint's folder,
`~/Documents/Ticket_Summaries/Sprint-<NN>_<start>_<end>/`, as `<KEY>_Summary.pdf`, with its
Markdown sources in `<KEY>/`. The sprint is the entry in the ticket's Jira sprints (field
`customfield_10020`) whose start-to-end range contains the last deliverable's merge or ship
date; when none does, ask the user. `<NN>` is the number that follows "Sprint" in that
sprint's name, zero-padded to two digits; when there is none, ask the user. `<start>` and
`<end>` are its `startDate` and `endDate` as YYYY-MM-DD in the time zone of the machine
running the skill. Example: `Sprint-07_2026-01-05_2026-01-16/`.

**Headings:** every Markdown file opens with its title as its H1:
`<KEY>: <the ticket's subject in plain words>` for the parts 1–2 file, and the output's title
for each output file. Parts 1 and 2 are H2 headings, and part 2's subsections are H3.
Headings carry no numbers.

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
- Each output is its own page: a Markdown file named `NN_<slug>.md`, where NN is its
  two-digit position in the confirmed order. It holds its title, a plain-language summary,
  the output, then a short list under an H2 "How to read this" heading, covering:
  - what it shows;
  - how to interpret it;
  - its sources;
  - a worked example: present only when the reading isn't obvious;
  - how its derived values were computed: present only when it has any;
  - how it relates to current behaviour: present only when that changed after it was
    produced.
- The plain-language summary is two to four sentences or bullets on what the output shows
  and what it means for the outsider. It follows the `customer-docs` Audience and Scope and
  proportion rules, uses the outsider's vocabulary in place of this skill's Names and terms
  rule, and follows this skill's Evidence and Tense rules.
- Refer to another output by its title; the PDF has no page numbers.

## Rules

**Overrides:** these Rules replace `CLAUDE.md`'s inline-derivation rule (in *Evidence and
sourcing*) and two of its *Documentation* rules: the one on development-process narrative,
and "Was X, changed because Y, now Z".

**Content**
- **Evidence:** every claim and figure traces to its evidence (a test, run, log,
  measurement or document). A figure no output shows has its source and derivation in the
  message that presents the draft. Totals and shares agree with each other.
- **Conditions:** state the conditions a result depends on (environment, hardware,
  configuration, inputs), so the outsider can tell whether it applies to their case.
- **Names and terms:** use the real repo, product and component names. Define each, and any
  other technical term, at its first use unless the outsider already knows it.
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

To regenerate a ticket summary, find its sources at `~/Documents/Ticket_Summaries/*/<KEY>/`
and work in that sprint folder. Run steps 1 and 3–6 on them, adding step 2 when the change
affects which outputs it needs. When no such folder exists, run every step. To rebuild only
a sprint summary, run step 6 with no new entry.

1. Confirm delivery and gather the facts:
   - the ticket's fields, verbatim, through a subagent making sequential Atlassian MCP
     calls: key, browse URL, title, type, priority, assignee, sprint
     (`customfield_10020`), description or plan, acceptance criteria, linked issues, and the
     comments bearing on the outcome;
   - each PR's merge date, merge commit and approver, from `gh`, or another deliverable's
     form and date;
   - the evidence: test results, run IDs, logs, measurements.

   The ticket summary describes what was delivered: while any deliverable is unmerged or
   unshipped, stop and tell the user what is pending. With no acceptance criteria on the
   ticket, derive them from its goal or description and confirm them with the user. Ask
   the user where any missing evidence is.

   Done when every deliverable has merged or shipped, every metadata row is filled, and
   every acceptance criterion has an outcome, with evidence for each one met or partly met.
2. Propose part 3's outputs and let the user pick. Each candidate names the part of the
   work it explains and the evidence it draws on. Each change the work made that has
   measured results has a candidate. Done when the user has confirmed the set and its
   order, or that there are none.
3. Draft the Markdown sources: one file for parts 1–2, and one per output. Done when every
   Format item is present or excused by its "Present only when" condition, and every Rule
   is met.
4. Run `style-check` on the drafts with category Documentation, skipping the rules named
   under Overrides and adding this skill's Names and terms, Context, Scale and Tense rules.
   Check each output's plain-language summary with category Customer-facing instead,
   limited to the `customer-docs` Audience and Scope and proportion rules plus this skill's
   Evidence and Tense rules. A rule that needs facts the text lacks goes under "Not
   checkable from text". Done when every flag is listed to the user, marked applied or not
   with the reason, and the drafts are presented with the source of each figure no output
   shows.
5. After the user approves the text, invoke the `md-to-pdf` skill to build the PDF with
   `--no-toc --no-page-numbers` and no `--title`: the parts 1–2 file first, then the output
   files in file-name order. Done when every page has been rendered and viewed, and every
   title the text refers to matches an output's title.
6. Add or update the ticket's entry and table row in the sprint summary,
   `Sprint-<NN>_Summary.md` in the sprint folder, creating it if it is missing. The sprint
   summary has three levels: its table shows the sprint's work at a glance, each entry adds
   detail, and each ticket summary gives the full account. Each level agrees with the more
   detailed one below it.

   The file opens with an H1 "Sprint <N>: ticket summaries" (`<N>` without zero-padding), a
   line giving the sprint's dates, a line reading "Status as of <YYYY-MM-DD>", then the
   table. The date is `<end>` once today is after it, otherwise today.

   The table has one row per sprint ticket assigned to the user, sub-tasks excluded, in key
   order. A subagent, as in step 1, fetches the rows with JQL
   `sprint = <id> AND assignee = currentUser() AND issuetype not in subTaskIssueTypes()`,
   where `<id>` is the `id` of the sprint's entry in `customfield_10020`, not `<N>`. After
   `<end>`, a ticket's status is the `to` of its last status change on or before `<end>`,
   from its changelog; with none, the `from` of its first change after `<end>`; with no
   changes, its current status. The columns:
   - **Ticket:** the ticket key, linked.
   - **Title:** the Jira title, verbatim.
   - **Status:** the Jira status, verbatim.
   - **Outcome:** one plain clause of at most 12 words with no technical terms, such as
     "Report pages now load in seconds instead of minutes." With a ticket summary, it
     states what the work achieved; without one, what the ticket sets out to do.
   - **Ticket summary:** the name of `<KEY>_Summary.pdf` if it is in this sprint folder,
     otherwise "—".

   The entries follow the table in delivery order, one per ticket summary in the folder.
   Each is an H2 matching the ticket summary's H1, then two or three plain-language bullets
   (the problem, what changed, the result or the caveat the outsider needs), then an italic
   line giving each deliverable with its merge or ship date. Every run regenerates the table
   in full, keeping each existing Outcome unless its ticket changed.

   Show the user the new or changed entry and the table. After they approve, rebuild
   `Sprint-<NN>_Summary.pdf` through the `md-to-pdf` skill with `--no-toc
   --no-page-numbers`. Done when every ticket the JQL query returns has a row, each Outcome
   agrees with its entry and ticket summary, each entry matches its ticket summary's
   figures, and every page of the rebuilt PDF has been viewed.
