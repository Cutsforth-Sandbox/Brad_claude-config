---
name: fact-check
description: Fact-check text with a fresh subagent until every claim is verified, corrected, labelled or listed to the user. Use before posting, sending or committing text with factual claims, or reporting a finding as confirmed, and when asked to "verify any unverified assertions and assumptions".
---

# Fact check

A fresh subagent checks every claim in the text against primary sources and reports what
is wrong, partly right, unverifiable or assumed (rules in
[checker-prompt.md](checker-prompt.md)). The check is done when each such claim is
corrected in the text, labelled in it, or listed to the user.

To **label** a claim is to mark it inline ("unverified:", "inferred from …", "assumed:")
in text that stays within the team or session, or, for text read outside the session, to
list it in the step 5 report instead.

This skill checks text. To test a diagnosis or root cause, use `differential-diagnosis`.

## 1. Stage the text

Stage each text verbatim as `<scratchpad>/fc/text-N.md`. Copy it with a shell command when
it already sits in a file; write it out only when it exists only in the conversation.
- When the user asked you to verify earlier responses or a plan, stage each one they refer
  to. Ask if it is unclear which.
- For a doc edit, also copy the full document to `<scratchpad>/fc/doc-N.<ext>`, apply the
  edit to the copy, and give that path with the line ranges the edit changed.

Done when: every text that will leave the session or be called verified has a staged file
that matches, character for character, the wording you would send now.

## 2. Fill the brief

Fill every `<…>` slot in the brief below.
- User-supplied items: quote verbatim from the user's messages in this session, including
  decisions made earlier in it and command output the user pasted that bears on the
  text's claims.
- Evidence already fetched: files, logs and command output already in the scratchpad or
  on disk, so the checker does not fetch them again.
- Doubt list: every claim you recalled, inferred, or are unsure of.

```
You are an independent fact-checker. Read <absolute path of this skill's
checker-prompt.md> and follow it in full.

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
- Environment notes: <tools to use where several could (e.g. a primary Jira tool rather
  than a discovery call), output-compression workarounds, or "none">
- Text to check: <each path, what it is (PR body, reply to X, doc edit, analysis, chat
  response), and who reads it: within the team or session, or outside it>
- Author: <the user, this session, or a named person>
- Full document(s) for edits: <path and changed line ranges, or "none">
- What it replies to or rests on: <paths or pasted text, or "none">
- Evidence already fetched: <paths, or "none">
- User-supplied items (facts, decisions, pasted output), each quoted verbatim: <list, or
  "none">
- Author's doubt list: <list, or "none">
```

Done when: no `<…>` slot remains, and each slot with nothing to give reads "none".

## 3. Dispatch

Run one fresh general-purpose subagent on Opus, or on a stronger model if one wrote the
text. Its whole brief is the filled brief from step 2.

Done when the report passes every check in the BEFORE YOU RETURN section of
[checker-prompt.md](checker-prompt.md). Read that section and check the report yourself.

Send all failed checks back to the same subagent in one message. If any check still fails
after that, label the affected claims "unverified:", and list the gap in the step 5
report.

## 4. Apply corrections

First re-run each live API call or web fetch saved in the notes behind a finding. If the
output differs, label the claim "unverified:" and show it in the step 5 report.

Apply each replacement verbatim to the staged files. List replacements for places outside
the staged files (stale restatements elsewhere in the repo) in the step 5 report. To
overturn a replacement, run the case yourself: a command, a file read, or a docs quote. A
replacement overturned with a receipt counts as resolved.

Label each unverifiable claim "unverified:" and each assumption with its "assumed:"
sentence. For text read outside the session, the checker's replacements already carry no
inline labels, and these labels go in the step 5 report.

A **delta** is wording in the final text that matches neither the checked text nor a
replacement applied verbatim. For each delta, do one of three things:
- re-run this skill on the full final text, with the delta lines in the doubt list;
- label each claim in the delta;
- quote it in the step 5 report as claim-free.

For a chat response, the step 5 message carries the corrected response in full plus the
report items. Any other sentence in it is a delta.

Done when all four hold:
- every replacement is applied, overturned with a receipt, or listed in the step 5 report;
- every unverifiable claim is labelled;
- every assumption is labelled, and every recommendation a refuted assumption undermines
  is replaced;
- every delta is re-checked, labelled, or quoted as claim-free.

## 5. Report

In your message to the user, show:
- the findings that change the text, in the report's ranked order, each with its
  replacement as applied;
- the unverifiable claims and assumptions, with the label the text carries or the note
  that they are listed here only;
- each overturned finding, with the checker's evidence and your receipt side by side;
- each delta you judged claim-free, quoted;
- each gap left after the resend;
- the confidence line;
- the checker's token use, summed across its completion notices.

Done when: every item above appears in your message. Posting, sending or committing waits for
the user's approval of the final text.
