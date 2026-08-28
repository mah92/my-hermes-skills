#!/usr/bin/env python3
"""Video -> Persian burned-in subtitles: local ASR pipeline (no downloads).
VAD(energy) -> join speech runs -> sherpa paraformer-en decode -> proportional
word split -> segments.json [{start,end,text}]. See persian-documents skill.
Usage: python transcribe_vad.py <video> <outdir>"""
import json, os, subprocess, sys, time, wave
import numpy as np
import sherpa_onnx

SRC, WS = sys.argv[1], sys.argv[2]
os.makedirs(WS, exist_ok=True)
WAV = f"{WS}/audio_16k.wav"

subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", SRC,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", WAV], check=True)
with wave.open(WAV, "rb") as w:
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
samples = raw.astype(np.float32) / 32768.0
sr, dur = 16000, len(samples) / 16000
print(f"audio {dur:.0f}s", flush=True)

fr = hp = int(sr * 0.03)
nf = (len(samples) - fr) // hp + 1
rms = np.array([np.sqrt(np.mean(samples[i*hp:i*hp+fr]**2)) for i in range(nf)])
noise, peak = float(np.percentile(rms, 25)), float(np.percentile(rms, 90))
thr = max(0.02, noise + 0.25 * (peak - noise))
active = rms > thr
runs, s = [], None
for i, a in enumerate(active):
    t = i * hp / sr                      # SECONDS — do not multiply by sr again!
    if a and s is None: s = t
    elif not a and s is not None:
        runs.append([s, t]); s = None
if s is not None: runs.append([s, dur])
joined = []
for st, en in runs:
    if joined and st - joined[-1][1] <= 0.7: joined[-1][1] = en
    else: joined.append([st, en])
joined = [r for r in joined if r[1] - r[0] >= 0.5]

# cap runs at 16s, split at deepest internal silence
work = []
for st, en in joined:
    while en - st > 16.0:
        lo, hi = int((st+14)*sr), min(int((st+18)*sr), int(en*sr))
        if hi - lo < sr: break
        sil = int(np.argmin(rms[lo//hp:hi//hp]) * hp / sr) + lo / sr
        work.append([st, st + sil]); st += sil
    work.append([st, en])
work = [w for w in work if w[1] - w[0] >= 0.5]
print(f"runs: {len(joined)} -> decode chunks: {len(work)}", flush=True)

MDIR = os.path.expanduser("~/.hermes/models/sherpa-onnx-paraformer-en-2023-09-16")
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
        en = r["start"] + d * ((j + len(part)) / len(words))
        if en - st >= 0.6:
            final.append({"start": round(st, 2), "end": round(en, 2), "text": " ".join(part)})

json.dump(final, open(f"{WS}/segments.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
durs = [c["end"] - c["start"] for c in final]
print(f"DONE: {len(final)} cues, avg {sum(durs)/len(durs):.1f}s, "
      f"coverage {100*sum(durs)/dur:.0f}%, wall {time.time()-t0:.0f}s -> {WS}/segments.json", flush=True)
