---
name: persian-video-subtitle
description: "Persian video subtitles (burned-in/SRT) + Farsi docs: DOCX/PPTX/PDF/Excel. RTL, fonts."
version: 3.2.0
category: productivity
---

# Persian Document Creation & Film Subtitles

Create Persian (Farsi) documents and media across formats with proper RTL, fonts, and layout.
Union of lessons from Ali's boxes (local 22.04 + VPS) — every recipe below was VERIFIED on a
real job and survived user feedback rounds. PORTABLE: no dependency on any user's folder
layout — only `hermes_files` (the shared model store) and standard/`$HOME` locations are assumed.

## FONTS

- FarsiWeb fonts at `/usr/share/fonts/truetype/farsiweb/`: `nazli.ttf` (body), `titr.ttf` (titles),
  `homa.ttf`, `nazlib.ttf`.
- Preferred modern faces (install once): Vazirmatn → `~/.fonts/vazir/Vazirmatn-Regular.ttf` from
  GitHub raw (`rastikerdar/vazirmatn`); family name is **Vazirmatn** (libass/WeasyPrint use
  family, NOT filename).
- For DOCX/PPTX the font is only STORED as a name (`B Nazanin`, `B Titr`, `Calibri`) — no local
  install needed; the user's Word/PowerPoint renders it.
- Fallback for anything: Tahoma. Vazirmatn/vazir = cleanest for PDFs + subtitles.
- Discover a usable Persian font with `fc-list :lang=fa` (standard fontconfig path); if the box
  has none, install Vazirmatn once.

## Word (DOCX) — python-docx with explicit OOXML (VERIFIED)

`npm docx` garbles Persian — do NOT use it. `python-docx` works IF you set the OOXML RTL
attributes explicitly (paragraph `w:bidi` alone is NOT enough — that was the old claim that
python-docx "corrupts"; the run-level recipe below is the verified fix):

```python
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt

doc = Document()
sec = doc.sections[0]                    # A4 portrait
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = sec.bottom_margin = Cm(2.2)

def rtl_paragraph(doc, text, font="B Nazanin", size=13):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi"); bidi.set(qn("w:val"), "1"); pPr.append(bidi)  # RTL paragraph
    run = p.add_run(text)
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts")) or OxmlElement("w:rFonts")
    rFonts.set(qn("w:cs"), font)          # CRITICAL: Word uses w:cs for Persian script
    rPr.insert(0, rFonts)
    run.font.size = Pt(size)
    return p
```

### Mixed Persian+English — RUN-LEVEL rtl required (user: «اشکالات چپچین و راستچین»)
Latin segments inside an RTL paragraph (URLs, "ISO/IEC", "Systems Engineer") mirror/reorder in
Word. Fix: split each paragraph into per-language runs and set on EACH run:
- Persian run: `w:rtl=1`, `w:lang=fa-IR`, CS font `B Nazanin`.
- Latin run: `w:rtl=0`, `w:lang=en-US`, font `Calibri` (or the Latin name).
- Pure-Latin lines: paragraph bidi OFF + LEFT align.
Verify structurally after build: every run has cs font + rtl/lang; vision-recheck with
`qwen3-vl-32b-instruct` on avalai (DeepSeek avalai models are text-only — say so honestly).

## PowerPoint (PPTX) — python-pptx font pitfalls (VERIFIED)

DOCX and PPTX set fonts in DIFFERENT XML namespaces. Mixing breaks rendering (tofu □):
- DOCX = WordprocessingML → `w:rFonts` with `w:cs`.
- PPTX = DrawingML → fonts are `a:latin` / `a:ea` / `a:cs` INSIDE `a:rPr`. Injecting `w:rFonts`
  into a pptx run is IGNORED → fallback theme fonts → boxes (e.g. "adoption momentum" as □).

Per every run in every textbox:

