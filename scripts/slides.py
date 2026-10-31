#!/usr/bin/env python3
# slides.py: check, export and preview slides written in Marp Markdown.
"""
The small CLI behind /ai-slide-maker:export. Standard library only.

Subcommands:
  map <file.md>               List each slide with its line numbers and title
  qa <file.md>                Static checks, no network or browser needed
  check <file.md>             Render every slide and report content that gets cut off
  export <file.md> [--pptx]   Export a PDF, and a PPTX on request, with npx @marp-team/marp-cli
  verify <file.md>            Check the exported files exist, are fresh and kept the speaker notes
  sheet <file.md> [--out P]   Render every slide into one overview PNG

Exit codes:
  0  success
  2  external command (npx or Chrome) failed or timed out
  3  input file missing or not a .md file
  4  hard gate FAIL (a check found problems)
  5  environment missing (npx or Chrome not found)

--selftest runs the built-in tests in a temp folder. Anything that needs npx or
Chrome is a manual check because the first run downloads a package.
"""
import argparse
import contextlib
import glob
import html as html_lib
import json
import math
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zipfile

VERSION = "0.1.0"
DEFAULT_TIMEOUT = 300
CHECK_TIMEOUT = 120
MARP_PACKAGE = "@marp-team/marp-cli@4.5.1"  # pinned: test before raising it
SHEET_WIDTH = 1920
SHEET_COLUMNS = 3
SHEET_GAP = 8

# rule id: (level, the problem, how to fix it)
RULES = {
    "Q1": ("FAIL", "draft marker on a slide", "finish it, or move it into speaker notes"),
    "Q2": ("FAIL", "image file not found", "fix the path or add the file"),
    "Q2R": ("WARN", "file from the web: it may not load offline, and loading it tells that server the deck was opened",
            "download it into assets/"),
    "Q3": ("FAIL", "note to the speaker on a slide",
           "move it into speaker notes (<!-- -->), or reword it as a source or caption"),
    "Q3W": ("WARN", "this may be a note to yourself", "if it is, move it into speaker notes"),
    "Q4": ("FAIL", "template placeholder not replaced", "replace the {{...}} text"),
    "Q5": ("WARN", "inline style= is dropped on export", "use a CSS class instead"),
    "Q6": ("WARN", "Markdown inside an HTML block is not rendered",
           "put a blank line after the opening tag and before the closing tag"),
    "Q7": ("WARN", "indented line after a blank line turns into a code block",
           "remove the blank line or the indent"),
    "Q8": ("WARN", "bold also colors the arrow", "write ↓ **80%** instead of **↓ 80%**"),
    "Q9": ("WARN", "full-slide background runs under the header and footer",
           "use ![bg right:40% contain], an inline ![h:520] image, or clear _header and _footer on this slide"),
    "Q10": ("WARN", "image still has its default screenshot name", "rename it to p{page}_{topic}.png"),
    "Q11": ("WARN", "two _class comments on one slide, so only the last one counts",
            "put them together: <!-- _class: top dense -->"),
    "Q12": ("FAIL", "file from outside the deck's folder, which would be copied into the export",
            "copy the file into assets/. If someone else gave you this deck, check why it asks for this file"),
    "Q13": ("FAIL", "comment never closed, which hides everything after it", "add -->"),
}

FRONTMATTER_RE = re.compile(r"\A\s*---[ \t]*\n.*?^---[ \t]*$", re.S | re.M)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
STYLE_RE = re.compile(r"<style\b.*?</style>", re.S | re.I)
FENCE_RE = re.compile(r"^(`{3,}|~{3,}).*?(?:^\1[ \t]*$|\Z)", re.S | re.M)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
RULER_RE = re.compile(r"^ {0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$")

IMG_RE = re.compile(r"!\[[^\]]*\]\(((?:[^()]|\([^()]*\))+)\)")
ATTR_REF_RE = re.compile(r"\b(?:src|srcset|poster)\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))", re.I)
CSS_REF_RE = re.compile(r"url\(\s*[\"']?([^\"')\s]+)|@import\s+[\"']([^\"']+)", re.I)
TITLE_SUFFIX_RE = re.compile(r'^(.*?)\s+(?:"[^"]*"|\'[^\']*\')$')

# Draft markers: TODO / FIXME / TBD / XXX as whole ASCII words (\b fails next to
# Chinese), and 【 only when it opens a "fill me in" note, since 【案例】 is a normal heading.
DRAFT_RE = re.compile(r"(?<![A-Za-z0-9_])(?:TODO|FIXME|TBD|XXX)(?![A-Za-z0-9_])|【(?:fill|待|補|新增|重點|修改|草稿|暫)")
SPEAKER_NOTE_RE = re.compile(
    r"待驗證|待核實|須核實|需核實|外部知識|待確認|待補(?![助貼償])|(?i:to be confirmed)|\bTBC\b")
SOFT_NOTE_RE = re.compile(r"推測|假設性|我猜|不確定(?!性)")  # also normal words, so only a WARN
PLACEHOLDER_RE = re.compile(r"\{\{.+?\}\}")
INLINE_STYLE_RE = re.compile(r"\bstyle\s*=\s*[\"']", re.I)
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ARROWS = tuple("↓↑→←⬇⬆➡⬅")
SCREENSHOT_RE = re.compile(r"截圖|螢幕快照|Screen ?Shot|Screen Recording", re.I)
FULL_BG_RE = re.compile(r"!\[([^\]]*\bbg\b[^\]]*)\]\(")

# CommonMark: these tags open an HTML block that runs to the next blank line,
# and Markdown inside that block stays as plain text. span is inline, so it is fine.
HTML_BLOCK_RE = re.compile(r"^ {0,3}</?(?:div|p|ul|ol|li|table|thead|tbody|tr|td|th|section|blockquote|h[1-6])\b", re.I)
MD_BLOCK_RE = re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|\|)")
MD_INLINE_RE = re.compile(r"\*\*[^*\s][^*]*\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)")
OPEN_TAG_RE = re.compile(r"<(?:div|ul|ol|table|tr|td|th|li|section|blockquote)\b[^>/]*>", re.I)
CLOSE_TAG_RE = re.compile(r"</(?:div|ul|ol|table|tr|td|th|li|section|blockquote)\s*>", re.I)
INDENT_RE = re.compile(r"^(?: {4}|\t)")

