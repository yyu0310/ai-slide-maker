# AGENTS.md

AI Slide Maker helps people make and change slide decks with an AI coding agent. A deck is one Markdown file in [Marp](https://marp.app) format. The readers are people who give talks, and most of them don't write code.

## Use it without the Claude Code plugin

The instructions live in `skills/*/SKILL.md`. In those files, `${CLAUDE_PLUGIN_ROOT}` means the root of this repo, so replace it with the path where you cloned it.

| Task | Instructions |
| --- | --- |
| Start a deck | `skills/new/SKILL.md` |
| Change a deck | `skills/edit/SKILL.md` |
| Check and export | `skills/export/SKILL.md` |
| Three-reader review | `skills/review/SKILL.md` |

## Layout

| Path | Purpose |
| --- | --- |
| `.claude-plugin/` | Plugin and marketplace manifests |
| `skills/` | One folder per command. English only, and they reply in the user's language |
| `scripts/slides.py` | `map`, `qa`, `check`, `export`, `verify`, `sheet` |
| `scripts/review_slides.py` | `prompts`, `verify` |
| `template/slides.md` | The starting deck. Every value to fill in is written as `{{...}}` |
| `examples/demo/` | Sample deck with made-up content |
| `docs/` | Slide guide and workflow, in English and Traditional Chinese |

## Run the tests

```bash
python3 scripts/slides.py --selftest
python3 scripts/review_slides.py --selftest
```

Both run offline in a temp folder. Anything that needs `npx` or a browser is a manual check:

```bash
python3 scripts/slides.py qa examples/demo/slides.md
python3 scripts/slides.py check examples/demo/slides.md
python3 scripts/slides.py export examples/demo/slides.md --pptx
python3 scripts/slides.py verify examples/demo/slides.md
python3 scripts/slides.py sheet examples/demo/slides.md
```

## Rules for changes

- Scripts use the Python standard library only and must run on Python 3.9.
- Write a failing test before you add or change a check, then try it on a real deck. Two early rules looked right in tests and produced false alarms on real decks.
- When you add or change a check, update `RULES` in `slides.py` and the table at the end of both guides.
- `template/slides.md` and `examples/demo/slides.md` carry their own copy of the CSS, because each deck has to work as a single file. Change both.
- `docs/` and all three READMEs move together. English is the main version.
- Keep Marp terms out of the first screen of the README. Readers come for slides.

## Known behavior

- Never run Marp in the deck's folder. A `marp.config.js` there would execute, a `.marprc.yml` could turn on HTML, and an `.npmrc` could swap the package source. `run_marp` uses an empty temp folder, `--no-config-file` and a pinned version. Test before raising the pin.
- Headless Chrome with a private profile writes its output and then never exits. `run_chrome` watches the output and ends Chrome itself. Don't replace it with `subprocess.run`.
- The rendered page lives in a temp folder, so `base_tag` points images back at the deck. Without it images fail quietly and `check` measures a shorter page.
- Every slide in a PPTX has a notes part, even with no notes. `pptx_note_count` reads the text instead of counting files.
- A slide with `![bg right]` renders as three stacked sections. The probe measures only the content layer.
