---
name: fact-check
description: Fact-check text with a fresh subagent until every claim is verified or labelled. Use before posting, sending or committing text with factual claims, or reporting a finding as confirmed, and when asked to "verify any unverified assertions and assumptions".
---

# Fact check

A fresh subagent builds an **inventory** of every claim in the text and returns a verdict
for each row. The check is done when every claim is in one of three states:
- backed by a **receipt** (defined in [checker-prompt.md](checker-prompt.md), RECEIPT);
- resting on a user-supplied item, quoted verbatim;
- carrying an inline label in the text.

This skill checks text. To test a diagnosis or root cause, use `differential-diagnosis`.

## 1. Stage the text

Stage each text verbatim as `<scratchpad>/fc/text-N.md`. Copy it with a shell command when
it already sits in a file; write it out only when it exists only in the conversation.
- When the user asked you to verify earlier responses or a plan, stage each one they refer
  to. Ask if it is unclear which.
- For a doc edit, also copy the full document to `<scratchpad>/fc/doc-N.<ext>`, apply the
  edit to the copy, and give that path.

Done when: every text that will leave the session or be called verified has a staged file
that matches, character for character, the wording you would send now.

## 2. Fill the brief

Fill every `<…>` slot in the brief below. Quote each user-supplied item verbatim from the
user's messages in this session. In the doubt list, put every claim you recalled, inferred,
or are unsure of.

```
You are an independent fact-checker. Read <absolute path of this skill's
checker-prompt.md> and follow it in full. Your report must let the caller leave every
claim backed by a receipt, resting on a user-supplied item, or labelled in the text.

LIMITS: read-only except for notes.
- Allowed: file reads, read-only shell commands (git reads, grep, version queries, local
  test runs that write nothing to the repo), read-only API GETs, CI run views, and official
  documentation.
- Write only notes, in <scratchpad>/fc/notes/.
- Out of bounds: repo edits, commits, pushes, posts, messages, and any API write (POST,
  PUT, PATCH, DELETE).

CONTEXT
- Scratchpad: <scratchpad>
- Repo / branch / HEAD: <…, or "none">
- Environment notes: <e.g. output-compression workarounds, or "none">
- Text to check: <each path, and what it is: PR body, reply to X, doc edit, analysis,
  chat response>
- Full document(s) for edits: <path, or "none">
- What it replies to or rests on: <paths or pasted text, or "none">
- User-supplied items (facts and decisions), each quoted verbatim: <list, or "none">
- Author's doubt list: <list, or "none">. Check these in addition to every claim in the
  text.
```

Done when: no `<…>` slot remains, and each slot with nothing to give reads "none".

## 3. Dispatch

Run one fresh general-purpose subagent on Opus, or on a stronger model if one wrote the
text. Its whole brief is the filled brief from step 2.

Done when the report passes every check in the BEFORE YOU RETURN section of
[checker-prompt.md](checker-prompt.md). Read that section and check the report yourself.
A receipt's command output may sit in the cited notes file; read it.

Send all failed checks back to the same subagent in one message. If any check still fails
after that, label the affected claims inline as "unverified:", and list the gap in the step
5 report.

## 4. Apply corrections

First re-run each live API call or web fetch saved in the notes behind a REFUTED or PARTLY
row or a correction. If the output differs, label the claim inline as "unverified:" and
show the row in the step 5 report.

Apply each correction verbatim to the staged files. To overturn one, run the case yourself:
a command, a file read, or a docs quote. A correction overturned with a receipt counts as
resolved.

A **delta** is wording in the final text that matches neither the checked text nor a
correction applied verbatim. For each delta, do one of three things:
- re-run this skill on the full final text, with the delta lines in the doubt list;
- label each claim in the delta inline ("unverified:", "inferred from …");
- quote it in the step 5 report as claim-free.

For a chat response, the step 5 message carries the corrected response in full plus the
report items. Any other sentence in it is a delta.

Done when all three hold:
- every correction is applied, or overturned with a receipt;
- every "assumed:" sentence the report gives is added, and every recommendation a REFUTED
  assumption undermines is replaced;
- every delta is re-checked, labelled, or quoted as claim-free.

## 5. Report

In your message to the user, show:
- every row that is not VERIFIED or SOURCE: USER, with its correction as applied, or the
  inline label the text already carries;
- each overturned row, with the checker's evidence and your receipt side by side;
- each delta you judged claim-free, quoted;
- each gap left after the resend;
- the assumptions list;
- the confidence line.

Done when: every item above appears in your message. Posting, sending or committing waits for
the user's approval of the final text.
