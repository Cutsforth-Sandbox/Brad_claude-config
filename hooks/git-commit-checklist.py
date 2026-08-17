#!/usr/bin/env python3
"""PreToolUse hook: deliver the pre-commit checklist while a commit is still being assembled.

It fires on `git add` as well as `git commit`. `PreToolUse` output reaches Claude only after the
matched call is already composed, so matching `commit` alone can never shape the commit that
triggered it -- it informs the retry at best. Staging is the ordinary precursor, so matching `add`
puts the checklist in hand before the commit is written. `git commit -a` and `git commit <file>`
skip staging and still get only the late match; CLAUDE.md carries the rule that keeps `git commit`
out of a batched tool block, which is the case no hook timing can rescue.

Division of labour, and why it is split this way:

* THIS HOOK DELIVERS. It returns `additionalContext` only -- no `permissionDecision` -- so it
  never touches whether the call is allowed. `additionalContext` is the one channel proven to
  reach Claude; `permissionDecisionReason` is documented as "For `"allow"` and `"ask"`, shown to
  the user but not Claude", so it is useless for carrying an instruction to the agent.
* THE `ask` PERMISSION RULES ENFORCE. `permissions.ask` in settings.json prompts before any
  commit, giving the user a veto if this checklist was skipped. The split is what the docs
  recommend: "Because the `if` filter is best-effort, use the permission system rather than a
  hook to enforce a hard allow or deny."

Neither half is sufficient alone, and both were observed failing alone on 2026-08-11:
  - Hook alone: a deliberately unapproved commit completed uninterrupted. A reminder with no
    veto behind it changes nothing.
  - A hook returning `permissionDecision: "ask"` never produced a prompt, despite the docs
    saying it "forces a permission prompt in auto mode" on >= 2.1.211 (running 2.1.223 at the
    time). Do not reintroduce a hook-side `ask` expecting it to gate attention.
  - `permissionDecision: "deny"` blocks reliably, but releasing it by retrying with an
    acknowledgement prefix is refused by the auto-mode classifier as an attempted bypass, which
    made committing impossible. Do not rebuild that design.

The `ask` RULE did start prompting once the user changed their permission mode; the hook-side
`ask` was never retested under that mode because the rule made it unnecessary.

Coverage: `permissions.ask` carries four rules -- `Bash(git commit:*)` plus
`Bash(git -C * commit:*)`, `Bash(git --no-pager commit:*)` and `Bash(git -c * commit:*)`. Bash
rules are literal string matches with no flag normalisation, so the plain rule alone matched none
of the flag forms the regex below catches, and those commits got the checklist with no veto behind
it. Compound commands (`cd x && git commit`) are covered by the plain rule, since permission rules
inspect subcommands -- verified. The three flag rules were added 2026-08-11; a mid-pattern `*`
combined with a trailing `:*` is not a documented combination, so if a flag-form commit ever fails
to prompt, that syntax is the first suspect.

`commit` filtering lives here rather than in settings.json's `if` field because, per the
Bash-`if` matching table, a pattern specifying more than the command name "run[s] the hook
anyway on `$()`, backticks, or `$VAR`" -- `Bash(git commit *)` would fire on any command
containing a variable. settings.json uses the safe `Bash(git *)` prefilter instead, which is the
command-name-only shape and does not over-fire.

Phrasing is deliberately descriptive rather than imperative: the docs warn that text "framed
as out-of-band system commands can trigger Claude's prompt-injection defenses, which causes
Claude to surface the text to you instead of treating it as context."
"""
import json
import re
import sys

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:  # noqa: BLE001
    sys.exit(0)  # unparseable input must never interfere with a commit

# Matches `git commit` and `git add`, with or without leading flags (`git -C path commit`,
# `git --no-pager commit`). Does not match `git log --grep=commit`, since `--grep=commit` is
# consumed as one flag token.
if not re.search(r"\bgit\b(?:\s+-{1,2}\S+(?:\s+\S+)?)*\s+(?:commit|add)\b", cmd):
    sys.exit(0)  # silent no-op: no stdout, no decision, the tool call proceeds untouched

print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": (
        "The user's commit convention on this machine: a commit is preceded by two things. "
        "First, a list of the files changed and the files created, given as two separate "
        "groups. Second, a question about whether to open the changes in their configured "
        "git difftool -- launched as `git difftool --staged -d`, which resolves `diff.tool` from "
        "their own gitconfig on whichever machine this is, and which shows the whole staged tree "
        "in one window rather than one window per file. Never search the filesystem for a diff "
        "tool and never hardcode its path. That form needs a HEAD, so it does not apply to a "
        "repository's first commit. "
        "The question is put to them with AskUserQuestion, which renders visibly, rather than as "
        "plain text they might not be shown; it is answered before the commit runs, and the "
        "difftool is opened only on an explicit yes. "
        "Commit messages always end with the Co-Authored-By trailer. That was settled on "
        "2026-08-11 and is no longer asked per commit. This hook is the durable record of that "
        "rule: the trailer itself is supplied by the environment, so if it ever stops appearing, "
        "this sentence is what says it still should. "
        "The user also sees a permission prompt for the commit itself, so a commit attempted "
        "without these two steps is one they are expected to decline."
    ),
}}))
