---
name: chinese-vocab-sheet
description: "Chinese vocab -> 2-column study sheet PDF (right Hanzi, left Persian + pinyin)."
version: 1.0.0
category: productivity
---

# Chinese Vocabulary Study Sheet (فهرست واژگان دوستونه)

Turn the vocabulary of a Chinese film/video into a printable STUDY SHEET:
one row per character-word with **right column = Hanzi, left column = Persian
gloss, middle = pinyin** (RTL reading order). A4 table, ~20 rows/page
(411 words → 21 pages). Verified 2026-08-29 on film 2 (你本来就值得).

Pipeline: extract vocab (jieba) → pinyin (pypinyin) + Persian glosses (LLM) →
weasyprint table PDF. Run everything with the **hermes venv python**
(`$HOME/.hermes/hermes-agent/venv/bin/python` — jieba, pypinyin, weasyprint).

## Steps

1. **Text source** — a script file, or a video's ASR output via the
   chinese-video-subtitle skill (`segments.json` → `zh_full.txt`).
2. **Extract vocab**: `python scripts/extract_vocab.py zh_full.txt <ws>` →
   `vocab.json` (jieba Han-only tokens, frequency-desc order).
3. **Gloss**: `python scripts/gloss_vocab.py <ws>` → `vocab_gloss.json`
   (pinyin tone-style + Persian glosses via api.avalai.ir `deepseek-v4-flash`,
   key env `HERMES_CUSTOM_API_AVALAI_IR_API_KEY`; resume-safe, ordered-parse
   fallback for numbered responses).
4. **Build sheet**: `python scripts/make_sheet.py <ws> <outdir>` → `vocab-sheet.pdf`.
   Columns: فارسی (right-aligned RTL, Nazli) | چینی (bold Hanzi, Noto Sans CJK
   SC) | پینیین (small, gray) — user asked «ستون راست چینی، ستون چپ فارسی».

## Pitfalls

- Persian column MUST be `direction: rtl; text-align: right` — otherwise Nazli
  text misaligns; weasyprint shapes it correctly (harfbuzz), no pre-shaping.
- Fonts via fontconfig: Noto Sans CJK SC + Nazli (farsiweb).
- LLM gloss prompt: short (1-4 words), grammatical function for particles,
  no pinyin output (pinyin comes from pypinyin locally, keeps column clean).
- Keep the glossed file order (frequency desc) — dedupe with a dict keyed by
  word before writing, or renamed duplicate rows appear (seen in the 1st run).

## Scripts
| File | Purpose |
|---|---|
| `extract_vocab.py` | jieba segmentation + frequency → vocab.json |
| `gloss_vocab.py` | pinyin + Persian glosses (avalai) → vocab_gloss.json |
| `make_sheet.py` | weasyprint table → vocab-sheet.pdf (ش راست چینی، ستون چپ فارسی) |
