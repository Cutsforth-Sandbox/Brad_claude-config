The brief that sent you here holds your LIMITS and CONTEXT. "The scratchpad" below is the
path in its CONTEXT.

RECEIPT
A receipt is evidence you fetched in this run:
- an official-docs quote with its URL;
- a file:line you read now;
- a command or tool call shown with its output.

Not receipts:
- memory and general knowledge, which are leads to check;
- a source written by the text's author or this session (their comments or commit
  messages), for that text's claims.

A count or other figure in a receipt shows the command and output that produced it.

Save the command and output of every live API call or web fetch that a REFUTED or PARTLY
verdict or a correction rests on, in the scratchpad's fc/notes/ as {ID}.txt.

STEP 1 — INVENTORY
Finish the full inventory before verifying any row.

Read each text unit by unit:
- A unit is a sentence. A bullet, table cell, heading or subject line with no
  sentence-ending punctuation is one unit. A code block is one unit.
- Number units per text as T1-U1…, T2-U1… in reading order.
- Split each unit into atomic claims, one row per claim.
- Give each row an ID and a location: its unit ID, or file:line for a row outside the text
  (a restatement or a repo fact).

Rows cover:
- every number, count, size, duration, date, weekday, version, ID, and run, commit or
  issue number;
- every name of a file, line, function, setting, permission, endpoint, person or ticket;
- every statement of behaviour (what the code, a platform or a service does);
- quantifiers (only, every, all, never, no, any) and negatives ("nothing", "no X exists");
- comparisons and implied claims ("before, only A had one" claims both the old state and
  the new state);
- cause and effect ("so", "because", "which means");
- what a person said, decided, owns or will do;
- the assumptions a recommendation, plan or conclusion relies on without stating them. A
  verified fact that could change later, such as a setting an admin controls, is not an
  assumption. Flag an assumption only when the recommendation or conclusion would change if
  it were false.

For a doc edit, inventory restatements of each changed fact found in the full document and
the repo.

STEP 2 — VERIFY EVERY ROW
Batch the first fetch per source: group rows by file, command or URL, and send independent
fetches together in one message. Follow-up fetches, such as those for the counter-example
hunt, are allowed. Each row still cites its own file:line, quote or output line.

Fetch narrowly: read line ranges and grep hits rather than whole files or logs. Quote a
docs page once, then cite that quote by row ID.

Try to confirm each row and try to break it. Hunt the counter-example:
- time-window edges, and whether a window or event the text names once recurs;
- re-runs;
- other branches or events;
- permission differences;
- the rest of a category: when the text names some members (credential types, items that
  change something, places a fact is stated), find the others;
- the case the text leaves out.

Give each row exactly one verdict. A row that needs two verdicts holds two claims; split
it.
- VERIFIED — a receipt backs it.
- REFUTED — evidence shows it is wrong.
- PARTLY — true but incomplete or overstated; name the part.
- INFERENCE — follows from VERIFIED or SOURCE: USER rows; give the chain as row IDs.
- SOURCE: USER — rests on a user-supplied item; cite the item.
- UNVERIFIABLE HERE — give the check you attempted (command, search or URL) and why it
  failed, then name who or what would settle it (a person, a console page, an API needing
  permissions you lack).

Every count, measurement or computed figure in the text needs its derivation (a command, a
query, or a document and page) stated inline, unless the sentence itself shows it, as when
it lists the items it counts. The verdict still follows the receipt; STEP 3 adds a missing
derivation.

For claims about external products and services, use official sources only: the vendor's
or project's own documentation. When two official sources disagree, name the newer by
edition identifier or cover date.

STEP 3 — CORRECTIONS
Give exact replacement wording for these rows, except assumption rows, which follow the
rules below:
- every REFUTED or PARTLY row;
- every INFERENCE or UNVERIFIABLE HERE row that the text states as fact instead of
  labelling inline. For an INFERENCE row, reasoning the text shows in the same sentence
  ("so", "because") counts as a label;
- every row whose figure lacks the inline derivation STEP 2 requires.

For each assumption row:
- VERIFIED or SOURCE: USER — nothing to add.
- REFUTED — name the recommendation it undermines, and give replacement wording for that
  recommendation.
- Otherwise — give a sentence to add that states it, labelled "assumed:".

Hold each replacement to the same bar. Every claim in it has a receipt from this run or an
inline label ("unverified:", "inferred from …", "assumed:"). Where no accurate wording
exists, recommend deleting the claim. Give each new claim in a replacement its own table
row, ID suffixed "c" (e.g. R12c), with its verdict and receipt.

REPORT — all five sections, every row present:
1. Confidence: one line, plus what would raise it.
2. Table: ID | location | claim (short quote) | verdict | receipt or reason (one line;
   put longer command output in the scratchpad's fc/notes/ as {ID}.txt and cite that path).
3. Corrections: ID -> exact replacement wording.
4. Assumptions: each assumption row ID, with who must confirm it.
5. Coverage, per text: the total unit count, the last unit quoted, and the IDs of units
   with no claim. Then the number of rows and the rows per verdict.

Assumption rows go in the table with the other rows.

BEFORE YOU RETURN
Check the report against each item and fix every failure before you return it:
- all five sections are present;
- for each text, every unit ID from U1 to the reported total appears in the table's
  location column or in the no-claim list, and the quoted last unit is the text's last
  unit;
- every row has exactly one of the six verdicts;
- every VERIFIED row's receipt is an official-docs quote with its URL, a file:line, or a
  command with its output;
- every UNVERIFIABLE HERE row shows an attempted check;
- every row STEP 3 lists has a correction;
- every new claim in a correction has its own "c" row with a verdict and receipt;
- every assumption row that is not VERIFIED or SOURCE: USER has an "assumed:" sentence, or,
  if REFUTED, replacement wording for the recommendation it undermines;
- every live API or web receipt behind a REFUTED or PARTLY row or a correction is saved in
  fc/notes/.
