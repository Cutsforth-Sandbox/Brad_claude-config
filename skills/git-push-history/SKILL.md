---
name: git-push-history
description: Generate a table of a git branch's real push history since it diverged from its base branch, using the remote-tracking branch's reflog as ground truth. Use when asked for a branch's push history - what's been pushed, and when.
---

# Git Push History Table

Commit dates say when code was written, not when it left the machine. The
remote-tracking branch's reflog (`refs/remotes/origin/<branch>`) records
the real push events - treat it as ground truth, not commit timestamps.

## Steps

1. Establish the base ref. If the user named one, use it. Otherwise find
   the branch's actual parent: list candidate refs, run
   `git log --oneline <candidate>..<branch>` for each, and take the
   candidate whose remaining commits are this branch's alone (the
   repository's default branch is a candidate, not the assumed answer).
   Done when you have a base ref and its merge-base hash with the branch.

2. List every commit unique to the branch, oldest first:
   `git log --reverse --format="%h|%ad|%s" --date=format:"%Y-%m-%d %H:%M" <base>..<branch>`
   Done when you have the full ordered commit list.

3. Check for unpushed work: compare `git rev-parse <branch>` to
   `git rev-parse origin/<branch>`. Done when you know whether local is
   ahead of the remote, and by how many commits.

4. Get the actual push events, newest first:
   `git reflog show --date=format:"%Y-%m-%d %H:%M" refs/remotes/origin/<branch>`
   Done when you have every push's timestamp and the commit that became
   the tip at that push.

5. **Attribute commits to pushes - a push can carry more than one commit,
   never assume 1:1.** Walking step 4's list oldest to newest, each push's
   commits are everything between the *previous* push's tip (exclusive)
   and *this* push's tip (inclusive), in step 2's order. Done when every
   commit from step 2 is attributed to exactly one push, none skipped or
   double-counted.

6. Anything from step 2 newer than the last reflog entry is unpushed -
   its own final row, attributed to no push.

7. Build the table: push #, date/time, commit(s) (short hash), and a
   plain-language one-line description of what that push delivered -
   written from the commit subject(s), not pasted verbatim.

8. Footnote anything structurally notable - especially if the branch's
   earliest commits actually originated on a *different* parent branch
   (`git branch --contains <first commit>`) rather than being pushed on
   this branch's own ref. `<base>..<branch>` includes them regardless; say
   so rather than presenting them as a push on this branch. Name the base
   ref used, so the table's scope is explicit.

## Output

Two copies of the same table, so it's never a one-off manual reformat to
actually use the result:

- A Markdown table in the chat response, for reading.
- The identical data as tab-separated values in its own fenced code
  block, column headers in the first row - paste this block directly into
  Excel/Sheets/Word and it lands in real columns, unlike a copied Markdown
  table's literal pipe characters.

Plus a one-line callout of anything structurally unusual (uneven push
sizes, a branch built on another feature branch instead of the default
branch, etc.).