DIRECTIVE_RE = re.compile(
    r"_?(?:headingDivider|marp|theme|style|size|math|title|description|author|image|keywords|url|lang|"
    r"paginate|header|footer|class|backgroundColor|backgroundImage|backgroundPosition|"
    r"backgroundRepeat|backgroundSize|color|transition)\s*:")
NOTE_RUN_RE = re.compile(r"<a:t\b[^>]*>([^<]*)</a:t>")
PROBE_RESULT_RE = re.compile(r'<pre id="slides-probe">(.*?)</pre>', re.S)

# Runs inside the rendered page. Marp clips each slide silently, so this measures
# every element against its slide. Background layers are skipped: a slide with
# ![bg right] renders as three stacked sections and only the content one counts.
# Under 5px is rendering noise. Under 16px is hard to read when projected.
PROBE = r"""<pre id="slides-probe"></pre><script>
addEventListener('load',()=>{document.fonts.ready.then(()=>{
 const svg=document.querySelector('svg[data-marpit-svg]');
 const k=svg.viewBox.baseVal.width/svg.getBoundingClientRect().width;
 const out=[];
 document.querySelectorAll('svg[data-marpit-svg]>foreignObject>section').forEach(sec=>{
  const layer=sec.getAttribute('data-marpit-advanced-background');
  if(layer==='background'||layer==='pseudo')return;
  const r=sec.getBoundingClientRect();
  const bar=tag=>{const e=sec.querySelector(':scope > '+tag);return e&&e.textContent.trim()?e.getBoundingClientRect():null};
  const hd=bar('header'),ft=bar('footer');
  let over=null,touch=null,small=null;
  sec.querySelectorAll('*').forEach(el=>{
   if(el.closest('header,footer,style,script,svg:not([data-marpit-svg])'))return;
   const b=el.getBoundingClientRect();
   if(!b.width||!b.height)return;
   const text=(el.textContent||'').trim().slice(0,40);
   const ownText=[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
   const size=parseFloat(getComputedStyle(el).fontSize);
   if(ownText&&size<16&&(!small||size<small.px))small={px:Math.round(size),text};
   const sides={bottom:b.bottom-r.bottom,top:r.top-b.top,right:b.right-r.right,left:r.left-b.left};
   if(text||el.tagName==='IMG')for(const side in sides){const px=sides[side]*k;if(px>5&&(!over||px>over.px))over={px:Math.round(px),side,text}}
   if(ft&&b.bottom>ft.top+1&&b.top<ft.bottom){const px=(b.bottom-ft.top)*k;if(!touch||px>touch.px)touch={px:Math.round(px),bar:'footer',text}}
   if(hd&&b.top<hd.bottom-1&&b.bottom>hd.top){const px=(hd.bottom-b.top)*k;if(!touch||px>touch.px)touch={px:Math.round(px),bar:'header',text}}
  });
  out.push({over,touch,small});
 });
 document.getElementById('slides-probe').textContent=JSON.stringify(out);
});});
</script>"""

SHEET_CSS = (
    "<style>html,body{margin:0!important;background:#666!important;height:auto!important;overflow:visible!important}"
    f"body{{display:grid!important;grid-template-columns:repeat({SHEET_COLUMNS},1fr);"
    f"gap:{SHEET_GAP}px;padding:{SHEET_GAP}px;box-sizing:border-box}}"
    "svg[data-marpit-svg]{width:100%!important;height:auto!important;display:block!important;margin:0!important}</style>"
)


def log(msg):
    print(f"[slides] {msg}", flush=True)


def check_md_file(path):
    if not os.path.isfile(path):
        log(f"ERROR: file not found: {path}")
        return 3
    if not path.endswith(".md"):
        log(f"ERROR: not a .md file: {path}")
        return 3
    return None


