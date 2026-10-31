# How to make a deck

These are the four steps the author follows from getting a topic to standing on stage. AI works through the first three with you. The fourth is a checklist for the day.

| Step | Result | Command |
| --- | --- | --- |
| 1. Topic and audience | One-sentence goal | `/ai-slide-maker:new` |
| 2. Outline | `outline.md` | `/ai-slide-maker:new` |
| 3. Make the slides | `slides.md`, PDF | `:new`, change things by asking, `:review`, `:export` |
| 4. On the day | Equipment and backups | Check these yourself |

## 1. Topic and audience

Answer four questions before you start:

- Goal: persuade, teach or share
- Audience: students, industry or mixed, and what they already know
- Length in minutes
- Any format or tool the host requires

Then write one sentence: **who will learn what, in how much time.** If you can't settle this sentence, the deck will drift.

## 2. Outline

Pick a structure:

| Structure | Order | Good for |
| --- | --- | --- |
| Story arc | Background, turning point, rising tension, climax, resolution | Personal stories, founder talks |
| Three parts | Problem, analysis, solution | Proposals, reports |
| Case-led | Each part opens with one concrete case | Teaching, explaining a topic |

For each part, settle three things:

- Its one-line message
- The case, number or activity it uses
- How many minutes it gets

Finish the outline before you make slides. This is the cheapest point to change direction.

## 3. Make the slides

1. Work through the outline one part at a time, and export after each part to look at the overview image.
2. Put what you will say in the speaker notes. Keep only what the audience needs on the slide.
3. Save images in `assets/` as `p{page}_{topic}.png`.
4. After the first draft, run `/ai-slide-maker:review`. Three kinds of reader find problems, and you decide what to do with each one.
5. Finish with `/ai-slide-maker:export`, which checks the deck before it exports.

For a shorter slot, wait until the full deck is stable, then copy it and cut the copy down. Leave the full deck alone.

The folder looks like this:

| File | Purpose |
| --- | --- |
| `slides.md` | The deck, with speaker notes |
| `slides.pdf` | The exported result |
| `outline.md` | The outline |
| `assets/` | Images |

## 4. On the day

Don't rely on the host. Check every link in the chain yourself.

- Bring your own HDMI and USB-C to HDMI adapters, and test them before you leave
- Keep two backups: a USB drive and a cloud link
- Arrive early to connect, and confirm the screen shows 16:9
- Turn off notifications and the screen saver, and turn on Do Not Disturb

See the [slide guide](guide.md) for layout decisions.