```python
from pptx.oxml.ns import qn
rPr = run._r.find(qn("a:rPr"))
for wf in rPr.findall(qn("w:rFonts")):      # drop invalid injections first
    rPr.remove(wf)
for tag, tf in (("latin", "Calibri"), ("ea", "B Nazanin"), ("cs", "B Nazanin")):
    el = rPr.find(qn("a:" + tag))
    if el is None:
        el = rPr.makeelement(qn("a:" + tag), {}); rPr.append(el)
    el.set("typeface", tf)
```

Rules: English runs → `a:latin Calibri`; Persian → `a:cs B Nazanin`; titles (≥18pt) →
`a:cs B Titr`; `run.font.name` sets ONLY `a:latin` — Persian still breaks without `a:cs`.
Persian fonts LACK glyphs for ←→≤≥× — replace with words (تا، حداکثر، حداقل) or boxes appear.
Appending slides to an existing deck: replicate the deck's native theme (read existing shapes'
`srgbClr` fills). Editing an EXISTING deck = deterministic FULL REBUILD, never incremental
insert/move (add_slide + sldIdLst.remove corrupts the package: duplicated slideN.xml, dropped
slides). Rebuild: deepcopy kept `spTree`, match by TITLE with a ZWNJ-tolerant key
(`norm(s)=s.replace('\u200c','').replace(' ','')`), build a fresh Presentation, strip default
children, append shapes; do NOT invent missing content — rebuild from verified evidence.
Verify after EVERY build: slide count, dup titles==0, empty slides==0, no w:rFonts remnants,
every run has a:latin+a:cs, canonical closing slide still LAST (this user checks: «چرا حذف کردی»).
RTL/LTR normalization pass: per paragraph `pPr algn=r` (unless explicit ctr for stats),
`rtl = 1 if has_persian else 0`; per textbox `a:bodyPr rtlCol`; per run lang fa-IR/en-US.
English-only subtitle boxes → rtl=0 + right-aligned, NOT mirrored.

## PDF

### WeasyPrint — BEST for new Persian PDFs
```bash
pip install weasyprint
```
```python
from weasyprint import HTML
html = f"""<html dir="rtl"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 2cm; }}
@font-face {{ font-family: 'Nazli'; src: url('file:///usr/share/fonts/truetype/farsiweb/nazli.ttf'); }}
body {{ font-family: 'Nazli', Tahoma; font-size: 13pt; direction: rtl; line-height: 2; }}
</style></head><body><h1>عنوان</h1><p>متن فارسی</p></body></html>"""
HTML(string=html).write_pdf("output.pdf")
```

### LaTeX + XePersian — academic
```latex
\documentclass[12pt]{article}
\usepackage{xepersian}
\settextfont{Nazli}
\begin{document} ... \end{document}
```
Compile `xelatex -interaction=nonstopmode file.tex` (template: `templates/persian-latex.tex`).

### DO NOT USE for Persian PDF
- **fpdf2** — poor Persian quality. **pymupdf insert_text raw** — does NOT shape Arabic script.

### PDF in-place translation (keep the ORIGINAL layout — user rule 2026-08-24: «فرمت و تصاویر و قالببندی باید مثل نسخه اصلی باشه»)
1. Extract spans + bboxes: `page.get_text("dict")` → blocks→lines→spans; build span→translation dict.
2. Redact only TEXT: `page.add_redact_annot(Rect(bbox), fill=(1,1,1))` + `apply_redactions()` — images/vectors SURVIVE.
3. Shape Persian BEFORE inserting: `get_display(arabic_reshaper.reshape(txt))` (pip arabic-reshaper + python-bidi); embed a Persian TTF via `pymupdf.Font(fontfile=VAZIR)` + `fontname="F0", fontfile=...` ("F0" placeholder name required for embedded TTFs).
4. **Uniform font sizes — never per-line shrink** (user: «ریز و درشت شدن فونتها»). Body 10.6 / heading 12 / title 18; `insert_textbox(rect, disp, fontsize=size, align=2)` wraps; shrink only 0.5 steps as last resort.
5. Raster image labels (foreign text baked into screenshots) are NOT redactable: only add a white caption band + colored text if REAL whitespace exists; otherwise leave image untouched — an untranslated label beats a destroyed image.
6. QC: render pages at dpi=110 and vision-check via `qwen3-vl-32b-instruct` on avalai (base64 data URL) — no tofu/overlap, diagrams intact.
7. Keep short Latin spans (part numbers) untouched.