def read_text(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def _extract_img_url(raw):
    """`pic.png "title"` -> `pic.png`. Strips a trailing quoted title, keeps spaces in the path."""
    raw = raw.strip()
    m = TITLE_SUFFIX_RE.match(raw)
    return m.group(1).strip() if m else raw


def find_npx():
    """Return (npx_path, bin_dir) or (None, None). Falls back to common Homebrew and nvm locations."""
    found = shutil.which("npx")
    if found:
        return found, os.path.dirname(found)
    candidates = ["/opt/homebrew/bin/npx", "/usr/local/bin/npx"]
    candidates += sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/npx")), reverse=True)
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c, os.path.dirname(c)
    return None, None


def find_chrome():
    """Return a Chrome-family browser, or None. CHROME_PATH wins when it points at a real program."""
    env = os.environ.get("CHROME_PATH")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    apps = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for app in apps:
        if os.path.isfile(app):
            return app
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def blank(pattern, text):
    """Replace each match with spaces so line numbers stay correct."""
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def strip_comments(text):
    """Blank out comments. Inline code is skipped, so `<!--` in a sentence stays text."""
    out, pos = [], 0
    for m in COMMENT_RE.finditer(blank(INLINE_CODE_RE, text)):
        out += [text[pos:m.start()], re.sub(r"[^\n]", " ", m.group(0))]
        pos = m.end()
    return "".join(out) + text[pos:]


def visible_text(text):
    """What the audience reads: no frontmatter, no speaker notes."""
    return strip_comments(blank(FRONTMATTER_RE, text))


def body_text(text):
    """Visible text without CSS or code blocks, for checks on the slide markup."""
    return blank(FENCE_RE, blank(STYLE_RE, visible_text(text)))


def lines_matching(text, pattern):
    return [(i, line.strip()) for i, line in enumerate(text.split("\n"), 1) if pattern.search(line)]


def slide_ranges(text):
    """[(first_line, last_line)] per slide, 1-based. A --- inside notes or code is not a new slide."""
    lines = body_text(text).split("\n")
    fm = FRONTMATTER_RE.match(text)
    start = fm.group(0).count("\n") + 2 if fm else 1
    ranges, first = [], start
    for i in range(start, len(lines) + 1):
        line = lines[i - 1]
        # --- right under a line of text turns that line into a heading.
        heading = line.strip().startswith("-") and i > start and lines[i - 2].strip()
        if RULER_RE.match(line) and not heading:
            ranges.append((first, i - 1))
            first = i + 1
    ranges.append((first, len(lines)))
    return ranges


def slide_map(text):
    """[(slide number, first line, last line, title)], so "slide 17" becomes exact lines."""
    raw, shown = text.split("\n"), body_text(text).split("\n")
    rows = []
    for n, (first, last) in enumerate(slide_ranges(text), 1):
        lines = [line.strip() for line in shown[first - 1:last] if line.strip()]
        used = [i for i in range(first, last + 1) if raw[i - 1].strip()]
        first, last = (used[0], used[-1]) if used else (first, last)
        headings = [line.lstrip("#").strip() for line in lines if re.match(r"#{1,6}\s", line)]
        rows.append((n, first, last, (headings or lines or ["(empty)"])[0]))
    return rows


def ref_kind(url):
    """Sort a file reference into data, remote, outside (leaves the deck's folder) or local."""
    if url.startswith("data:"):
        return "data"
    if url.startswith(("http://", "https://", "//")):
        return "remote"
    path = urllib.parse.unquote(url)
    if path.startswith(("file:", "/", "~", "\\")) or re.match(r"[A-Za-z]:[\\/]", path):
        return "outside"
    return "outside" if os.path.normpath(path).startswith("..") else "local"


def image_findings(body, md_dir, source):
    found = []
    for i, line in enumerate(body.split("\n"), 1):
        refs = []
        for m in IMG_RE.finditer(line):
            url = _extract_img_url(m.group(1))
            wrapped = url.startswith("<") and url.endswith(">")
            # An unwrapped path with a space is not an image in Markdown: it prints as raw text.
            refs.append((url[1:-1] if wrapped else url, " " in url and not wrapped))
        refs += [(next(g for g in m.groups() if g), False) for m in ATTR_REF_RE.finditer(line)]
        for url, broken in refs:
            kind = ref_kind(url)
            if kind == "remote":
                found.append(("Q2R", i, url))
            elif kind == "outside":
                found.append(("Q12", i, url))
            elif kind == "local":
                # Accept the decoded form of %20. Try the literal path first: a file name can contain %20.
                decoded = urllib.parse.unquote(url)
                if broken:
                    found.append(("Q2", i, f"{url} (write the path as <{url}>)"))
                elif not any(os.path.isfile(os.path.join(md_dir, p)) for p in (url, decoded)):
                    found.append(("Q2", i, url))
                if SCREENSHOT_RE.search(decoded):
                    found.append(("Q10", i, url))
    # CSS can pull files in too, and it lives in the frontmatter and <style> blocks.
    for i, line in enumerate(source.split("\n"), 1):
        for m in CSS_REF_RE.finditer(line):
            url = m.group(1) or m.group(2)
            kind = ref_kind(url)
            if kind == "remote":
                found.append(("Q2R", i, url))
            elif kind == "outside":
                found.append(("Q12", i, url))
    return found


def html_block_findings(body):
    found = []
    in_block = False  # ends at the next blank line
    depth = 0  # open tags, which survive blank lines
    after_blank = False
    for i, line in enumerate(body.split("\n"), 1):
        if not line.strip():
            in_block = False
            after_blank = True
            continue
        if depth > 0 and after_blank and INDENT_RE.match(line):
            found.append(("Q7", i, line.strip()))
        opens = HTML_BLOCK_RE.match(line)
        if opens:
            in_block = True
        if in_block and (MD_INLINE_RE.search(line) or (not opens and MD_BLOCK_RE.match(line))):
            found.append(("Q6", i, line.strip()))
        depth = max(0, depth + len(OPEN_TAG_RE.findall(line)) - len(CLOSE_TAG_RE.findall(line)))
        after_blank = False
    return found


def full_background_findings(text, body):
    fm = FRONTMATTER_RE.match(text)
    head = fm.group(0) if fm else ""
    bars = [k for k in ("header", "footer") if re.search(rf"^{k}:[ \t]*['\"]?[^'\"\s]", head, re.M)]
    if not bars:
        return []
    raw, shown = text.split("\n"), body.split("\n")
    found = []
    for first, last in slide_ranges(text):
        if all(f"_{k}:" in "\n".join(raw[first - 1:last]) for k in bars):
            continue  # this slide clears its own header and footer
        for i in range(first, last + 1):
            for m in FULL_BG_RE.finditer(shown[i - 1]):
                if not re.search(r"\b(?:left|right)\b", m.group(1)):
                    found.append(("Q9", i, shown[i - 1].strip()))
    return found


def class_findings(text):
    raw = blank(FENCE_RE, text).split("\n")
    found = []
    for first, last in slide_ranges(text):
        hits = [i for i in range(first, last + 1) if re.search(r"<!--\s*_class\s*:", raw[i - 1])]
        found += [("Q11", i, raw[i - 1].strip()) for i in hits[1:]]
    return found


def run_rules(text, md_dir):
    """Return [(rule, line number, detail)] for every problem in a deck."""
    visible = visible_text(text)
    body = body_text(text)
    # Header and footer text sits in the frontmatter, so placeholders are checked there too.
    source = blank(FENCE_RE, strip_comments(text))

    found = [("Q1", i, line) for i, line in lines_matching(visible, DRAFT_RE)]
    found += [("Q3", i, line) for i, line in lines_matching(visible, SPEAKER_NOTE_RE)]
    found += [("Q3W", i, line) for i, line in lines_matching(visible, SOFT_NOTE_RE)]
    found += [("Q4", i, line) for i, line in lines_matching(source, PLACEHOLDER_RE)]
    found += [("Q5", i, line) for i, line in lines_matching(body, INLINE_STYLE_RE)]
    # Pair the ** first: in `**a** → b` the arrow follows a closing **.
    found += [("Q8", i, line.strip()) for i, line in enumerate(body.splitlines(), 1)
              if any(m.group(1).strip().startswith(ARROWS) for m in BOLD_RE.finditer(line))]
    found += image_findings(body, md_dir, source)
    found += [("Q13", i, line) for i, line in lines_matching(blank(INLINE_CODE_RE, source), re.compile("<!--"))]
    found += html_block_findings(body)
    found += full_background_findings(text, body)
    found += class_findings(text)
    return found


def is_note(comment):
    inner = comment[4:-3].strip()
    return bool(inner) and inner != "fit" and not DIRECTIVE_RE.match(inner)


def count_notes(text):
    """Slides with a speaker note. Marp directives are comments too, so they are skipped."""
    raw = blank(FENCE_RE, text).split("\n")
    total = 0
    for first, last in slide_ranges(text):
        if any(is_note(c) for c in COMMENT_RE.findall("\n".join(raw[first - 1:last]))):
            total += 1
    return total


def pptx_note_count(path):
    """Slides whose notes hold real text. Every slide gets a notes part, so counting parts proves nothing."""
    total = 0
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name):
                    # The last run is the slide number.
                    if any(r.strip() for r in NOTE_RUN_RE.findall(z.read(name).decode("utf-8"))[:-1]):
                        total += 1
    except zipfile.BadZipFile:
        log(f"ERROR: not a valid PPTX: {path}")
        return -1
    return total


