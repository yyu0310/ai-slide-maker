# Slide guide

This guide covers the judgment calls: when to split a slide, where images go, and what belongs in the speaker notes. Rules a program can check already live in the template and the checks, so nobody has to memorize them. The [full workflow](workflow.md) is a separate page.

## One file is the whole deck

- The CSS at the top sets the look of the deck. In the body, `---` starts a new slide.
- Text inside `<!-- -->` is the speaker's script. The audience never sees it, and it becomes presenter notes in PowerPoint.
- `slides.py map` lists the line numbers of every slide.

| Effect | Syntax |
| --- | --- |
| New slide | `---` |
| Cover or closing slide | `<!-- _class: lead -->` |
| Section divider | `<!-- _class: part -->` |
| Start content at the top (slides center it vertically by default) | `<!-- _class: top -->` |
| Slide with more content | `<!-- _class: dense -->` |
| Hide the page number | `<!-- _paginate: false -->` |
| No header or footer on this slide | `<!-- _header: '' -->`, `<!-- _footer: '' -->` |
| Two classes on one slide | `<!-- _class: top dense -->`, on one line. A second `_class` comment replaces the first |
| Small label above the title | `<div class="kicker">text</div>`, then a blank line before the title |
| Small text | `<span class="small">text</span>` |
| Tag | `<span class="tag">text</span>` |
| Limit image height | `![h:300](./assets/image.png)` |
| Text left, image right | `![bg right:40% contain](./assets/image.png)` |
| Two columns | See below |

Two columns need the blank lines shown here:

```html
<div class="cols">
<div>

**Left heading**

- Point

</div>
<div>

**Right heading**

- Point

</div>
</div>
```

## When to split a slide

Each slide makes one point. `check` tells you whether content got cut off and suggests a fix, but content that fits can still be hard to read.

- More than 5 or 6 points, or 2 long paragraphs: split it.
- A table with more than 5 rows: split it, or use `dense` on that slide.
- A slide with an image: keep the text to 3 or 4 lines.
- A table image that is too wide: keep the header and the key rows, and say in the caption that the rest is left out.
- Write the title as a claim, such as "Growth comes from returning customers", instead of "Revenue analysis".

## Where images go

| Situation | Syntax | Notes |
| --- | --- | --- |
| Text and image side by side | `![bg right:40% contain]` | Add `contain` for screenshots and charts so they show in full. Leave it out for portraits and photos so they fill the space |
| The image is the point | Its own slide, `![h:520]` | Good for long screenshots and news clippings. It stays clear of the header and footer |
| Full background | `![bg]` | The header and footer text sits on top of the image and gets hard to read, so clear `_header` and `_footer` on that slide |
| Image under the text | Title and text first, then `![h:300]` | Don't put an image between two blocks of text |

Save images in `assets/` as `p{page}_{topic}.png`, such as `p17_revenue.png`, so the folder matches the deck at a glance. If a path has a space, wrap it: `![](<my assets/chart.png>)`.

## Table or timeline

- Use a table for comparisons and lists.
- Use a timeline for things that happen in order: one line per step, with `↓` on the line between them.
- Bold only the number. Write `↓ **80%**` so the arrow keeps its color.

## Slides and script

Slides are the finished product for the audience. Reminders to yourself go in the script.

| Content | Where it goes |
| --- | --- |
| A number you still need to confirm, or how to answer a tough question | Script |
| Data year, sample size, source | A source line or caption on the slide, such as "Source: 2025 survey, 212 responses" |
| A conclusion that is uncertain | On the slide, in words like "may" or "tends to" |

## Three HTML traps

- `style="..."` gets dropped. Put styles in a CSS class at the top of the file.
- To use Markdown inside a `<div>`, leave a blank line after the opening tag and before the closing tag.
- Inside an HTML block, a line indented 4 spaces after a blank line turns into a code block.

## When to export

- Export after each part and look at the overview image. Fixing layout as you go beats fixing it all at the end.
- Run `/ai-slide-maker:review` after a first draft or a big rewrite. Small text fixes don't need it.

## Long and short versions

Once the full deck is stable, copy it and cut the copy down to a talk version. Leave the full deck alone so you can always make a new short version from it.

## Layouts that need help

- Maps and architecture diagrams: draw them with code and save them to `assets/`.
- A full-bleed photo with text on top needs a high-resolution original.
- Complex floating layouts don't work well. Use an image or split the slide.

## What it can and can't do

| Item | Status |
| --- | --- |
| Reveal items one by one | Not in this tool's output. PDF and PowerPoint show everything at once |
| Video | Can't be embedded. Insert it in PowerPoint by hand |
| PowerPoint | Each slide is a picture, so the layout matches exactly but the text can't be edited. Speaker notes are kept |
| Editable PowerPoint | Left out on purpose. Marp's experimental `--pptx-editable` lost the speaker notes and images in our test, and turned some Chinese characters into look-alike radicals |
| Rebuilding from an old PDF | Text-based decks are easy. Visual decks need the original images |

## What the checks look for

`qa` needs no browser and finishes almost instantly. `check` renders every slide. A FAIL needs fixing, and a WARN is a heads-up.

| ID | What it finds | Level |
| --- | --- | --- |
| Q1 | Draft markers on a slide, such as TODO or 【待補】 | FAIL |
| Q2 | Image file not found, or a path with a space that isn't wrapped in `<>` | FAIL |
| Q2R | Image from the web, which may not load offline | WARN |
| Q3 | A note to the speaker on a slide, such as "to be confirmed" | FAIL |
| Q3W | Words that may be a note to yourself, such as 我猜 or 推測 | WARN |
| Q4 | A `{{...}}` from the template still there | FAIL |
| Q5 | `style=` that will be dropped | WARN |
| Q6 | Markdown right after an HTML tag with no blank line, which won't render | WARN |
| Q7 | An indented line that turns into a code block | WARN |
| Q8 | Bold wrapped around an arrow | WARN |
| Q9 | A full background running under the header or footer | WARN |
| Q10 | An image with its default screenshot name | WARN |
| Q11 | Two `_class` comments on one slide | WARN |
| Q12 | A file from outside the deck's folder, which would be copied into the export | FAIL |
| Q13 | A comment that never closes and hides the slides after it | FAIL |
| C1 | Content cut off at the edge of a slide | FAIL |
| C2 | Content running into the header or footer | WARN |
| C3 | Text under 16px, hard to read when projected | WARN |
