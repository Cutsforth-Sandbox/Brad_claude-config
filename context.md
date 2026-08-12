# Global context — source pointers

Not documentation — a pointer file for finding facts, per the "Finding
factual answers" order in `~/.claude/CLAUDE.md`. This is the machine-wide
fallback consulted when the current repo has no `context.md` of its own.

## Where hardware facts live

Manuals, datasheets, and programming guides for equipment used across
projects (Rigol scopes and signal generators, Raspberry Pi, etc.):

Resolved in this order, taking the first that contains a `context.md`: `$HW_DOCS`, then
`$OneDrive/Documents/HW_Docs`, then `$HOME/HW_Docs`. This is the same chain
`check-hw-docs/checker.py` implements, so the two cannot drift. On this Windows machine
it currently lands on `%OneDrive%\Documents\HW_Docs`.

That folder keeps its own `context.md` — a manifest of every PDF's official
source URL, verified date, and known version. Read the manifest first; it
names which document is authoritative for a given fact and whether it has
been verified recently. The `check-hw-docs` skill keeps it current.
