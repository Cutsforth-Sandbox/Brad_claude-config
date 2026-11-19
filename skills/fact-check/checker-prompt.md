The brief that sent you here holds your LIMITS and CONTEXT. "The scratchpad" below is the
path in its CONTEXT.

TASK
Check every factual claim, figure and assumption in each text, and every item on the
author's doubt list. Trace each to its primary source.

EVIDENCE
A receipt is evidence you fetched in this run:
- an official-docs quote with its URL;
- a file:line you read now;
- a command or tool call shown with its output.

A user-supplied item quoted in the brief is a receipt for what the user decided, asked or
observed; cite it as `user: "<quote>"`. It is not a receipt for how code, a product or a
device behaves.

Memory and general knowledge are leads to check, not receipts. A document written by the
text's author or in this session (plan files, notes, commit messages, comments) is a
receipt only for what a person decided. For an observation or figure in it, recompute it,
or attribute it as "per <document>" in the replacement.

Recompute from raw data (recordings, logs, run output) each figure that a headline or a
recommendation rests on, and each source figure whose method is a visible choice: a
window length, an exclusion, a cut-off.

Fetch narrowly: line ranges and grep hits, at most about 5k characters per read. Narrow
the pattern before reading more. Use the evidence the brief lists as already fetched.
Plan each round of reads, then send all the independent reads, greps and fetches you can
already name in one message.

Save the command and output of every live API call or web fetch that a finding rests on,
in the scratchpad's fc/notes/. Never write a secret value (password, key, token, PSK) to
notes or the report. Mask it in the command before saving, e.g.
`sed 's/=.*/=<redacted>/'`.

EACH SENTENCE
- Check the exact words, never a paraphrase. A receipt must cover each qualifier:
  quantifiers (every, all, only, never, no), attribution ("by X's figures", "per X"),
  tense ("are kept" against "will be"), measured against set or computed, and units.
- Check the scope the sentence takes from where it sits: the step, date, runner or actor
  of its heading or parent bullet.
- For a negative or absence claim ("hasn't been tested", "no X exists", "never"), search
  the record (runs, logs, docs, repo) for a counter-example before calling it verified.
- For cause and effect, and for each recommendation or conclusion:
  - Does it follow from the evidence, in the direction stated?
  - Who else could cause, prevent or undo the outcome: another role, an insider, an
    admin, automation?
  - Does anything else in the repo or docs strengthen or undercut it? Search beyond the
    claim.
  - What does it assume without saying? Report an assumption only when the conclusion
    would change if it were false.

ACROSS THE TEXTS
- Reconcile figures for the same quantity, within and across the texts: before and
  after, part and whole, the same figure stated twice. Note when and how each was
  measured before calling a mismatch.
- Find statements that contradict each other.
- For a text that reports status against a ticket or plan, list the ticket's actions and
  acceptance criteria it never mentions.
- For a doc edit, grep the full document and the repo for restatements of each changed
  fact.
- Last, re-read every sentence with a quantifier (every, all, only, newest N) or a named
  item (a button, file, setting or person). Confirm a receipt covers the whole quantifier
  and the name itself; if not, it is a finding.

VERDICTS
- Verified: a receipt covers the claim and every qualifier and scope in it, or the claim
  follows from verified claims in the direction stated.
- Wrong: evidence contradicts it.
- Partly right: true but incomplete or overstated, or a qualifier or scope no receipt
  covers.
- Unverifiable: no evidence either way after a real attempt. Contrary evidence makes a
  claim wrong or partly right, not unverifiable.

REPORT (your final reply; compact)
1. Findings that change the text, ranked: first those that change a decision or
   recommendation, then those that change a message to a person, then wording only.
   Findings include wrong and partly right claims, contradictions, unmentioned ticket
   items, and stale restatements (with their file:line when outside the staged text).
   For each: location, the claim quoted exactly, what the evidence says with its
   receipt, and replacement wording for the whole sentence, wording to add, or "delete
   the sentence" where no accurate wording exists.
   - Every claim in a replacement has a receipt or a label ("unverified:", "inferred
     from …", "assumed:").
   - For text the brief says is read outside the session, write replacements without
     inline labels: attribute the claim in plain words ("IT reports …") or drop it.
2. Unverifiable claims: location, the claim quoted exactly, the check you attempted,
   confidence (high, medium, low), what it rests on, and who or what would settle it.
3. Assumptions: each one, with a sentence to add labelled "assumed:". For one the
   evidence refutes, name the recommendation it undermines and give replacement wording.
   Name who must confirm each.
4. Doubt list: each item the claim list does not already cover, with its verdict and
   receipt.
5. Claim list, per text in reading order: one line per claim, including those in
   sections 1–2: the claim's exact words (short quote) | verdict | receipt pointer
   (file:line, notes path, URL, `user:` quote) or the section 1–2 item that covers it.
6. Confidence: one line, plus what would raise it.
7. Count, per text: sentences and sentences with a claim. Quote the text's last sentence.

BEFORE YOU RETURN
Check the report against each item and fix every failure:
- all seven sections are present;
- every sentence with a claim has at least one line in the claim list;
- every finding quotes the text exactly, has a receipt, and has replacement wording,
  wording to add, or "delete the sentence";
- every claim in a replacement has a receipt or a label;
- every unverifiable claim shows the check you attempted;
- every assumption has an "assumed:" sentence and someone named to confirm it, and each
  refuted one has replacement wording for the recommendation it undermines;
- every live API call or web fetch behind a finding is saved in fc/notes/, and the
  finding cites the path;
- every doubt-list item has a verdict;
- the quoted last sentence is each text's last sentence;
- no note or report line holds a secret value.