## Excel (XLSX) — openpyxl rightToLeft
```python
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
wb = Workbook(); ws = wb.active
ws.sheet_view.rightToLeft = True            # KEY: RTL sheet
ws['A1'] = 'عنوان'
ws['A1'].font = Font(name='Tahoma', size=14, bold=True)
ws['A1'].alignment = Alignment(horizontal='right')
wb.save('output.xlsx')
```

## Film video → Persian burned-in (چسبیده) subtitles (VERIFIED 2026-08-28, Moltbook job v1+v2)

Pipeline: local audio → TenVad segmentation with timestamps → translate per segment → SRT/ASS → ffmpeg burn → vision QC → Bale.

1. **Audio + segmentation (sherpa Tencent VAD — VERIFIED)**: `ffmpeg -i in.mp4 -ar 16000 -ac 1 out.wav`;
   then **TenVad** via `sherpa_onnx.VoiceActivityDetector` (model `ten-vad.onnx` ~332KB from the
   k2-fsa sherpa-onnx asr-models release, direct GitHub download works; keep a local copy under
   `~/.cache/sherpa/`). Config: window_size=768, threshold=0.5, min_silence=0.4, min_speech=0.25,
   max_speech=20; feed 768-sample windows, drain `vad.front` (segment `.start` is in SAMPLES;
   end = start + len(.samples)). TenVad gives speech boundaries with TRUE audio times
   (~97% coverage; energy-VAD fallback ~92%). Cap runs at 16s (split at deepest internal silence),
   decode EACH RUN with sherpa-onnx paraformer-en from `hermes_files` (`~/.hermes/models/` mirror);
   CRITICAL: decode LONG runs — on 1-3s blips paraformer hallucinates fragmentary text.
   Split each run's words into ≤9-word cues with `time = start + dur*(word_idx/len(words))`.
   WHY VAD AT ALL: paraformer-en emits NO word timestamps (res.words==[], timestamps==None) —
   segment timing MUST come from the VAD. script: `scripts/transcribe_tenvad.py`.
   CONTAINERS (hermes-bot-containers): keep a model copy in the shared store at
   `hermes_files/sherpa-vad/ten-vad.onnx` (ro-mounted in every bot container) and pass its path
   as argv[3] — the `~/.cache` default is not visible inside containers. FONTS in containers:
   `/usr/share/fonts/truetype/farsiweb` is host-only — copy `nazli.ttf` (and `titr.ttf`) to
   `hermes_files/fonts/` and burn with `fontsdir=/home/oem/hermes_files/fonts`.
   Verified 2026-08-28 in
   hermes-marziye: full pipeline + skills list (image venv `/opt/hermes/.venv/bin/hermes skills
   list`) shows the skill enabled. NOTE: the mounted HOST hermes-agent venv's `hermes` CLI fails
   to import hermes_cli inside containers (system-site-packages dependency) — use the image's
   own `/opt/hermes/.venv/bin/hermes` for CLI checks.
   UNITS PITFALL: segment `.start` and the window index are SAMPLES — convert with /sr exactly
   once (multiplying twice silently collapses the cue list to 0).
2. **Translate per segment** (LLM, api.avalai.ir + deepseek-v4-flash): chunks of **40 lines
   with `max_tokens=16384`** (60-line chunks got TRUNCATED/EMPTY responses on deepseek-v4-flash —
   verified twice: 2026-08-28 on the host AND in the marziye container E2E; 40/16384 → 100%;
   a system hint «فقط خطوط ID<TAB>متن را برگردان، بدون توضیح» helps),
   prompt "ID<TAB>English" → "ID<TAB>Persian", concise spoken style, ≤~70 chars, keep proper
   nouns (Moltbook, agent, AI), نیمفاصله. write_file REFUSES `N|text` lines (looks like read_file
   output) → use TAB separator. Save progress as JSON {idx: fa} after every chunk (resume-safe);
   backfill misses in a second pass; DIAGNOSE empty responses with ONE raw API test call before
   changing parameters (30s, saves retry loops).
