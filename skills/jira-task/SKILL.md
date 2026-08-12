---
name: jira-task
description: Draft a Jira task/ticket in the user's required format. Use whenever composing, revising, or reviewing a Jira ticket, task, story, or bug report — including when asked to "write up" an issue for Jira.
---

# Writing a Jira task

Produce the ticket in exactly these sections, in this order. No other sections
unless they add meaningfully to understanding the task — either for the
assignee (what to understand / what to fix) or for management placing it into
a sprint or workflow.

## Structure

1. **Title** — one line, comprehensible to someone not working on the specific
   project but who knows the product name and basic terminology.
2. **Context** — background for the issue and the pieces/elements involved.
3. **Goal** — what the issue is / the desired outcome. Technical terms are OK,
   but anything too specific or jargon-y gets a quick inline definition.
4. **Actions** — what needs to be done.
5. **Acceptance criteria** — conditions to satisfy.
6. **Definition of done** — what makes the task solidly considered DONE.

## Style rules

- Bullet lists, not narrative prose paragraphs.
- Concise. Do not bloat with technical density — a draft once came back
  "drastically bloated and technically dense" and was collapsed from 10
  sections to this format.
- Verify project facts against the repo/docs before stating them; do not
  narrate assumed history. Flag anything that is an assumption.

## Workflow

1. Draft the ticket in chat as markdown for review.
2. Do not file it anywhere. If Atlassian/Jira MCP tools are connected, offer
   to file it after the draft is approved — filing requires the user's explicit
   go-ahead each time.
