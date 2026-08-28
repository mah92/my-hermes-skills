---
name: persian-documents
description: "Persian/Farsi docs: DOCX (python-docx), PPTX, PDF (WeasyPrint/pymupdf), Excel, burned-in subtitles."
version: 3.0.0
category: productivity
---

# Persian Document Creation

Create Persian (Farsi) documents and media across formats with proper RTL, fonts, and layout.
Union of lessons from Ali's boxes (local 22.04 + VPS) — every recipe below was VERIFIED on a
real job and survived user feedback rounds.

## FONTS

- FarsiWeb fonts at `/usr/share/fonts/truetype/farsiweb/`: `nazli.ttf` (body), `titr.ttf` (titles),
  `homa.ttf`, `nazlib.ttf`.
- Preferred modern faces (install once): Vazirmatn → `~/.fonts/vazir/Vazirmatn-Regular.ttf` from
  GitHub raw (`rastikerdar/vazirmatn`); family name is **Vazirmatn** (libass/WeasyPrint use
  family, NOT filename).
- For DOCX/PPTX the font is only STORED as a name (`B Nazanin`, `B Titr`, `Calibri`) — no local
  install needed; the user's Word/PowerPoint renders it.
- Fallback for anything: Tahoma. Vazirmatn/vazir = cleanest for PDFs + subtitles.

## Word (DOCX) — python-docx with explicit OOXML (VERIFIED)

`npm docx` garbles Persian — do NOT use it. `python-docx` works IF you set the OOXML RTL
attributes explicitly (paragraph `w:bidi` alone is NOT enough — that was the old local-skill
claim that python-docx "corrupts"; the run-level recipe below is the verified fix):

```python
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm

doc = Document()
sec = doc.sections[0]                    # A4 portrait
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = sec.bottom_margin = Cm(2.2)

def rtl_paragraph(doc, text, font="B Nazanin", size=13, align_right=True):
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
`srgbClr` fills, e.g. navy 0A1F33 / card 143A63 / gold C9A227 / text EDF4FB).
Editing an EXISTING deck = deterministic FULL REBUILD, never incremental insert/move
(add_slide + sldIdLst.remove corrupts the package: duplicated slideN.xml, dropped slides).
Rebuild: deepcopy kept `spTree`, match by TITLE with a ZWNJ-tolerant key
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
5. Raster image labels (Chinese baked into screenshots) are NOT redactable: only add a white caption band + colored text if REAL whitespace exists; otherwise leave image untouched — an untranslated label beats a destroyed image.
6. QC: render pages at dpi=110 and vision-check via `qwen3-vl-32b-instruct` on avalai (base64 data URL) — no tofu/overlap, diagrams intact.
7. Pitfall: this box has few Persian fonts — download Vazirmatn via proxy into `~/.fonts/`; keep short Latin spans (part numbers) untouched.

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

## Video → Persian burned-in (چسبیده) subtitles (VERIFIED 2026-08-28, Moltbook job)

Pipeline: local audio → segment with timestamps → translate per segment → SRT/ASS → ffmpeg burn → vision QC → Bale.

1. **Audio + segmentation (this box, NO downloads needed)**: `ffmpeg -i in.mp4 -ar 16000 -ac 1 out.wav`;
   energy-VAD (30ms RMS, `thr = max(0.02, p25 + 0.25*(p90-p25))`) → JOIN speech runs with gap ≤0.7s
   (cap 16s, split long runs at deepest internal silence) → decode EACH RUN with sherpa-onnx
   paraformer-en (`~/.hermes/hermes-agent/venv/bin/python` has sherpa_onnx; model at
   `~/.hermes/models/sherpa-onnx-paraformer-en-2023-09-16` = mirror of hermes_files store).
   CRITICAL: decode LONG runs, not 1-3s blips — paraformer hallucinates fragmentary text
   ("yeah yeah generalized village") on tiny chunks; 5-20s chunks give grammatical text.
   Then split each run's words into ≤9-word cues with `time = start + dur*(word_idx/len(words))`.
   Result: ~500 cues, ~92% audio coverage, avg 2.2s. scripts: `workspaces/moltbook-subs/transcribe_vad.py`
   (same logic works for any talk video). sherpa paraformer-en emits NO word timestamps
   (`res.words==[]`, `timestamps==None`) — hence the proportional split; VAD gives true audio times
   (better than YouTube auto-caption text, which drifts +2-3.5s — see lessons).
   UNITS PITFALL: VAD loop time is `i*hop/sr` SECONDS — multiplying again by sr slices empty arrays
   and the whole cue list silently collapses to 0 (cost a debug session).
2. **Translate per segment** (LLM, api.avalai.ir + deepseek-v4-flash): chunks of 60 lines,
   prompt "ID<TAB>English" → "ID<TAB>Persian", concise spoken style, ≤~70 chars, keep proper
   nouns (Moltbook, agent, AI), نیمفاصله. write_file REFUSES `N|text` lines (looks like read_file
   output) → use TAB separator. Save progress as JSON {idx: fa} after every chunk (resume-safe).
3. **Zero-overlap SRT/ASS** (Moltbook lesson: overlapping cues = libass stacks them = vertical jitter):
   `end_i = min(end_i, next_start)` with min duration 0.6s. ASS header: PlayResX=640/PlayResY=360,
   Alignment=2, MarginV=24, FontSize=19, Outline=1.5, Shadow=0.6, Bold=1, PrimaryColour=&H00FFFFFF,
   OutlineColour=&H00141414, Encoding=1. **ASS Dialogue timestamps MUST be `H:MM:SS.CC` with
   TWO-digit centiseconds — a 3-digit fraction (`00:00:00.330`) makes libass 0.15 reject the
   ENTIRE track (silent: 0 px rendered, no error) — cost a debug session 2026-08-28.** SRT keeps
   `,mmm` (3-digit ms, fine).
   FONTS: fc-match resolving is NOT enough — on this box libass 0.15 renders **Nazli** only with
   `fontsdir=/usr/share/fonts/truetype/farsiweb` (Amiri renders NOTHING through fontconfig);
   DejaVu/Arial render but with UNJOINED Arabic forms. Nazli + fontsdir + harfbuzz = connected,
   readable Persian. QC check: count bright pixels in the bottom band programmatically
   (`np.frombuffer` gray >= 360x640) — 0 px = track rejected, ~100-300 px = rendering.
4. **Burn** (cd into the file's dir, use relative paths — colon in absolute path breaks the filter):
   ```bash
   ffmpeg -y -i in.mp4 -vf "ass=fa.ass:fontsdir=/usr/share/fonts/truetype/farsiweb" -c:v libx264 -crf 21 -preset veryfast -c:a copy -movflags +faststart out.mp4
   ```
   SRT alternative with styling: `subtitles=fa.srt:force_style='FontName=Amiri,FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00141414,Outline=1.5,Shadow=0.6,MarginV=24,Bold=1,Alignment=2'`
   ASS force_style color format is `&HAABBGGRR` (NOT #RRGGBB); BorderStyle=4 = opaque box.
   Put `scale=` BEFORE `subtitles=` if scaling; `-ss` BEFORE `-i` when trimming. ~30MB for 21 min at 360p, CRF 21.
5. **Vision QC**: `vision_analyze(local path)` FAILS on this box (aux vision model can't see local
   files) → call avalai directly, model `qwen3-vl-32b-instruct`, key `HERMES_CUSTOM_API_AVALAI_IR_API_KEY`
   (NOT DEEPSEEK_API_KEY → 401; DeepSeek avalai models are text-only), image = `data:image/png;base64,...`.
   Extract frames with `ffmpeg -ss T -i out.mp4 -frames:v 1 -q:v 2 f.png`. Confirm letters CONNECTED, no tofu.
   Vision cannot judge sync — verify timing programmatically (cues from VAD are audio-true by construction).
6. **Deliver**: `sendDocument` mp4 (+srt/ass bonus) via `https://tapi.bale.ai/bot<TOKEN>/sendDocument`,
   chat_id = owner DM, token from `~/.hermes/.env` `BALE_BOT_TOKEN`; assert `ok==True`. ≤50MB ok.
   Write the sender to a FILE (an `&` inside a heredoc caption trips the shell guard).

