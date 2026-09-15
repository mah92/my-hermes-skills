---
name: sherpa-onnx-ar-stt
description: "Use when transcribing Arabic audio with sherpa-onnx (FastConformer non-streaming, or streaming zipformer)."
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [stt, asr, arabic, sherpa-onnx, transcription, fastconformer, zipformer, streaming]
    related_skills: [sherpa-onnx-en-stt, hermes-persian-stt, hermes-persian-tts]
---

# Arabic STT with sherpa-onnx (FastConformer + streaming zipformer)

Transcribe Arabic audio/video to text locally with sherpa-onnx. Two proven
models, both benchmarked on 29-30 Google FLEURS `ar_eg` sentences (whitespace
WER after diacritic stripping, greedy decode, desktop CPU):

| Model | WER | Streaming | Size |
|-------|-----|-----------|------|
| **FastConformer hybrid large pcd (int8)** — accuracy pick | **8.48%** (fp32: 8.29%) | NO | 174 MB |
| **streaming zipformer ar_en_id_ja_ru_th_vi_zh (int8)** — real-time pick | ~14.9%* | YES (~1-2s chunks) | 259 MB |
| moonshine-base-ar — NOT recommended | 14.02%* | NO | 119 MB |

\* moonshine crashed (ONNX broadcast error) on 16/29 samples — real WER is worse.
\* zipformer used the wrong language on 2/29 samples (multilingual confusion).

Published repos (Ali's HF): https://huggingface.co/mah92/sherpa-onnx-nemo-ctc-ar-fastconformer-hybrid-large-pcd-v1.0-non-streaming-2024-12-25 and `...-non-streaming-int8-2024-12-25` (date suffix = model's HF publish date 2024-12-25, NOT convert date).

## When to Use
- User wants the transcript/text of an Arabic video, voice note, or audio file
- Local (offline) Arabic ASR without cloud APIs
- Streaming Arabic ASR (dictation-style) → zipformer variant

## Models

### Non-streaming (accuracy): Arabic FastConformer int8
- HF repo: `mah92/sherpa-onnx-nemo-ctc-ar-fastconformer-hybrid-large-pcd-v1.0-non-streaming-int8-2024-12-25`
- Files: `model.int8.onnx` (174 MB), `tokens.txt` (1025 SentencePiece tokens, `<blk>` = 1024 = LAST id)
- Base model: `nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0` (published 2024-12-25, ~114M params, diacritized output)
- Download:
  ```bash
  mkdir -p ~/.hermes/models/sherpa-onnx-ar-fastconformer-int8 && cd $_
  BASE=https://huggingface.co/mah92/sherpa-onnx-nemo-ctc-ar-fastconformer-hybrid-large-pcd-v1.0-non-streaming-int8-2024-12-25/resolve/main
  wget $BASE/model.int8.onnx $BASE/tokens.txt
  ```

### Streaming (real-time): zipformer multilingual
- Download: https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10.tar.bz2 (259 MB)
- Extract to `~/.hermes/models/`; use the `*.int8.onnx` encoder/joiner + fp32 decoder.
- Chunk 16 frames (160ms), left context 128 — real-time dictation-capable.

## Transcription (one command)
```bash
python3 scripts/transcribe_ar.py <input.mp4|wav|ogg...> [out.txt]
```
Same pattern as the English skill: ffmpeg → 16k mono WAV → sherpa-onnx offline
decode. For streaming (mic / live), use `OnlineRecognizer.from_transducer` with
the zipformer files — chunked `accept_waveform` + `is_ready`/`decode_stream` loop.

## Non-streaming decode via onnxruntime (no sherpa needed)
The FastConformer export is a single graph (`audio_signal` [B,80,T] fp32 +
`length`). Features: 80-bin log-mel fbank (librosa mel, low_freq=0, hann window,
dither=0, remove_dc_offset=False) with per-feature normalization over time
(mean/std per bin, eps 1e-5). Greedy CTC-style collapse on argmax ids, skipping
repeats AND id 1024 (`<blk>`); join with SentencePiece pieces, `▁` → space.
Reference implementation: `test.py` in the HF repo.

## Verify
```bash
wc -w out.txt
head -c 600 out.txt
```

## Pitfalls (learned 2026-09-14)
- **Streaming FastConformer Arabic does NOT exist and community fine-tunes are
  broken**: a fine-tuned `streaming_70_13.nemo` variant's cache-aware encoder
  output diverges from full-context (per-frame cosine sim ~0.17) and produces
  repeated text at ANY chunk size (105/57/201/2320 frames all tested). Verified
  with direct NeMo `forward_for_export` A/B. Don't retry — use the zipformer for
  streaming.
- **sherpa `OnlineRecognizer` NeMo-transducer metadata contract**: `vocab_size`
  meta must be `decoder.vocab_size` WITHOUT +1 (sherpa adds 1 for blank itself);
  `<blk>` must be the LAST tokens.txt line; `chunk_shift` = streaming_cfg
  `shift_size` (NOT chunk_size); `window_size` = chunk_size + pre_encode_cache.
- **sherpa NeMo path dtype**: decoder inputs are int32 (`targets` (B,1),
  `target_length` (B)); encoder `length`/`cache_last_channel_len` are int64.
- **NeMo predict-step output has U+1 columns** (leading blank-context col);
  sherpa wants exactly the LAST column (embedding of the last consumed token) —
  slice `[:, -1, :]` inside the graph, else the joiner broadcasts and returns
  all-blank.
- **Dynamic int8 quantization breaks Conv here**: `ConvInteger` has no ORT CPU
  kernel for this graph (`NOT_IMPLEMENTED: /pre_encode/conv/...`). Exclude
  Conv/ConvTranspose/LSTM from `quantize_dynamic` (see `quantize.py` in the HF
  repo).
- **NeMo `set_export_config` RESETS `streaming_cfg`** (it calls
  `setup_streaming_params()` with defaults). Re-apply custom
  `setup_streaming_params(...)` AFTER `set_export_config`, before `export()`.
- **cuInit error 999** (after suspend/resume) breaks NeMo restore — set
  `CUDA_VISIBLE_DEVICES=-1` in the export process; no reboot needed.
- **HF uploads of >100MB files: use remote server 106, not the local link**
  (local Wi-Fi to HF can drop to ~50KB/s; server 106 uploads at ~2-5MB/s).
  Recipe: rsync with `--partial --append-verify` (network breaks mid-transfer
  are routine), then `python3` + `huggingface_hub.upload_file` on the server
  (HF token already at `~/.cache/huggingface/token` there). Big files resume
  from HF's chunk cache — a "second" upload after a local partial only sends
  the remainder.
- **sherpa model_type auto-detect**: passing the fp32 encoder with int8
  joiner/decoder works; sherpa sniffs NeMo transducer from `model_type`
  metadata — keep the full metadata block from the HF repo's `convert.py`.

## Language-switching (Hermes multi-ASR note)
Each Hermes user profile picks its STT via `~/.hermes/config.yaml`:
```yaml
stt:
  provider: <name>
```
To serve multiple languages on one box, register one command provider per
language under `stt.providers` (ar/en/fa scripts are interchangeable — same
`{input_path}` contract, same `--quiet` requirement) and switch `stt.provider`
in the user's settings; restart the gateway afterwards.