def base_tag(md_dir):
    return f'<base href="{pathlib.Path(md_dir).as_uri()}/">'


def inject(page, head="", body=""):
    """Add to the top of <head> and before the real closing </body>."""
    page = page.replace("<head>", "<head>" + head, 1)
    before, tag, after = page.rpartition("</body>")
    return before + body + tag + after


def parse_probe(dom):
    m = PROBE_RESULT_RE.search(dom)
    if not m or not m.group(1).strip():
        return None
    try:
        return json.loads(html_lib.unescape(m.group(1)))
    except ValueError:
        return None


def page_shape(page):
    """Return (slide count, slide width, slide height). The page also holds other svg, such as theme icons."""
    tags = re.findall(r"<svg\b[^>]*\bdata-marpit-svg\b[^>]*>", page)
    view = re.search(r'viewBox="0 0 (\d+) (\d+)"', tags[0]) if tags else None
    return (len(tags), *(map(int, view.groups()) if view else (1280, 720)))


def sheet_size(slides, view_w, view_h):
    cell_w = (SHEET_WIDTH - SHEET_GAP * (SHEET_COLUMNS + 1)) / SHEET_COLUMNS
    rows = math.ceil(slides / SHEET_COLUMNS)
    return SHEET_WIDTH, math.ceil(rows * (cell_w * view_h / view_w + SHEET_GAP) + SHEET_GAP)


def run_marp(args, timeout):
    """Run marp-cli with absolute paths from an empty folder. Returns 0, 2 or 5.

    Never run it in the deck's folder. A marp.config.js there would execute, a
    .marprc.yml could turn on HTML and scripts, and an .npmrc could swap the
    package source. That matters when someone else gave you the folder.
    """
    npx, bin_dir = find_npx()
    if npx is None:
        log("ERROR: npx not found. Install Node.js (brew install node, or nvm install --lts)")
        return 5
    env = dict(os.environ)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    try:
        with work_dir() as cwd:
            # --no-stdin plus stdin=DEVNULL: marp-cli hangs waiting on stdin otherwise.
            r = subprocess.run(
                [npx, "--yes", MARP_PACKAGE, "--no-stdin", "--no-config-file", "--allow-local-files", *args],
                cwd=cwd, capture_output=True, text=True, timeout=timeout,
                stdin=subprocess.DEVNULL, env=env,
            )
    except subprocess.TimeoutExpired:
        log(f"ERROR: npx timed out after {timeout}s")
        return 2
    if r.returncode != 0:
        log(f"ERROR: npx failed (returncode={r.returncode})")
        print("\n".join(r.stderr.splitlines()[-30:]), file=sys.stderr)
        return 2
    return 0


def cmd_map(path):
    err = check_md_file(path)
    if err:
        return err
    for n, first, last, title in slide_map(read_text(path)):
        print(f"slide {n}: lines {first}-{last}: {title}")
    return 0


def cmd_qa(path):
    err = check_md_file(path)
    if err:
        return err

    findings = run_rules(read_text(path), os.path.dirname(os.path.abspath(path)))
    fails = warns = 0
    for rule in RULES:
        hits = [f for f in findings if f[0] == rule]
        if not hits:
            continue
        level, problem, fix = RULES[rule]
        log(f"{level} {rule}: {problem}. Fix: {fix}")
        for _, lineno, detail in hits:
            print(f"  line {lineno}: {detail}")
        if level == "FAIL":
            fails += len(hits)
        else:
            warns += len(hits)
    log(f"qa: {fails} FAIL, {warns} WARN")
    return 4 if fails else 0


def render_page(path, work, timeout):
    """Render the deck to one HTML page in `work`. Returns (exit code, page text)."""
    out = os.path.join(work, "slides.html")
    rc = run_marp(["--template", "bare", os.path.abspath(path), "-o", out], timeout)
    if rc:
        return rc, None
    return 0, read_text(out)


def run_chrome(chrome, work, args, is_done, timeout):
    """Run headless Chrome until is_done(stdout) is true. Returns (exit code, stdout).

    The private profile keeps it away from the user's open Chrome. With a private
    profile Chrome writes its output and then never exits (seen on Chrome 154,
    whatever the flags), so this watches the output and ends Chrome itself.
    """
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           f"--user-data-dir={os.path.join(work, 'profile')}", "--virtual-time-budget=8000", *args]
    out_path = os.path.join(work, "chrome.out")

    def output():
        with open(out_path, encoding="utf-8", errors="replace") as f:
            return f.read()

    with open(out_path, "w") as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            exited = proc.poll() is not None
            text = output()
            if is_done(text):
                return 0, text
            if exited:
                log(f"ERROR: browser stopped without output (returncode={proc.returncode})")
                return 2, ""
            time.sleep(0.1)
        log(f"ERROR: browser timed out after {timeout}s")
        return 2, ""
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # Chrome's helper processes share this group
        except (AttributeError, OSError):
            proc.kill()
        proc.wait()


def png_complete(path):
    try:
        with open(path, "rb") as f:
            f.seek(-8, os.SEEK_END)
            return f.read() == b"IEND\xaeB`\x82"
    except OSError:
        return False


