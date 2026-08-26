---
name: sherpa-onnx-en-stt
description: "Use when transcribing English audio with sherpa-onnx."
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [stt, asr, english, sherpa-onnx, transcription, paraformer]
    related_skills: [hermes-persian-stt, matcha-tts]
---

# English STT with sherpa-onnx (paraformer-en)

Transcribe English audio/video to text locally with the sherpa-onnx
**offline paraformer-en** model. Model path + proven pattern — works in the
same env as the Persian STT skill (hermes venv/miniconda base, sherpa_onnx
1.12/1.13).

## When to Use
- User wants the transcript/text of an English video, voice note, or audio file
- Local (offline) English ASR without cloud APIs

## Models (already downloaded on this box)
| Model | Path | Size |
|-------|------|------|
| paraformer-en-2024-03-09 (int8) — USE THIS | `~/.hermes/models/sherpa-onnx-paraformer-en-2023-09-16/` (model.int8.onnx, tokens.txt) | 229 MB |
| streaming zipformer-en-2023-06-26 (int8 left-128) — downloaded, ONLINE API BROKEN here | `~/.hermes/models/sherpa-onnx-streaming-zipformer-en-2023-06-26/` | 73 MB |

Download URLs (HF, csukuangfj org):
- https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-en-2024-03-09/resolve/main/model.int8.onnx
- https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-en-2024-03-09/resolve/main/tokens.txt

## Transcription (one command)
```bash
python3 scripts/transcribe_en.py <input.mp4|wav|ogg...> [out.txt]
```
The script auto-extracts 16k mono WAV via ffmpeg (if needed), decodes in 60s
chunks with `OfflineRecognizer.from_paraformer`, and writes a wrapped
paragraph transcript (~90 words/paragraph, no punctuation — ASR output).

Measured: 17.4 min video → 3,307 words in ~4 min wall (int8, 4 threads,
RTF ≈ 0.2-0.3).

## Verify
```bash
wc -w out.txt            # ~190 words per minute of speech
head -c 600 out.txt      # readable? first paragraph sane?
```

## Pitfalls (all learned the hard way 2026-08-26)
- **Streaming (online) zipformer API is BROKEN in the installed sherpa-onnx
  python wheels (1.12.11 AND 1.13.4)**: `OnlineRecognizer.from_transducer`
  loads + decodes fine, but `rec.get_result(stream)` /
  `get_result_all` / `s.get_result` all die with C++ `IndexError: _Map_base::at` —
  the C++ result map never gets the stream. `OnlineStream` has NO `.result`
  attribute in these wheels. Don't burn time on workarounds — use the offline
  model (paraformer) which works via `OfflineStream.result`.
- **zipformer EN models ship `bpe.model` (sentencepiece), and the python
  wrapper chokes on it directly** (`symbol-table.cc:ReadTokens` error with
  binary garbage). Fix: export a plain tokens.txt with sentencepiece first
  (vits2 env has it):
  ```python
  import sentencepiece as spm
  sp = spm.SentencePieceProcessor(); sp.Load("bpe.model")
  open("tokens.txt","w").write("\n".join(sp.IdToPiece(i) for i in range(sp.GetPieceSize())) + "\n")
  ```
  (500-piece vocab for the en zipformer.)
- **Param names in the new wrapper are NOT the old ones**: offline paraformer
  takes `paraformer=<path>` (NOT `model=`); online transducer takes flat
  kwargs (tokens, encoder, decoder, joiner) with NO separate config classes
  (`OnlineRecognizerConfig` etc. removed from the module in 1.12+).
- **Chunked offline decoding**: paraformer has no state between streams, so a
  60s-chunk loop is safe and keeps memory flat. The chunk borders can lose a
  syllable or two — acceptable for transcripts; don't overlap for the sake of
  it unless word-exactness matters.
- **HF repo names**: sherpa-onnx models live under `csukuangfj/` (NOT
  `k2-fsa/`); wrong org → "Invalid username or password." + 29-byte downloads.
- Video already on disk? `ls -la` the file and compare remote `Content-Length`
  before re-downloading (uupload.ir case: sizes matched, no download needed).
