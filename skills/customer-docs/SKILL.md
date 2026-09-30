---
name: customer-docs
description: Customer-facing writing — release notes, customer communications, and decks read outside the engineering team. Use when writing or reviewing one.
---

# Customer-facing documents

The reader is an **outsider**: they trust the product, never saw the defect, the
investigation, or the internal names, and read the document once to decide what to do.

## Rules

**Predecessor**
- Reuse the predecessor's sections, labels and tone where they fit. Its length is a
  reference, not a limit, and these rules override its format where the two differ.

**Audience**
- A fix states the problem the outsider saw before the fix.
- A change carries its context alongside its outcome: what the outsider sees differently,
  or what it follows from (another entry in the document can supply this). An outcome
  alone, such as "X no longer happens", has neither.
- Use the outsider's vocabulary: what they meet on screen, in a log, or on an output (the
  display, the alarm, a log message). An internal term appears only where the reader
  already meets it.

**Scope and proportion**
- Describe each change at its real scale, in the section and product area it belongs to.
  An edge case gets a brief line that gives its typical size.
- State a customer-visible cost plainly and briefly, e.g. values that shift after
  upgrading.

**Evidence**
- Attribute field findings and state them qualitatively ("analysis of customer data
  indicates … may …"): one site's figures describe that site. Figures that follow from the
  design itself are stated directly.
- Derivations and `file:line` sources go in the message that presents the draft, and stay
  out of the document.

**Tense**
- In a fix entry, the symptom takes unambiguous past tense (*showed*, *recorded*) and the
  fix present tense. A modal (*could*) or a verb spelled the same in both tenses (*read*)
  blurs the symptom. The Cause line is exempt.

**Release notes**
- Sections are commonly Added / Fixed / Changed / Removed.
- Cover the changes this release makes. Merges not in this build, internal or unreleased
  versions, informal deployments and deployment prerequisites go to the deployment
  communication.
- Fixed holds defects the customer experienced: symptom (which may name its trigger), an
  optional one-line "Cause:", then "Now:".
- Changed holds behaviour and calculation changes, edge cases included.
- Each top-level entry opens with a label naming the part of the product where the change
  lives: the predecessor's label where one fits, otherwise a new one in the same form.

**Slides**
- Every element sits fully on the slide.
- Side-by-side comparisons share a comparable, legible text size, with the current item at
  least as large as its reference.
- Keep the template's look and adapt its geometry: resize, move, and tighten indents or
  margins before shrinking text.

## Workflow

To review an existing document, run steps 1 and 3 on it.

1. Read the predecessor (the previous release's notes and deck, or the last communication
   of this kind). Done when its sections and their roles, labels, bullet length and tone
   are known, or the user confirms there is none.
2. Draft the text in Markdown, in chat or as a `.md` the user can edit. Done when every
   line meets the Rules and every figure has a source in the accompanying message.
3. Run `style-check` with category Customer-facing, giving it the predecessor. Done when
   each flag is applied, or shown to the user with the reason it was not.
4. After the user approves the text, generate the Word or PowerPoint files from it. Done
   when every page or slide has been rendered and viewed, and every slide meets the Slides
   rules.