@contextlib.contextmanager
def work_dir():
    path = tempfile.mkdtemp(prefix="slides-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def overflow_fix(px, side, view_h):
    if side in ("left", "right"):
        return "make it narrower: shorten the text or drop a column"
    if px <= view_h * 0.2:
        return "add <!-- _class: dense --> or cut a line or two"
    return "Split the slide, or cut the text"


def cmd_check(path, timeout=CHECK_TIMEOUT):
    err = check_md_file(path)
    if err:
        return err
    chrome = find_chrome()
    if chrome is None:
        log("ERROR: Chrome not found. Install Chrome, or set CHROME_PATH")
        return 5

    md_dir = os.path.dirname(os.path.abspath(path))
    with work_dir() as work:
        rc, page = render_page(path, work, timeout)
        if rc:
            return rc
        view_h = page_shape(page)[2]
        # The page lives in a temp folder, so <base> points images back at the deck.
        probe = os.path.join(work, "probe.html")
        with open(probe, "w", encoding="utf-8") as f:
            f.write(inject(page, head=base_tag(md_dir), body=PROBE))
        rc, dom = run_chrome(chrome, work, ["--window-size=1280,720", "--dump-dom", pathlib.Path(probe).as_uri()],
                             lambda text: text.rstrip().endswith("</html>"), timeout)
        if rc:
            return rc

    rows = parse_probe(dom)
    if rows is None:
        log("ERROR: the browser returned no result")
        return 2

    fails = warns = 0
    for n, row in enumerate(rows, 1):
        over, touch, small = row["over"], row["touch"], row["small"]
        if over:
            fails += 1
            log(f"FAIL C1 slide {n}: cut off by {over['px']}px at the {over['side']}, near: {over['text']!r}. "
                f"Fix: {overflow_fix(over['px'], over['side'], view_h)}")
        if touch:
            warns += 1
            log(f"WARN C2 slide {n}: runs {touch['px']}px into the {touch['bar']}, near: {touch['text']!r}")
        if small:
            warns += 1
            log(f"WARN C3 slide {n}: {small['px']}px text is hard to read when projected, near: {small['text']!r}")
    log(f"check: {len(rows)} slides, {fails} FAIL, {warns} WARN")
    return 4 if fails else 0


def cmd_export(path, timeout=DEFAULT_TIMEOUT, pptx=False):
    err = check_md_file(path)
    if err:
        return err

    abspath = os.path.abspath(path)
    stem = abspath[: -len(".md")]

    for fmt in ["pdf", "pptx"] if pptx else ["pdf"]:
        log(f"exporting {os.path.basename(stem)}.{fmt}")
        rc = run_marp([abspath, f"--{fmt}", "-o", f"{stem}.{fmt}"], timeout)
        if rc:
            return rc
        log(f"export finished: {stem}.{fmt}")
    return 0


def cmd_verify(path):
    err = check_md_file(path)
    if err:
        return err

    abspath = os.path.abspath(path)
    pdf_path = abspath[: -len(".md")] + ".pdf"
    pptx_path = abspath[: -len(".md")] + ".pptx"
    md_mtime = os.path.getmtime(abspath)

    ok = True

    exists = os.path.isfile(pdf_path)
    log(f"{'OK  ' if exists else 'FAIL'} PDF exists: {pdf_path}")
    ok = ok and exists

    if exists:
        size = os.path.getsize(pdf_path)
        size_ok = size > 0
        log(f"{'OK  ' if size_ok else 'FAIL'} PDF size > 0 ({size} bytes)")
        ok = ok and size_ok

        pdf_mtime = os.path.getmtime(pdf_path)
        mtime_ok = pdf_mtime >= md_mtime
        log(f"{'OK  ' if mtime_ok else 'FAIL'} PDF is not older than the .md")
        ok = ok and mtime_ok
    else:
        log("FAIL PDF size > 0 (skipped, file missing)")
        log("FAIL PDF is not older than the .md (skipped, file missing)")

    if os.path.isfile(pptx_path):
        fresh = os.path.getmtime(pptx_path) >= md_mtime
        log(f"{'OK  ' if fresh else 'FAIL'} PPTX is not older than the .md")
        want = count_notes(read_text(abspath))
        got = pptx_note_count(pptx_path)
        notes_ok = got >= want
        log(f"{'OK  ' if notes_ok else 'FAIL'} PPTX kept the speaker notes ({got} of {want} slides)")
        ok = ok and fresh and notes_ok

    return 0 if ok else 4


def cmd_sheet(path, out=None, timeout=CHECK_TIMEOUT):
    err = check_md_file(path)
    if err:
        return err
    chrome = find_chrome()
    if chrome is None:
        log("ERROR: Chrome not found. Install Chrome, or set CHROME_PATH")
        return 5

    abspath = os.path.abspath(path)
    out = os.path.abspath(out) if out else abspath[: -len(".md")] + ".sheet.png"
    with work_dir() as work:
        rc, page = render_page(path, work, timeout)
        if rc:
            return rc
        slides, view_w, view_h = page_shape(page)
        width, height = sheet_size(slides, view_w, view_h)
        sheet = os.path.join(work, "sheet.html")
        with open(sheet, "w", encoding="utf-8") as f:
            f.write(inject(page, head=base_tag(os.path.dirname(abspath)) + SHEET_CSS))
        # Shoot into the temp folder: an old sheet at `out` would already look complete.
        shot = os.path.join(work, "sheet.png")
        rc, _ = run_chrome(chrome, work, [f"--window-size={width},{height}", f"--screenshot={shot}",
                                          pathlib.Path(sheet).as_uri()], lambda _: png_complete(shot), timeout)
        if rc:
            return rc
        shutil.copyfile(shot, out)

    log(f"sheet: {slides} slides -> {out}")
    return 0


def run_selftest():
    results = []

    def check(name, cond):
        results.append((name, cond))
        log(f"[{'PASS' if cond else 'FAIL'}] {name}")

    def write(path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def fake_pptx(path, notes):
        # Real files carry one notes part per slide, with the slide number as a second run.
        with zipfile.ZipFile(path, "w") as z:
            for i, note in enumerate(notes, 1):
                z.writestr(f"ppt/notesSlides/notesSlide{i}.xml",
                           f'<p:notes><a:t>{note}</a:t><a:t lang="en">{i}</a:t></p:notes>')

    with tempfile.TemporaryDirectory(prefix="slides selftest ") as tmp:
        os.makedirs(os.path.join(tmp, "assets"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "my assets"), exist_ok=True)
        for name in ("assets/ok.png", "my assets/pic one.png", "a%20b.png", "assets/chart (1).png"):
            with open(os.path.join(tmp, name), "wb") as f:
                f.write(b"\x89PNG fake")

        head = "---\nmarp: true\nheader: 'Talk'\n---\n\n"

        # rule, slide source, should the rule fire?
        cases = [
            ("Q1", "# T\n\nTODO: add chart\n", True),
            ("Q1", "# T\n\n【fill in】 content\n", True),
            ("Q1", "# T\n\nThe mastodon slide is fine\n", False),
            ("Q1", "# T\n\n<!-- TODO: check this number -->\n", False),
            ("Q1", "這裡TODO補圖\n", True),
            ("Q1", "【待補】圖表\n", True),
            ("Q1", "【案例】台積電\n", False),
            ("Q1", "Use `<!--` here\n\nTODO\n\n<!-- ok -->\n", True),
            ("Q2", "![a](assets/not_exist.png)\n", True),
            ("Q2", '<img src="assets/not_exist.png">\n', True),
            ("Q2", "![a](assets/ok.png)\n", False),
            ("Q2", '<img class="w" src="assets/ok.png">\n', False),
            ("Q2", "![bg fit](assets/ok.png)\n", False),
            ("Q2", '![a](my assets/pic one.png "caption")\n', True),
            ("Q2", '![a](<my assets/pic one.png> "caption")\n', False),
            ("Q2", "![a](my%20assets/pic%20one.png)\n", False),
            ("Q2", "![a](a%20b.png)\n", False),
            ("Q2", "![a](assets/chart (1).png)\n", True),
            ("Q2", "![a](<assets/chart (1).png>)\n", False),
            ("Q2", "<!-- ![old](assets/not_exist.png) -->\n", False),
            ("Q2", '<img src="data:image/png;base64,AAAA">\n', False),
            ("Q2R", "![remote](https://example.com/pic.png)\n", True),
            ("Q2R", "![a](assets/ok.png)\n", False),
            ("Q3", "# T\n\n這個數字待核實\n", True),
            ("Q3", "# T\n\nFigures to be confirmed\n", True),
            ("Q3", "# T\n\n不確定性很高\n", False),
            ("Q3", "# T\n\n<!-- 這個數字待核實 -->\n", False),
            ("Q3", "申請待補助\n", False),
            ("Q3", "我猜你也遇過\n", False),
            ("Q3W", "我猜你也遇過\n", True),
            ("Q3W", "今天天氣很好\n", False),
            ("Q12", "![a](../secret.png)\n", True),
            ("Q12", "![a](/etc/logo.png)\n", True),
            ("Q12", '<img src="file:///tmp/x.png">\n', True),
            ("Q12", "<style>\n@import 'file:///tmp/x.css';\n</style>\n", True),
            ("Q12", "---\nmarp: true\nstyle: |\n  a { background: url(../x.png); }\n---\n\n# T\n", True),
            ("Q12", "![a](assets/ok.png)\n", False),
            ("Q12", "![bg](./assets/ok.png)\n", False),
            ("Q12", "![a](assets/../assets/ok.png)\n", False),
            ("Q2R", "<style>\n@import url('https://example.com/a.css');\n</style>\n", True),
            ("Q2R", "<video src=https://example.com/a.mp4></video>\n", True),
            ("Q13", "# A\n\n<!-- never closed\n\n---\n\n# B\n", True),
            ("Q13", "# A\n\n`<!--` is a comment\n\n---\n\n# B\n\n<!-- ok -->\n", False),
            ("Q4", "# {{title}}\n", True),
            ("Q4", "---\nmarp: true\nheader: '{{title}}'\n---\n\n# T\n", True),
            ("Q4", "# Real title\n", False),
            ("Q4", "```\n{{ jinja }}\n```\n", False),
            ("Q4", "# T\n\n<!-- {{ask the host}} -->\n", False),
            ("Q5", '<div style="color:red">a</div>\n', True),
            ("Q5", '<div class="a">a</div>\n', False),
            ("Q5", "---\nmarp: true\nstyle: |\n  section { color: red; }\n---\n\n# T\n", False),
            ("Q5", '```html\n<div style="color:red">a</div>\n```\n', False),
            ("Q6", '<div class="a">**x**</div>\n', True),
            ("Q6", '<div class="a">\n**x**\n</div>\n', True),
            ("Q6", '<div class="a">\n\n**x**\n\n</div>\n', False),
            ("Q6", 'Inline <span class="a">**x**</span> is fine\n', False),
            ("Q6", '<div class="kicker">Label</div>\n# Title\n', True),
            ("Q6", '<div class="kicker">Label</div>\n\n# Title\n', False),
            ("Q11", "<!-- _class: top -->\n<!-- _class: dense -->\n\n# T\n", True),
            ("Q11", "<!-- _class: top dense -->\n\n# T\n", False),
            ("Q11", "<!-- _class: top -->\n\n# A\n\n---\n\n<!-- _class: dense -->\n\n# B\n", False),
            ("Q7", "<ul>\n  <li>one</li>\n\n    <li>two</li>\n</ul>\n", True),
            ("Q7", "<ul>\n  <li>one</li>\n  <li>two</li>\n</ul>\n", False),
            ("Q7", "Text\n\n    plain indented code\n", False),
            ("Q8", "**↓ 80%**\n", True),
            ("Q8", "**→ 80%**\n", True),
            ("Q8", "↓ **80%**\n", False),
            ("Q8", "- **價格即機率** → Yes\n", False),
            ("Q8", "**無人異議** → **爭議方勝**\n", False),
            ("Q9", head + "![bg](assets/ok.png)\n", True),
            ("Q9", head + "![bg contain](assets/ok.png)\n", True),
            ("Q9", head + "![bg right:40% contain](assets/ok.png)\n", False),
            ("Q9", "![bg](assets/ok.png)\n", False),
            ("Q9", head + "<!-- _header: '' -->\n\n![bg](assets/ok.png)\n", False),
            ("Q9", head + "# First\n\n---\n\n<!-- _header: '' -->\n\n# Second\n\n---\n\n![bg](assets/ok.png)\n", True),
            ("Q10", "![a](assets/截圖 2026-10-31.png)\n", True),
            ("Q10", "![a](assets/Screen Shot 2026-10-31.png)\n", True),
            ("Q10", "![a](assets/p3_chart.png)\n", False),
        ]
        for rule, source, want in cases:
            got = rule in {r for r, _, _ in run_rules(source, tmp)}
            check(f"{rule} {'fires' if want else 'stays quiet'}: {source.strip()[:48]!r}", got == want)

        hit = [f for f in run_rules("# T\n\n<!--\nnote\n-->\n\nTODO\n", tmp) if f[0] == "Q1"]
        check("line numbers survive a multi-line note", hit and hit[0][1] == 7)

        # slide_ranges: a --- inside notes or code is not a new slide
        check("slide_ranges counts rulers", len(slide_ranges("---\nmarp: true\n---\n\n# A\n\n---\n\n# B\n")) == 2)
        check("slide_ranges ignores --- in notes",
              len(slide_ranges("# A\n\n<!--\n---\n-->\n\n---\n\n# B\n")) == 2)
        check("slide_ranges ignores --- in code",
              len(slide_ranges("```\n---\n```\n\n---\n\n# B\n")) == 2)

        check("slide_ranges: --- right after text is a heading",
              len(slide_ranges("# A\nsub\n---\n\n# B\n")) == 1)
        check("slide_ranges: blank line before the frontmatter",
              len(slide_ranges("\n---\nmarp: true\n---\n\n# A\n")) == 1)
        check("slide_ranges: spaced ruler", len(slide_ranges("# A\n\n- - -\n\n# B\n")) == 2)
        check("slide_ranges: indented ruler", len(slide_ranges("# A\n\n  ---\n\n# B\n")) == 2)
        check("slide_ranges: unclosed code fence runs to the end",
              len(slide_ranges("# A\n\n```\ncode\n\n---\n\n# B\n")) == 1)
        bom = os.path.join(tmp, "bom.md")
        with open(bom, "wb") as f:
            f.write(b"\xef\xbb\xbf---\nmarp: true\n---\n\n# A\n")
        check("read_text drops a BOM", len(slide_ranges(read_text(bom))) == 1)

        # slide_map: lets an agent turn "slide 2" into line numbers without counting rulers
        mapped = slide_map("---\nmarp: true\n---\n\n<!-- _class: lead -->\n# First\n\n---\n\nNo heading here\n\n---\n\n<!-- note -->\n")
        check("slide_map lists each slide with its lines and title",
              mapped == [(1, 5, 6, "First"), (2, 10, 10, "No heading here"), (3, 14, 14, "(empty)")])
        check("overflow_fix: a small overrun can use dense", "dense" in overflow_fix(100, "bottom", 720))
        check("overflow_fix: a large overrun needs splitting", "Split" in overflow_fix(300, "bottom", 720))
        check("overflow_fix: too wide is a different fix", "narrower" in overflow_fix(100, "right", 720))

        # count_notes: slides with a real note, directives do not count
        note_cases = [
            ("# A\n", 0),
            ("<!-- _class: lead -->\n# A\n", 0),
            ("<!-- _class: lead\n_paginate: false -->\n# A\n", 0),
            ("<!-- backgroundColor: red -->\n# A\n", 0),
            ("# <!-- fit --> A\n", 0),
            ("# A\n\n<!-- say this -->\n", 1),
            ("<!-- _class: lead -->\n# A\n\n<!-- say this -->\n", 1),
            ("# A\n\n<!-- one -->\n\n<!-- two -->\n\n---\n\n# B\n\n<!-- three -->\n", 2),
        ]
        for source, want in note_cases:
            check(f"count_notes = {want}: {source.strip()[:40]!r}", count_notes(source) == want)

        # pptx_note_count: every slide has a notes part, only real text counts
        pptx = os.path.join(tmp, "notes.pptx")
        fake_pptx(pptx, ["", "say this", ""])
        check("pptx_note_count counts text, not files", pptx_note_count(pptx) == 1)
        fake_pptx(pptx, ["42", ""])
        check("pptx_note_count keeps a note that is only a number", pptx_note_count(pptx) == 1)

        # run_marp: never in the deck's folder, because it can hold a config file or .npmrc
        fake_bin = os.path.join(tmp, "fake bin")
        os.makedirs(fake_bin)
        seen = os.path.join(tmp, "npx args.txt")
        write(os.path.join(fake_bin, "npx"), f'#!/bin/sh\npwd > "{seen}"\nprintf "%s\\n" "$@" >> "{seen}"\n')
        os.chmod(os.path.join(fake_bin, "npx"), 0o755)
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = fake_bin + os.pathsep + saved_path
        rc = run_marp(["deck.md"], 10)
        os.environ["PATH"] = saved_path
        called = read_text(seen).split("\n")
        check("run_marp succeeds with a fake npx", rc == 0)
        check("run_marp runs in an empty folder", os.path.realpath(called[0]) != os.path.realpath(tmp)
              and not os.path.exists(called[0]))
        check("run_marp turns off config files", "--no-config-file" in called)
        check("run_marp pins the package version", any(re.fullmatch(r"@marp-team/marp-cli@\d+\.\d+\.\d+", c) for c in called))

        # pure helpers behind check and sheet
        tag = base_tag("/tmp/my slides")
        check("base_tag encodes spaces and ends with /", tag == '<base href="file:///tmp/my%20slides/">')
        page = inject("<html><head></head><body><p>&lt;/body&gt;</p></body></html>", head="<H>", body="<B>")
        check("inject adds to head and the real end of body",
              "<head><H></head>" in page and page.endswith("<B></body></html>"))
        dom = '<pre id="slides-probe">[{"over":null,"touch":{"px":&quot;3&quot;}}]</pre>'
        check("parse_probe reads escaped JSON", parse_probe(dom) == [{"over": None, "touch": {"px": "3"}}])
        check("parse_probe with no result -> None", parse_probe("<html></html>") is None)
        page = ('<style>a{mask:url("x")} <svg viewBox="0 0 16 16"></style>'
                '<svg data-marpit-svg="" viewBox="0 0 960 720"></svg><svg viewBox="0 0 960 720" data-marpit-svg=""></svg>')
        check("page_shape reads slides, not other svg", page_shape(page) == (2, 960, 720))
        check("page_shape falls back to 16:9", page_shape("<html></html>") == (0, 1280, 720))
        width, height = sheet_size(7, 1280, 720)
        check("sheet_size fits 3 rows at 16:9", width == SHEET_WIDTH and 1080 < height < 1115)
        check("sheet_size is taller at 4:3", sheet_size(7, 960, 720)[1] > height)

        # qa exit codes
        ok_md = os.path.join(tmp, "ok.md")
        write(ok_md, "# Title\n\nPlain text, no images\n")
        check("qa clean deck -> exit 0", cmd_qa(ok_md) == 0)
        warn_md = os.path.join(tmp, "warn.md")
        write(warn_md, '# Title\n\n<div style="color:red">a</div>\n')
        check("qa WARN only -> exit 0", cmd_qa(warn_md) == 0)
        fail_md = os.path.join(tmp, "fail.md")
        write(fail_md, "# Title\n\nTODO: add chart\n")
        check("qa FAIL -> exit 4", cmd_qa(fail_md) == 4)

        # exit 3: missing file or non-.md
        not_md = os.path.join(tmp, "file.txt")
        write(not_md, "x")
        nope = os.path.join(tmp, "nope.md")
        for name, fn in (("map", cmd_map), ("qa", cmd_qa), ("check", cmd_check), ("export", cmd_export),
                         ("verify", cmd_verify), ("sheet", cmd_sheet)):
            check(f"{name} missing file -> exit 3", fn(nope) == 3)
            check(f"{name} non-.md -> exit 3", fn(not_md) == 3)

        # verify: three FAIL modes and one PASS
        v_md = os.path.join(tmp, "verify_target.md")
        write(v_md, "# Title\n\n<!-- say this -->\n")
        check("verify PDF missing -> exit 4", cmd_verify(v_md) == 4)

        v_pdf = os.path.join(tmp, "verify_target.pdf")
        with open(v_pdf, "wb"):
            pass
        check("verify PDF size 0 -> exit 4", cmd_verify(v_md) == 4)

        with open(v_pdf, "wb") as f:
            f.write(b"%PDF-1.4 fake")
        now = time.time()
        os.utime(v_pdf, (now - 100, now - 100))
        os.utime(v_md, (now, now))
        check("verify PDF older than md -> exit 4", cmd_verify(v_md) == 4)

        os.utime(v_pdf, (now + 100, now + 100))
        check("verify all pass -> exit 0", cmd_verify(v_md) == 0)

        # verify: a PPTX next to it must be fresh and keep the notes
        v_pptx = os.path.join(tmp, "verify_target.pptx")
        fake_pptx(v_pptx, [""])
        os.utime(v_pptx, (now + 100, now + 100))
        check("verify PPTX lost the notes -> exit 4", cmd_verify(v_md) == 4)
        fake_pptx(v_pptx, ["say this"])
        os.utime(v_pptx, (now - 100, now - 100))
        check("verify PPTX older than md -> exit 4", cmd_verify(v_md) == 4)
        os.utime(v_pptx, (now + 100, now + 100))
        check("verify PPTX fresh with notes -> exit 0", cmd_verify(v_md) == 0)

        # run_chrome: Chrome with a private profile can stay alive after writing its output
        def fake_browser(name, script):
            program = os.path.join(tmp, name)
            write(program, "#!/bin/sh\n" + script)
            os.chmod(program, 0o755)
            return program

        is_page = lambda text: text.rstrip().endswith("</html>")
        started = time.time()
        rc, out = run_chrome(fake_browser("stays", "echo '<html></html>'\nsleep 30\n"), tmp, [], is_page, 10)
        check("run_chrome returns once output is complete, no exit needed",
              rc == 0 and is_page(out) and time.time() - started < 5)
        rc, out = run_chrome(fake_browser("quits", "exit 0\n"), tmp, [], is_page, 10)
        check("run_chrome: exits with no output -> exit 2", rc == 2)
        rc, out = run_chrome(fake_browser("hangs", "sleep 30\n"), tmp, [], is_page, 1)
        check("run_chrome: nothing before the deadline -> exit 2", rc == 2)

        png = os.path.join(tmp, "shot.png")
        check("png_complete: missing file -> False", not png_complete(png))
        with open(png, "wb") as f:
            f.write(b"\x89PNG partial")
        check("png_complete: cut short -> False", not png_complete(png))
        with open(png, "ab") as f:
            f.write(b"IEND\xaeB`\x82")
        check("png_complete: has the end marker -> True", png_complete(png))

        # find_chrome: CHROME_PATH wins when it points at a real program
        fake_chrome = os.path.join(tmp, "fake chrome")
        write(fake_chrome, "#!/bin/sh\n")
        os.chmod(fake_chrome, 0o755)
        saved = os.environ.get("CHROME_PATH")
        os.environ["CHROME_PATH"] = fake_chrome
        check("find_chrome honors CHROME_PATH", find_chrome() == fake_chrome)
        os.environ["CHROME_PATH"] = os.path.join(tmp, "nope")
        check("find_chrome ignores a broken CHROME_PATH", find_chrome() != os.environ["CHROME_PATH"])
        if saved is None:
            del os.environ["CHROME_PATH"]
        else:
            os.environ["CHROME_PATH"] = saved

    # find_npx: the return shape must be consistent, either (None, None) or (path, that path's directory)
    npx_path, npx_dir = find_npx()
    check("find_npx return shape is consistent",
          (npx_path is None and npx_dir is None)
          or (npx_path is not None and npx_dir == os.path.dirname(npx_path)))

    log("[SKIP] check, export and sheet need npx and Chrome: run them on examples/demo/slides.md")

    passed = sum(1 for _, c in results if c)
    total = len(results)
    log(f"selftest result: {passed}/{total} passed")
    return 0 if passed == total else 1


def main():
    parser = argparse.ArgumentParser(prog="slides.py", description="Check, export and preview Marp slides")
    parser.add_argument("--selftest", action="store_true", help="run the built-in self test")
    sub = parser.add_subparsers(dest="command")

    p_map = sub.add_parser("map", help="list each slide with its line numbers and title")
    p_map.add_argument("file")

    p_qa = sub.add_parser("qa", help="static checks, no network or browser needed")
    p_qa.add_argument("file")

    p_check = sub.add_parser("check", help="render every slide and report content that gets cut off")
    p_check.add_argument("file")
    p_check.add_argument("--timeout", type=int, default=CHECK_TIMEOUT)

    p_export = sub.add_parser("export", help="export a PDF with npx marp-cli")
    p_export.add_argument("file")
    p_export.add_argument("--pptx", action="store_true", help="also export a PPTX")
    p_export.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)

    p_verify = sub.add_parser("verify", help="check the exported files")
    p_verify.add_argument("file")

    p_sheet = sub.add_parser("sheet", help="render every slide into one overview PNG")
    p_sheet.add_argument("file")
    p_sheet.add_argument("--out", help="output path, default <file>.sheet.png")
    p_sheet.add_argument("--timeout", type=int, default=CHECK_TIMEOUT)

    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    if args.command == "map":
        sys.exit(cmd_map(args.file))
    elif args.command == "qa":
        sys.exit(cmd_qa(args.file))
    elif args.command == "check":
        sys.exit(cmd_check(args.file, timeout=args.timeout))
    elif args.command == "export":
        sys.exit(cmd_export(args.file, timeout=args.timeout, pptx=args.pptx))
    elif args.command == "verify":
        sys.exit(cmd_verify(args.file))
    elif args.command == "sheet":
        sys.exit(cmd_sheet(args.file, out=args.out, timeout=args.timeout))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
