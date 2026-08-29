#!/usr/bin/env python3
"""Video -> English segments with REAL audio times (Tencent VAD + paraformer-en).
RUN WITH THE HERMES VENV PYTHON: $HOME/.hermes/hermes-agent/venv/bin/python
(sherpa_onnx 1.13.x must be importable — any other interpreter without it fails).
TenVad gives speech segments WITH start/end samples (the paraformer model emits
NO word timestamps). Decode each long segment, split into <=9-word cues
proportionally. Usage: python transcribe_tenvad.py <video> <outdir> [ten_vad.onnx]
TenVad model: https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/ten-vad.onnx
(direct download from the k2-fsa sherpa-onnx asr-models release works)."""
import json, os, subprocess, sys, time, wave
import numpy as np
import sherpa_onnx

SRC, WS = sys.argv[1], sys.argv[2]
TENVAD = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/.cache/sherpa/ten-vad.onnx")
os.makedirs(WS, exist_ok=True)
WAV = f"{WS}/audio_16k.wav"

subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", SRC,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", WAV], check=True)
with wave.open(WAV, "rb") as w:
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
samples = raw.astype(np.float32) / 32768.0
sr, dur = 16000, len(samples) / 16000
print(f"audio {dur:.0f}s", flush=True)

c = sherpa_onnx.VadModelConfig()
c.sample_rate = sr
c.ten_vad.model = TENVAD
c.ten_vad.window_size = 768
c.ten_vad.threshold = 0.5
c.ten_vad.min_silence_duration = 0.4
c.ten_vad.min_speech_duration = 0.25
c.ten_vad.max_speech_duration = 20.0
vad = sherpa_onnx.VoiceActivityDetector(c, 60)

win = c.ten_vad.window_size
segs, idx = [], 0
while idx + win <= len(samples):
    vad.accept_waveform(samples[idx:idx+win])
    idx += win
    while not vad.empty():
        seg = vad.front
        st = int(seg.start)                      # start in SAMPLES
        segs.append([st / sr, (st + len(seg.samples)) / sr])
        vad.pop()
vad.flush()
while not vad.empty():
    seg = vad.front
    st = int(seg.start)
    segs.append([st / sr, (st + len(seg.samples)) / sr])
    vad.pop()
segs = [g for g in segs if g[1] - g[0] >= 0.5]
print(f"TenVad segments: {len(segs)}", flush=True)

# cap at 16s, split at deepest internal silence
work = []
for st, en in segs:
    while en - st > 16.0:
        lo, hi = int((st+14)*sr), min(int((st+18)*sr), int(en*sr))
        if hi - lo < sr: break
        fr = int(0.03*sr)
        seg_rms = np.array([np.sqrt(np.mean(samples[i:i+fr]**2))
                            for i in range(lo//fr*fr, hi, fr)])
        sil = 14 + float(np.argmin(seg_rms)) * 0.03 if seg_rms.size else 14.0
        work.append([st, st+sil]); st += sil
    work.append([st, en])
work = [w for w in work if w[1] - w[0] >= 0.5]

MDIR = os.path.expanduser("~/.hermes/models/sherpa-onnx-paraformer-en-2023-09-16")
if not os.path.exists(os.path.join(MDIR, "model.int8.onnx")):
    MDIR = os.path.join(os.path.expanduser("~/hermes_files"), "sherpa-onnx-en-stt", "sherpa-onnx-paraformer-en-2023-09-16")
rec = sherpa_onnx.OfflineRecognizer.from_paraformer(
    paraformer=os.path.join(MDIR, "model.int8.onnx"),
    tokens=os.path.join(MDIR, "tokens.txt"), num_threads=4, sample_rate=16000)

runs_text, t0 = [], time.time()
for i, (st, en) in enumerate(work):
    chunk = samples[int(st*sr):int(en*sr)]
    srec = rec.create_stream(); srec.accept_waveform(sr, chunk)
    rec.decode_stream(srec)
    txt = srec.result.text.strip()
    if txt: runs_text.append({"start": st, "end": en, "text": txt})
    if i % 20 == 0: print(f"  [{i}/{len(work)}] {time.time()-t0:.0f}s", flush=True)

final = []
for r in runs_text:
    words = r["text"].split(); d = r["end"] - r["start"]
    n = max(1, int(np.ceil(len(words) / 9.0)))
    per = int(np.ceil(len(words) / n))
    for j in range(0, len(words), per):
        part = words[j:j+per]
        st = r["start"] + d * (j / len(words))
        en2 = r["start"] + d * ((j + len(part)) / len(words))
        if en2 - st >= 0.6:
            final.append({"start": round(st, 2), "end": round(en2, 2), "text": " ".join(part)})

json.dump(final, open(f"{WS}/segments.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(f"{WS}/en_full.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(r["text"] for r in runs_text))
durs = [x["end"] - x["start"] for x in final]
print(f"DONE: {len(final)} cues, avg {sum(durs)/len(durs):.1f}s, "
      f"coverage {100*sum(durs)/dur:.0f}%, wall {time.time()-t0:.0f}s -> {WS}/segments.json", flush=True)
