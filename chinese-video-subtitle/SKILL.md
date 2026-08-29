---
name: chinese-video-subtitle
description: "Chinese film video -> dual subtitles: Chinese line + Persian line below (burned-in)."
version: 1.0.0
category: productivity
---

# Chinese Video -> Dual Subtitles (中文 + فارسی)

For Chinese-language films/videos: local ASR (sherpa paraformer-zh), then TWO burned-in
subtitle lines per cue — **Chinese on the upper line, Persian below it**. Verified 2026-08-29
on two Chinese videos (18min + 8.8min, 640x360) with hermes-agent. PORTABLE: only hermes_files
(shared model store), $HOME and standard system paths are assumed.

Pipeline: ffmpeg audio → TenVad segmentation → paraformer-zh decode → Chinese cues →
Chinese→Persian translation (LLM) → dual-track ASS → ffmpeg burn → QC → Bale.

## Requirements (all pre-installed on Ali's box)

- **Hermes venv python** for ALL sherpa work: `$HOME/.hermes/hermes-agent/venv/bin/python`
  (sherpa_onnx 1.13.4; conda vits2 has 1.12.11 — don't use it for this pipeline).
- **ten-vad.onnx** (Tencent VAD): `hermes_files/sherpa-vad/ten-vad.onnx` (or
  `~/.cache/sherpa/ten-vad.onnx`; containers must pass the hermes_files path).
- **paraformer-zh**: `hermes_files/sherpa-onnx-zh-stt/sherpa-onnx-paraformer-zh-2023-09-14/`
  (`model.int8.onnx` ~206MB + `tokens.txt`) from
  `https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14` — direct HF download
  works. Mirror symlink: `~/.hermes/models/sherpa-onnx-paraformer-zh-2023-09-14` → hermes_files.
- **Fonts**: Chinese = `Noto Sans CJK SC` (fonts-noto-cjk, `/usr/share/fonts/opentype/noto/`,
  family name "Noto Sans CJK SC"); Persian = `Nazli`
  (`/usr/share/fonts/truetype/farsiweb/nazli.ttf`, needs `fontsdir=` — see pitfalls).
  Containers: copy both into `hermes_files/fonts/` (Nazli ttf + the CJK .ttc) and pass
  `fontsdir=/home/oem/hermes_files/fonts`.

## Steps

1. **Transcribe** (Chinese text + VAD timing): `scripts/transcribe_zh.py <video> <ws> [ten_vad] [model_dir]`
   → `segments.json` `[{start,end,text}]` + `zh_full.txt`. Same mechanics as the English
   TenVad pipeline: VAD `.start` is in SAMPLES (convert with `/sr` ONCE); decode LONG runs
   (paraformer hallucinates on 1-3s blips); cap runs 16s (split at deepest silence);
   split into ≤12-CHAR Chinese cues (reading pace ~3-4s; Chinese packs more meaning per char
   than English words).
2. **Translate zh→fa**: `scripts/translate_zh_fa.py <ws>` → `fa_cues.json {idx: fa}`.
   Chunk=**40 lines + max_tokens=16384** (60-line chunks → empty responses), TAB separator,
   save-after-chunk resume, retries + raw-test-diagnosis if empties persist. `write_file`
   refuses `N|text` lines → use TAB.
   **PROMPT = dub-style**: a plain "translate this" prompt produced garbled Persian on the
   emotional monologue («خب، حجم آهای، اصلاً عبور کن!») — the verified system prompt demands
   natural FLUID spoken Persian like real dubbing, handles interjections (哎/啊/嗯) naturally
   or drops them, and FORBIDS pinyin/transliteration (first pass emitted pinyin junk). Second
   pass with the dub prompt was clean ("انگار با یه مسئلهای مواجه شدم که نمیشه ازش گذشت").
3. **Dual ASS/SRT**: `scripts/make_dual_ass.py <ws> [width height]` → `zh.srt`, `fa.srt`,
   `dual.ass`. TWO Dialogue events per cue (same times): style **ZH** (`Noto Sans CJK SC`,
   MarginV ≈ H*0.15 → upper line) and style **FA** (`Nazli`, MarginV ≈ H*0.062 → lower line).
   Zero overlap (`end_i = min(end_i, next_start)`, min 0.8s). ASS times MUST be `H:MM:SS.CC`
   (2-digit centis — 3-digit fraction makes libass 0.15 reject the WHOLE track silently).
4. **Burn** (cd to file dir; relative paths — colons in absolute paths break the filter):
   ```bash
   ffmpeg -y -i in.mp4 -vf "ass=dual.ass:fontsdir=/usr/share/fonts/truetype/farsiweb" \
     -c:v libx264 -crf 21 -preset veryfast -c:a copy -movflags +faststart out.mp4
   ```
   `fontsdir` ADDS to fontconfig (Chinese via system Noto still resolves). Size: 18min/360p
   with two text lines = ~48MB at CRF 24 (CRF 21 gave 59MB — over Bale's 50MB; use CRF 24 for
   ≥15min videos, CRF 21-23 for short ones). Containers: `fontsdir=/home/oem/hermes_files/fonts`.
5. **QC**: extract frames at cue midpoints (`ffmpeg -ss T -i out.mp4 -frames:v 1`); pixel-check
   TWO bands — Chinese upper band (~y H*0.55..H*0.8) AND Persian lower band (~y H*0.78..H*0.94);
   both must show text pixels. Vision: avalai `qwen3-vl-32b-instruct` with base64 data-URL
   (reads Chinese natively; `vision_analyze(local)` fails on this box; DeepSeek avalai models
   are text-only) — confirm BOTH lines legible, letters joined for Persian, no tofu.
6. **Deliver**: Bale `sendDocument` mp4 + `zh.srt` + `fa.srt` (tapi.bale.ai, token from
   `~/.hermes/.env`, chat from BALE_CHAT_ID). ≤50MB fits.

## Pitfalls

- **No CJK font = empty Chinese subtitles**: check `fc-list :lang=zh` first; libass renders
  NOTHING (not tofu) when the face is missing — pixel-check both bands.
- **Nazli needs `fontsdir`** on this box (Amiri renders nothing; DejaVu renders unjoined) —
  always pass `fontsdir=/usr/share/fonts/truetype/farsiweb` (host) or
  `/home/oem/hermes_files/fonts` (containers).
- **ASS centis**: `H:MM:SS.CC` two digits — a 3-digit fraction silently kills the whole track.
- **The two SRTs share cue numbering** so `zh.srt`/`fa.srt` can be merged by a player; the
  burned dual.ass is the deliverable for chat apps.
- **Long videos**: translation dominates wall-time (533 cues ≈ 8-12 min with 40-line chunks);
  run chunks in the background, keep progress JSON.
- **VPS/remote**: model mirror via hermes_files keeps containers + remote consistent; scp skill
  files + model dir once per host (GitHub unreachable from the VPS — bundle/scp).

## Scripts
| Script | Purpose |
|---|---|
| `transcribe_zh.py` | TenVad + paraformer-zh → segments.json (Chinese, real audio times) |
| `translate_zh_fa.py` | Chinese→Persian chunked LLM translation → fa_cues.json |
| `make_dual_ass.py` | zh.srt + fa.srt + dual.ass (ZH upper / FA lower, zero overlap) |