3. **Zero-overlap SRT/ASS** (lesson: overlapping cues = libass stacks them = vertical jitter):
   `end_i = min(end_i, next_start)` with min duration 0.6s. ASS header: PlayResX=video width,
   PlayResY=video height, Alignment=2, MarginV=24, FontSize≈19@360p, Outline=1.5, Shadow=0.6,
   Bold=1, PrimaryColour=&H00FFFFFF, OutlineColour=&H00141414, Encoding=1.
   **ASS Dialogue timestamps MUST be `H:MM:SS.CC` with TWO-digit centiseconds — a 3-digit
   fraction (`00:00:00.330`) makes libass 0.15 reject the ENTIRE track (silent: 0 px rendered,
   no error!).** SRT keeps `,mmm` (3-digit ms, fine). script: `scripts/make_ass.py`.
   FONTS: fc-match resolving is NOT enough — on this box libass 0.15 renders **Nazli** only with
   `fontsdir=` pointing at the font's directory (Amiri renders NOTHING through fontconfig);
   DejaVu/Arial render but with UNJOINED Arabic forms. Pick a font with `fc-list :lang=fa` and
   pass `fontsdir=<its dir>`; Nazli + harfbuzz = connected, readable Persian.
   QC check: count bright pixels in the bottom band programmatically (gray frame → 0 px = track
   rejected, ~100-300 px = rendering).
