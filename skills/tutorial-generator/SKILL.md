---
name: tutorial-generator
description: Generates a structured, self-contained HTML tutorial from a topic and target audience. Use this skill whenever the user wants a tutorial, how-to guide, lesson, walkthrough, explainer, or training material on any subject, even if they only say "teach me X", "explain X step by step", "make a guide for X", or "write onboarding material for X". Covers learning objectives, step-by-step sections, worked examples, a short quiz, and a summary.
---

# Tutorial generator

Turn a topic and an audience into a clear, step-by-step tutorial delivered as ONE self-contained HTML file (no external scripts, fonts, or images) that opens correctly offline.

## Inputs

Collect these. If the user did not give one, assume a sensible default, state the assumption in one line, and continue. Do not interrogate the user.

| Input | Default if missing |
|---|---|
| Topic | required, ask once if absent |
| Audience | complete beginner, comfortable with a computer |
| Level | beginner |
| Length | 5 to 7 sections, about 10 minutes of reading |
| Tone | friendly, plain language, no jargon without a definition |

## Workflow

1. **Define 3 learning objectives.** Each starts with a verb a reader can demonstrate ("Explain...", "Build...", "Identify...").
2. **Outline the sections.** Order them so each section only uses ideas from earlier ones. Start with the one-sentence "what and why", end with a practical result.
3. **Write each section** using the structure below.
4. **Add a 3-question quiz** with answers and a one-line explanation per answer.
5. **Write a summary** of at most 5 bullets and one suggested next step.
6. **Build the HTML file** following the output rules, then save it and present it.

## Section structure

Every section has:
- A heading that states what the reader will do or understand
- 2 to 4 short paragraphs, each making one point
- One concrete example, analogy, or code/command block (when the topic is technical, the example must be runnable or copy-pasteable)
- A "Common mistake" callout when there is a realistic trap

Define a term the first time it appears, in plain words, in the same sentence.

## Accuracy rules

- Do not invent commands, flags, API names, or version numbers. If unsure whether something is current, say so in the text or leave it out.
- For fast-changing topics (tools, SDKs, pricing), tell the reader to check the official docs and link the docs home page if known.
- Never include real client data, secrets, tokens, or personal information in examples. Use obvious placeholders.

## Output rules (HTML)

- Single file, inline CSS only, no JavaScript required to read it.
- Readable on a phone: `<meta name="viewport" ...>`, max-width about 720px, 16px base font, generous line height.
- Support light and dark mode with `prefers-color-scheme`.
- Semantic structure: one `<h1>`, `<h2>` per section, a table of contents linking to section ids, `<pre><code>` for code.
- The quiz answers go in `<details>` elements so the reader can reveal them without JavaScript.
- File name: kebab-case of the topic, for example `what-is-an-mcp-server.html`.

## Final reply

After saving the file, reply with the file, then at most 3 lines: the audience and level you assumed, the section count, and one thing the user could ask you to change (for example "make it more advanced").
