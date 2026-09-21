---
name: hermes-persian-tts
description: "Persian TTS via MatchaTTS C++ daemon — general-purpose, not Bale-specific. Loads models once (2.5s), then ~200ms per request."
version: 1.1.0
author: علی محمودی
license: MIT
metadata:
  hermes:
    tags: [tts, persian, matcha, vocos, daemon, zahra]
    related_skills: [hermes-bale-messenger]
---

# MatchaTTS Daemon — Fast Persian TTS

Adds Persian text-to-speech to Hermes using the MatchaTTS C++ inference engine
running as a background daemon. Models load once (2.5s), then every request
is ~200ms — 12x faster than loading from scratch each time.

## Quick Setup

### 1. Install the skill

```bash
npx skills add mah92/hermes-persian-skills --skill hermes-persian-tts
```

### 2. Download models

```bash
python3 ~/.hermes/skills/hermes-persian-tts/scripts/download_models.py
```

This downloads:
- Matcha-TTS ONNX model (~72 MB) — Zahra voice, 22050 Hz
- Vocos universal vocoder (k2-fsa vocos-22khz-univ, ~51 MB)
- Token map file

### 3. Build the C++ binary

#### 3a. Clone the repo

```bash
git clone --recurse-submodules https://github.com/mah92/matcha_tts_infer.git
```

This clones `matcha_tts_infer` + the `NormalizeText` submodule (ezafe, hazm, shakkelha, homograph, espeak-ng).

#### 3b. Install build tools and libraries

```bash
sudo apt-get install -y cmake build-essential libespeak-ng-dev libicu-dev
```

#### 3c. Install ONNX Runtime

```bash
ldconfig -p | grep libonnxruntime
# If not found:
wget https://github.com/microsoft/onnxruntime/releases/download/v1.20.0/onnxruntime-linux-x64-1.20.0.tgz
tar xzf onnxruntime-linux-x64-1.20.0.tgz
sudo cp -r onnxruntime-linux-x64-1.20.0/lib/* /usr/local/lib/
sudo cp -r onnxruntime-linux-x64-1.20.0/include/* /usr/local/include/
sudo ldconfig
```

#### 3d. Build

```bash
cd matcha_tts_infer && mkdir -p build && cd build
cmake .. && make -j$(nproc)
```

#### 3e. Verify

```bash
ls -la build/MatchaTTSInfer   # ~250 KB binary
```

### 4. Configure environment

`tts.py` reads the binary and espeak-ng data locations from environment
variables (no hardcoded machine-specific paths):

```bash
export MATCHA_TTS_BIN=/path/to/matcha_tts_infer/build/MatchaTTSInfer
export ESPEAK_DATA=/path/to/espeak-ng-data    # optional
```

`tts.py` auto-starts the daemon on first use, so there is no separate
daemon-management step. The daemon is started from the `NormalizeText/`
directory automatically (so `./assets/` resolves correctly).

### 5. Configure Hermes

Add to `~/.hermes/config.yaml`:

```yaml
tts:
  provider: matcha
  providers:
    matcha:
      type: command
      command: python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.5 {input_path} {output_path}
      output_format: ogg
      timeout: 60
      voice_compatible: true
```

Then restart the gateway.

## How It Works

```
Hermes → tts.py → Unix socket /tmp/tts_infer.sock → MatchaTTSInfer daemon → WAV → ffmpeg → OGG
```

The daemon listens on `/tmp/tts_infer.sock` (Unix domain socket). The `tts.py`
wrapper connects, sends JSON with text + params, receives WAV path, converts
to OGG OPUS, and passes it back to Hermes.

The daemon loads all models once at startup:
- Token map (158 tokens)
- Matcha-TTS ONNX (~72 MB)
- Vocos vocoder ONNX (~51 MB, k2-fsa vocos-22khz-univ with ISTFT reconstruction)
- NormalizeText pipeline (ezafe, homograph, shakkelha, hazm, espeak-ng)

Subsequent requests skip all loading — just normalize + synthesize.

## Performance

| Metric | Value |
|--------|-------|
| Daemon startup | ~2.5s (one-time) |
| First request | ~2.2s (includes first-time normalizeText init) |
| Subsequent requests | ~200ms |
| MatchaTTS inference | ~35ms |
| Vocos inference | ~10ms |
| NormalizeText (cached) | ~140ms |

## Files

| File | Purpose |
|------|---------|
| `scripts/tts.py` | TTS command provider — talks to daemon, converts to OGG |
| `scripts/download_models.py` | Download models from HuggingFace |
| `$MATCHA_TTS_BIN` | C++ binary (built separately) |
| `/tmp/tts_infer.sock` | Daemon socket (created at startup, cleaned on stop) |

## Common Pitfalls

1. **`MATCHA_TTS_BIN` not set.** tts.py needs the path to the MatchaTTSInfer binary. Set it in `~/.hermes/.env` or the shell environment.
2. **Failed to load SentencePiece model.** The daemon must run from the `NormalizeText/` directory so `./assets/` resolves. tts.py handles this automatically via `cwd`, but a manually-started daemon must `cd` there first.
3. **Daemon dies after first request.** SIGPIPE when client disconnects mid-request. The daemon ignores SIGPIPE — rebuild if using an older version.
4. **Stale socket after crash.** If daemon crashes, `/tmp/tts_infer.sock` remains. Delete it before restarting: `rm -f /tmp/tts_infer.sock`.
5. **Vocos model incompatible.** Use the k2-fsa `vocos-22khz-univ.onnx` (mels → mag/x/y). The binary reconstructs the waveform via ISTFT.
6. **Empty text passed to tts.py.** Hermes writes text to `{input_path}`. The script reads it with UTF-8 encoding.
7. **OPUS 48kHz metadata.** OGG output may show 48000 Hz in ffprobe — normal OPUS internal rate.
8. **Long text is auto-split by tts.py (since v1.1.0).** Text longer than ~2000 chars is now split at natural pauses (`. ! ? : ; ، « » ( )` and newlines) inside `tts.py`, synthesized chunk by chunk, and the WAVs are concatenated into a single OGG. Without this, text longer than ~3500 chars makes the daemon spin forever and balloon memory (observed: ~18 GB RSS → host OOM-kill). Do NOT bypass the splitter.