4. **Burn** (cd into the file's dir, use relative paths — colon in absolute path breaks the filter):
   ```bash
   ffmpeg -y -i in.mp4 -vf "ass=fa.ass:fontsdir=/usr/share/fonts/truetype/farsiweb" -c:v libx264 -crf 21 -preset veryfast -c:a copy -movflags +faststart out.mp4
   ```
   SRT alternative with styling: `subtitles=fa.srt:force_style='FontName=...,FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00141414,Outline=1.5,Shadow=0.6,MarginV=24,Bold=1,Alignment=2'`
   ASS force_style color format is `&HAABBGGRR` (NOT #RRGGBB); BorderStyle=4 = opaque box.
   Put `scale=` BEFORE `subtitles=` if scaling; `-ss` BEFORE `-i` when trimming. ~30MB for 21 min at 360p, CRF 21.
5. **Vision QC**: `vision_analyze(local path)` FAILS on Ali's box (aux vision model can't see local
   files) → call avalai directly, model `qwen3-vl-32b-instruct`, key `HERMES_CUSTOM_API_AVALAI_IR_API_KEY`
   (NOT DEEPSEEK_API_KEY → 401; DeepSeek avalai models are text-only), image = `data:image/png;base64,...`.
   Extract frames with `ffmpeg -ss T -i out.mp4 -frames:v 1 -q:v 2 f.png`. Confirm letters CONNECTED, no tofu.
   Vision cannot judge sync — verify timing programmatically (cues from TenVad are audio-true by construction).
6. **Deliver**: `sendDocument` mp4 (+srt/ass bonus) via `https://tapi.bale.ai/bot<TOKEN>/sendDocument`,
   chat_id = owner DM, token from `~/.hermes/.env` `BALE_BOT_TOKEN`; assert `ok==True`. ≤50MB ok.
   Write the sender to a FILE (an `&` inside a heredoc caption trips the shell guard).

### Lessons learned on the Moltbook job (user feedback: «زیرنویس بین دو جا جابجا میشه» + «خیلی جاها سینک نیست»)
1. **Vertical jitter** = OVERLAPPING cues (YouTube auto-captions have same-start/gap<display groups;
   `end=next_start` without overlap-cleanup stacks them). Fix: merge same-start groups, `end_i=min(end_i, start_{i+1})`, explicit .ass.
2. **Desync** = the caption TEXT timestamps themselves drift vs audio (measured vs official VTT:
   +0.16s@0s → +1.75s@56s → +2.1-3.6s@100s). Any SRT from web caption APIs inherits it. Real fix:
   ASR the actual audio with VAD timing (local sherpa+TenVad route) — audio-true by construction.
3. Tool state on the box: sherpa paraformer-en = no word timestamps; heavier ASR (faster-whisper)
   may be ruled out by the owner as too heavy (484MB download / 10-20min CPU) — prefer the local
   sherpa stack; propose heavy installs before running.
4. USER PREFERENCE: cost/weight-conscious — do web_search + GitHub checks FIRST, install only the
   lightest working tool, visually confirm BEFORE ≈100MB downloads / ≈10min CPU runs.
5. **marziye container E2E (2026-08-28, her own 17-min session) — problems SHE hit & solved,
   now encoded here**: (a) translation: 60-line chunks → truncated/empty API responses; fix =
   CHUNK=40 + max_tokens=16384 (100% success) — she diagnosed with ONE raw API test call first;
   (b) STALE artifacts from earlier runs in the workspace (old segments.json / fa_cues.json /
   fa.srt / fa.ass) get misread as state — run each job in a FRESH output dir or delete the four
   files before starting; (c) QC negative control: frame from a known cue-GAP must show only
   noise-level pixels — proves the pixel test isn't a false positive; and the vision model READ
   the subtitle at t=480s and it matched the cue translation for that instant (validates sync).
   The whole pipeline ran fully inside the container: no YouTube, no web captions, no downloads.

### Related skills found on the web (2026-08-28)
- `Jaqen00/Skills` → `subtitle-burn` (github.com/Jaqen00/Skills): ffmpeg/libass burn, width-based
  font sizing, height-based margins, normalize-overlap step.
- `SkillsMP` `opensquilla/subtitle-burner` (skillsmp.com): SRT→MP4 single-pass burn, audio copy.
- ffmpeg-micro.com "subtitles filter guide" (2026-05): force_style reference, escaping traps
  (colons in paths, quotes in font names, UTF-8), BorderStyle=4 box mode, filter-order rules.

## Long foreign-language text → Persian → RTL docx → Bale (VERIFIED 2026-08-26)
1. Fetch: `web_extract` often blocked for CN/JP → `curl -skL -A 'Mozilla/5.0'` (add proxy if the
   host needs one); `-k` REQUIRED behind an own proxy (else exit 97).
2. Strip script/style/tags + `html.unescape`; cut title→footer. note.com EN = AI translation of Chinese original — say so honestly.
3. Chunk translate: ~7,300-7,500-char chunks on paragraph boundaries; ONE chunk per turn; MEANING-based
   natural Persian (not word-for-word — v1 rejected: «ترجمه فارسیات خیلی ضعیفه»), نیمفاصله everywhere.
4. RTL docx via python-docx (use the agent's own venv python — e.g. `$HOME/.hermes/hermes-agent/venv/bin/python3`):
   A4, margins 2.2cm, w:bidi paragraphs, CS fonts: fa `B Nazanin`, zh `SimSun`, en `Calibri`. Font names stored only.
5. Deliver each file via Bale sendDocument; expect a rewrite round — keep v1 files until v2 accepted.

## Iranian Academic Paper Structure
1. Title page 2. چکیده + واژگان کلیدی 3. مقدمه 4. مبانی نظری و پیشینه تحقیق 5. روش تحقیق 6. یافتههای تحقیق 7. نتیجهگیری و پیشنهادها 8. منابع و مآخذ (فارسی + لاتین)

## Summary
| Format | Best Tool |
|--------|-----------|
| PDF (new) | WeasyPrint 🥇 (fpdf2/pymupdf-raw: NO) |
| PDF (translate in place) | pymupdf redact + arabic_reshaper + Vazirmatn |
| Word | python-docx + w:bidi/w:cs/run-level rtl (npm docx: NO) |
| PowerPoint | python-pptx + a:latin/a:ea/a:cs per run; full-rebuild edits |
| Excel | openpyxl + rightToLeft |
| Academic PDF | LaTeX + XePersian |
| Film subtitles | sherpa TenVad+paraformer → LLM FA → ffmpeg libass burn |
