---
name: new
description: Start a new slide deck from a topic. Use when the user wants to make slides, a presentation, a talk or a pitch deck. Works out who it is for, agrees an outline, then builds the deck.
---

# Start a new slide deck

Reply in the user's language. Write the slides in the language of the talk.

Keep the single quotes around paths. If a path contains a single quote, ask the user to rename the file first.

## 1. Pin down the talk

Ask only what the user has not already told you, all in one message:

- Goal: persuade, teach or share
- Audience: who they are and what they already know
- Length in minutes
- Any format the host requires
- The name and date to show on the cover, if they want them
- Where to save it (default: a new folder named after the talk in the current folder)

Then write one sentence: "In N minutes, this audience will learn this." Show it and wait for the user to agree.

## 2. Agree the outline

Offer these three structures and recommend one:

- Story arc: background, turning point, rising tension, climax, resolution
- Three parts: problem, analysis, solution
- Case-led: each part opens with one concrete case

Write `outline.md` in the deck folder. For each part, list its one-line message, its case, number or activity, and its minutes. Show it and wait for the user to agree before you make any slides.

## 3. Build the deck

```bash
mkdir -p '<folder>/assets'
cp -n "${CLAUDE_PLUGIN_ROOT}/template/slides.md" '<folder>/slides.md'
```

Read `${CLAUDE_PLUGIN_ROOT}/docs/guide.md` before you write a slide. Then:

- Replace every `{{...}}`. Delete any field the user left blank and the layouts you do not use. Keep the CSS at the top of the file.
- Write each title as a claim, not a topic.
- Put what the speaker says in `<!-- -->` comments. The audience never sees them.
- Use only facts and numbers the user gave you or that you can source. Tell the user what is still missing rather than inventing it.
- Save images in `assets/` as `p{page}_{topic}.png`.

After each part, run both checks and fix what they report:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slides.py" qa '<folder>/slides.md'
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slides.py" check '<folder>/slides.md'
```

## 4. Hand it over

Tell the user:

- Where the deck is
- What is still missing, if anything
- They can change it by asking, for example "delete the table on slide 7" or "make slide 5 text on the left, image on the right"
- `/ai-slide-maker:review` gets feedback from three kinds of reader
- `/ai-slide-maker:export` makes the PDF