### Lessons learned on the Moltbook job (user feedback: «زیرنویس بین دو جا جابجا میشه» + «خیلی جاها سینک نیست»)
1. **Vertical jitter** = OVERLAPPING cues (YouTube auto-captions have same-start/gap<display groups;
   `end=next_start` without overlap-cleanup stacks them). Fix: merge same-start groups, `end_i=min(end_i, start_{i+1})`, explicit .ass.
2. **Desync** = the caption TEXT timestamps themselves drift vs audio (measured vs official VTT:
   +0.16s@0s → +1.75s@56s → +2.1-3.6s@100s). Any SRT from web caption APIs inherits it. Real fix:
   ASR the actual audio with VAD/word timing (our local sherpa+VAD route) — audio-true by construction.
3. Tool state on this box: sherpa paraformer-en = no word timestamps; faster-whisper NOT installed
   (owner ruled out the heavy 484MB/10-20min run — «نکن. سنگینه»; pre-cache once if ever needed);
   yt-dlp direct YouTube = blocked (Connection reset) → tunnel via VPS socks5 (ssh -D), but
   raw.githubusercontent / jsdelivr / hf.co / release-assets were ALSO unreachable through it — local
   models + installed fonts only.
4. USER PREFERENCE: cost/weight-conscious — do web_search + GitHub checks FIRST, install only the
   lightest working tool, visually confirm BEFORE ≈100MB downloads / ≈10min CPU runs. Propose, don't run heavy.

### Related skills found on the web (2026-08-28)
- `Jaqen00/Skills` → `subtitle-burn` (github.com/Jaqen00/Skills): ffmpeg/libass burn, width-based
  font sizing, height-based margins, normalize-overlap step, `python cli.py burn --video-file ... --subtitle-file ... --output ...`.
- `SkillsMP` `opensquilla/subtitle-burner` (skillsmp.com): SRT→MP4 single-pass burn, audio copy.
- ffmpeg-micro.com "subtitles filter guide" (2026-05): force_style reference, escaping traps
  (colons in paths, quotes in font names, UTF-8), BorderStyle=4 box mode, filter-order rules.

## Long foreign-language text → Persian → RTL docx → Bale (VERIFIED 2026-08-26)
1. Fetch: `web_extract` often blocked for CN/JP → `curl -skL -x socks5h://127.0.0.1:1080 -A 'Mozilla/5.0'`; `-k` REQUIRED behind own proxy (else exit 97).
2. Strip script/style/tags + `html.unescape`; cut title→footer. note.com EN = AI translation of Chinese original — say so honestly.
3. Chunk translate: ~7,300-7,500-char chunks on paragraph boundaries; ONE chunk per turn → `tr2/tr_NN.txt`; MEANING-based natural Persian (not word-for-word — v1 rejected: «ترجمه فارسیات خیلی ضعیفه»), نیمفاصله everywhere.
4. RTL docx via hermes venv python-docx (`/home/oem/.hermes/hermes-agent/venv/bin/python3`): A4, margins 2.2cm, w:bidi paragraphs, CS fonts: fa `B Nazanin`, zh `SimSun`, en `Calibri`. Font names stored only.
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
| Video subtitles | sherpa VAD+paraformer → LLM FA → ffmpeg libass burn |
