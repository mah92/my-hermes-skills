---
name: chinese-flashcards
description: "Chinese vocab -> printable duplex flashcards PDF (Hanzi+pinyin front, Persian back)."
version: 1.0.0
category: productivity
---

# Chinese Flashcards from a Film (آموزش چینی با فلشکارت)

Turn the vocabulary of a Chinese film/video into PRINTABLE DUPLEX flashcards:
**front = Hanzi (large) + pinyin (tone marks), back = Persian gloss**. Cut guides
(dashed borders), 6 cards per A4 sheet, card index in every corner so the user
can verify front/back alignment after duplex printing. Verified 2026-08-29 on
film 2 (你本来就值得, 411 unique words → 139-page deck).

Pipeline: extract vocab (jieba) → pinyin (pypinyin) + Persian glosses (LLM) →
weasyprint PDF. Run everything with the **hermes venv python**
(`$HOME/.hermes/hermes-agent/venv/bin/python` — jieba, pypinyin, weasyprint
installed there).

## Steps

1. **Text source**: either a script file or the ASR output of a video. For a
   video use the chinese-video-subtitle skill's `segments.json` → `zh_full.txt`
   (or: `python -c "import json;print('\n'.join(x['text'] for x in json.load(open('segments.json'))))" > zh_full.txt`).
2. **Extract vocab**: `python scripts/extract_vocab.py zh_full.txt <ws>` →
   `vocab.json` `[{w, f}]` sorted by frequency. (jieba filters to Han-only
   tokens; punctuation/numbers dropped.)
3. **Gloss**: `python scripts/gloss_vocab.py <ws>` → `vocab_gloss.json`
   `[{w, f, py, fa}]`. API: api.avalai.ir `deepseek-v4-flash`, key env
   `HERMES_CUSTOM_API_AVALAI_IR_API_KEY`. Resume-safe (words with `fa` are
   skipped), chunks of 100, ordered parse fallback (the LLM sometimes numbers
   lines 1..N instead of echoing the word — parser maps by line order when the
   head isn't a word).
4. **Build PDFs**: `python scripts/make_flashcards.py <ws> <outdir>` → BOTH
   duplex variants:
   - `flashcards.pdf` — for printers set to **flip on short edge**
   - `flashcards-longedge.pdf` — for **flip on long edge**
   Back-page grid compensates the driver's rotation/mirroring so card N's back
   lands at card N's physical position; the corner index proves it. If the user
   reports the back number ≠ front number, switch the other variant.

## Duplex alignment (the mirror trap — get this right)

Blanket rule was derived empirically on 2026-08-29 (user asked «حواست که پشت
صفحه آینهای میشه؟»):

- A duplex driver with "flip on **short edge**" lays page 2 down ROTATED 180°.
  ⇒ back page grid = whole-page 180° (`list(reversed(page))`), content NOT
  pre-rotated. After cutting, flipping a card over its horizontal axis shows
  the Persian upright.
- A driver with "flip on **long edge**" lays page 2 down MIRRORED.
  ⇒ back page grid = columns reversed (per row), content NOT pre-rotated.
  User flips the card over the vertical axis to read it.
- Never mix both (grid + content rotation) — they cancel or double.
- Always put a card INDEX on both sides and instruct: «پشت هر کارت باید شماره
  همان کارت باشد؛ اول یک برگه تست بزنید.»

## Pitfalls

- **weasyprint** must run under the hermes venv (system python may lack it);
  it shapes Persian correctly via pango/harfbuzz (no arabic_reshaper needed).
- **Fonts**: Chinese = `Noto Sans CJK SC` (fonts-noto-cjk); Persian = `Nazli`
  (farsiweb). Both resolved via fontconfig; check `fc-list :lang=fa`.
- LLM glosses: first pass (plain prompt) produced garbage for function words —
  the verified system prompt demands short glosses (1-4 Persian words),
  grammatical function for particles (的 → «یِ اضافه/ملکیت»), NO pinyin.
- Hanzi fontsize 40pt fits ≤ 6 chars per card; longer compounds auto-wrap
  (font-size drops are not implemented — keep the vocab at word level, jieba
  rarely emits > 6-char words).
- QC preview: `pdftoppm -png -r 80 -f 2 -l 2 flashcards.pdf p` then vision-check
  front page (Hanzi + pinyin present, no tofu) — the BACK page will look
  upside-down to a vision model even though it is CORRECT for print (that's the
  180° compensation; verify pairing via the index numbers, not by reading text).

## Scripts
| File | Purpose |
|---|---|
| `extract_vocab.py` | jieba segmentation + frequency → vocab.json |
| `gloss_vocab.py` | pinyin (pypinyin) + Persian glosses (avalai) → vocab_gloss.json |
| `make_flashcards.py` | weasyprint → flashcards.pdf + flashcards-longedge.pdf (6/A4, idx, cut guides) |
