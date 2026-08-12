# Reviewer briefs

Disclosed reference for [`branch-review`](SKILL.md). Each brief below is
pasted **verbatim** into its subagent — never paraphrased — preceded by this
shared preamble:

> You are reviewing a real code change as one of several independent
> reviewers, each assigned a distinct angle. Work only your assigned angle;
> other angles are covered by other reviewers. For every candidate, report
> `file:line`, a one-line summary, and a concrete failure scenario — the
> user-visible consequence (wrong output, crash, data loss), not an
> intermediate state (a value goes stale, a set grows). Report every
> candidate you can name a failure scenario for, even half-believed ones — an
> independent verifier judges them next. Report `(none)` when the diff gives
> you nothing on this angle.

Each brief carries a **trigger** — the condition in the diff that puts it on
the roster (checked in `SKILL.md` step 2).

## Brief 1 — Correctness scan

**Trigger:** always.

Read every hunk in the diff, line by line. Then read the **enclosing
function** of each hunk — a bug on an unchanged line of a touched function is
in scope, since the change re-exposes or fails to fix it.

Hunt for: inverted or wrong conditions, off-by-one, null/undefined deref where
adjacent lines show the value can be absent, missing `await`, falsy-zero
checks, wrong-variable copy-paste, unescaped regex metacharacters, error
swallowed in a catch that should propagate.

Also hunt for empty/null inputs and boundary values the diff doesn't guard.

Also hunt for the diff language's classic pitfalls: SQL injection, float
equality, timezone/DST drift, `==` coercion, closure-captured loop variables,
mutable default arguments, late-binding closures, nil-map writes, a dataclass
default evaluated once, `hash()` non-determinism, predicate methods with side
effects.

Also: when the diff adds or changes a type that wraps another (a cache,
proxy, decorator, or adapter), check that every method routes to the wrapped
instance and not back through a registry, session, or global — a wrapper that
resolves through the global it's supposed to intercept will recurse or
re-enter.

**Repro rule.** Where a candidate can be settled by running something, run it
and report the result as the failure scenario.

## Brief 2 — Failure and state

**Trigger:** the diff touches error handling, retries, threading, async code,
locks, or shared mutable state.

Hunt for whether failures are surfaced, retried, or silently swallowed —
including retry/backoff logic that can storm, loop, or mask a real failure
from the user.

Hunt for races, partial writes, non-idempotent operations, lock-scope
mistakes, and ordering assumptions that don't hold under concurrent or
re-entrant execution.

## Brief 3 — Blast radius

**Trigger:** the diff deletes, renames, or changes the signature of anything.

For every line the diff deletes or replaces, name the invariant or behavior it
enforced, then check whether the new code re-establishes it. A removed guard,
a dropped error path, a narrowed validation, or a deleted test that covered a
real case are all candidates.

Using the shared surface and changed-symbol list from `SKILL.md` step 2: for
each changed symbol, check its **callers** for a new precondition, a changed
return shape, a new exception, or a timing/ordering dependency they don't
expect — and check its **callees** for whether a parallel change in the same
diff makes the call unsafe.

Also watch for: moved or extracted code that shed a guard or a regex anchor on
the way; config defaults flipped.

## Brief 4 — Adversary

**Trigger:** the diff parses input or reads from an external source.

**Untrusted input.** For every input the diff touches that crosses a trust
boundary — typed entry, a config or data file, a CLI argument, an environment
variable, a network payload — try blank, zero, negative, `inf`/`nan`, an
inverted range, an oversized value, and the wrong text encoding.

**Unreliable upstream.** For every external source the diff reads — a device,
a web service, a database, a file feed, the system clock — assume it returns
data that is *plausible but wrong*, not merely absent or erroring. This
includes the case where each individual input is valid but a batch of them is
mutually inconsistent.

## Brief 5 — Cleanup

**Trigger:** always.

**Reuse.** Grep shared and utility modules, and files adjacent to the change,
for something the diff re-implements. Name the existing helper to call
instead.

**Simplification.** Redundant or derivable state, copy-paste with slight
variation, deep nesting, dead code left behind. Name the simpler form that
does the same job.

**Efficiency.** Redundant computation or repeated I/O, independent operations
run sequentially, blocking work added to a startup path or hot path, and
long-lived objects built from closures that keep their whole enclosing scope
alive. Name the cheaper alternative.

**Altitude.** A special case layered onto shared infrastructure instead of
generalizing the underlying mechanism.

**Conventions.** Find the `CLAUDE.md` files that govern the changed code —
user-level, repo-root, and any in a directory that is an ancestor of a changed
file. Flag a violation only when you can quote the exact rule and the exact
line that breaks it.

**Tests.** Whether changed or added tests assert observable behavior or
internal implementation details; setup/teardown asymmetry between tests.

**Drift.** New code that diverges from the idiom already used in the
surrounding file or module.

For every candidate here, state the concrete **cost** in the failure scenario
— what is duplicated, wasted, harder to maintain, or which rule is broken —
rather than a crash. These candidates rank below every correctness finding
(briefs 1–4) when the report is assembled.

## Brief 6 — Build reproducibility

**Trigger:** the diff touches a BitBake recipe (`.bb`/`.bbappend`), a
`kas/*.yml` config, a git submodule pin, or CI workflow config.

Check: layer or submodule revisions pinned to a fixed commit rather than a
floating branch or `HEAD`; toolchain and dependency versions pinned rather
than "latest" or unbounded; CVE scanning (`cve-check` or equivalent) present
and enabled if the repo already has it configured elsewhere — flag only a
regression (previously enabled, now removed or weakened), not the general
absence of tooling nobody asked this review to introduce; an SBOM-generation
step removed or bypassed if one existed before the diff.

State the concrete cost in the failure scenario, same as brief 5 — what
becomes unreproducible or unpinned, not a crash.
