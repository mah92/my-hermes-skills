#!/usr/bin/env python3
"""Transcribe English audio/video to text locally (sherpa-onnx paraformer-en).

Usage:
    python3 transcribe_en.py <input.mp4|wav|ogg|m4a...> [out.txt]

Auto-extracts 16k mono WAV when the input isn't a WAV (needs ffmpeg).
Model auto-downloads from HuggingFace if missing (csukuangfj org).
Output: text file with ~90-word paragraphs + full text on stdout.
"""
import os, re, subprocess, sys, tempfile, time, wave
import numpy as np
import sherpa_onnx

MDIR = os.path.expanduser("~/.hermes/models/sherpa-onnx-paraformer-en-2023-09-16")
MODEL_URL = "https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-en-2024-03-09/resolve/main/"
MODEL, TOKENS = os.path.join(MDIR, "model.int8.onnx"), os.path.join(MDIR, "tokens.txt")

def ensure_model():
    if os.path.exists(MODEL) and os.path.getsize(MODEL) > 1_000_000 and os.path.exists(TOKENS):
        return
    os.makedirs(MDIR, exist_ok=True)
    print("Model missing — downloading paraformer-en (229 MB)...", file=sys.stderr)
    for f in ("model.int8.onnx", "tokens.txt"):
        subprocess.run(["curl", "-sL", "--retry", "5", "-o", os.path.join(MDIR, f), MODEL_URL + f],
                       check=True)

def to_wav_16k_mono(path):
    if path.lower().endswith(".wav"):
        with wave.open(path, "rb") as w:
            if w.getframerate() == 16000 and w.getnchannels() == 1:
                return path
    tmp = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp],
                   check=True)
    return tmp

if len(sys.argv) < 2:
    sys.exit(__doc__)
src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + "_transcript.txt"

ensure_model()
rec = sherpa_onnx.OfflineRecognizer.from_paraformer(
    paraformer=MODEL, tokens=TOKENS, num_threads=4, sample_rate=16000)

wav = to_wav_16k_mono(src)
with wave.open(wav, "rb") as w:
    n = w.getnframes()
    data = np.frombuffer(w.readframes(n), dtype=np.int16)
samples = data.astype(np.float32) / 32768.0
if wav != src:
    os.unlink(wav)

t0 = time.time(); nsec = len(samples) / 16000
print(f"audio: {nsec:.0f}s, decoding...", file=sys.stderr)

chunk_len = int(60 * 16000)
segments = []
for start in range(0, len(samples), chunk_len):
    seg = samples[start:start + chunk_len]
    if len(seg) < int(0.05 * 16000):
        continue
    s = rec.create_stream()
    s.accept_waveform(16000, seg)
    rec.decode_stream(s)
    t = s.result.text.strip()
    if t:
        segments.append(t)
    if start == 0 or int(start / 16000) % 120 == 0:
        print(f"[{int(start/16000)}s/{int(nsec)}s]", file=sys.stderr, flush=True)

full = " ".join(segments)
words = full.split()
paras = [" ".join(words[i:i+90]) for i in range(0, len(words), 90)]
out_text = "\n\n".join(p[0].upper() + p[1:] for p in paras if p) + "\n"
with open(out, "w") as f:
    f.write(out_text)
print(f"WORDS={len(words)} RTF={(time.time()-t0)/nsec:.2f} "
      f"({time.time()-t0:.0f}s wall) -> {out}", file=sys.stderr)
print(out_text)
