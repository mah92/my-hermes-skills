#!/usr/bin/env python3
"""Chinese video -> segments.json with REAL audio times.
RUN WITH THE HERMES VENV PYTHON: $HOME/.hermes/hermes-agent/venv/bin/python
(sherpa_onnx 1.13.x must be importable — any other interpreter without it fails).
Tencent VAD (ten-vad.onnx) cuts speech; sherpa-onnx paraformer-zh (int8) decodes.
Model: csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14 (hermes_files shared store).
VAD tuning: use env TENVAD_THRESHOLD / TENVAD_MIN_SILENCE / TENVAD_MIN_SPEECH /
TENVAD_MERGE_GAP (soft-spoken films: threshold=0.35, min_silence=0.40, min_speech=0.30,
merge_gap=0.6 — the 0.5 threshold misses ~36% of quiet speech, verified 2026-08-29 Chinese
job #2; keep min_silence >=0.4 and merge tiny gaps or the start feels «جابهجا»).
Usage: python transcribe_zh.py <video> <outdir> [ten_vad.onnx] [model_dir]"""
import json, os, subprocess, sys, time, wave
import numpy as np
import sherpa_onnx

SRC, WS = sys.argv[1], sys.argv[2]
TENVAD = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/.cache/sherpa/ten-vad.onnx")
MDIR = sys.argv[4] if len(sys.argv) > 4 else os.path.expanduser("~/.hermes/models/sherpa-onnx-paraformer-zh-2023-09-14")
if not os.path.exists(os.path.join(MDIR, "model.int8.onnx")):
    MDIR = os.path.join(os.path.expanduser("~/hermes_files"), "sherpa-onnx-zh-stt/sherpa-onnx-paraformer-zh-2023-09-14")
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
c.ten_vad.threshold = float(os.environ.get("TENVAD_THRESHOLD", 0.5))
c.ten_vad.min_silence_duration = float(os.environ.get("TENVAD_MIN_SILENCE", 0.4))
c.ten_vad.min_speech_duration = float(os.environ.get("TENVAD_MIN_SPEECH", 0.25))
c.ten_vad.max_speech_duration = 20.0
vad = sherpa_onnx.VoiceActivityDetector(c, 60)

win = c.ten_vad.window_size
segs, idx = [], 0
while idx + win <= len(samples):
    vad.accept_waveform(samples[idx:idx+win])
    idx += win
    while not vad.empty():
        seg = vad.front
        st = int(seg.start)                      # start in SAMPLES — /sr once!
        segs.append([st / sr, (st + len(seg.samples)) / sr])
        vad.pop()
vad.flush()
while not vad.empty():
    seg = vad.front
    st = int(seg.start)
    segs.append([st / sr, (st + len(seg.samples)) / sr])
    vad.pop()
segs = [g for g in segs if g[1] - g[0] >= 0.35]
# merge runs separated by tiny gaps (env TENVAD_MERGE_GAP, default 0.6s) — prevents
# mid-sentence splits that make early subtitles feel «جابهجا» (verified 2026-08-29)
MERGE = float(os.environ.get("TENVAD_MERGE_GAP", 0.6))
merged = []
for g in segs:
    if merged and g[0] - merged[-1][1] <= MERGE:
        merged[-1][1] = g[1]
    else:
        merged.append(g[:])
segs = merged
print(f"TenVad segments (after merge {MERGE}s): {len(segs)}", flush=True)

# cap runs at 16s, split at deepest internal silence
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
print(f"decoded runs: {len(runs_text)}", flush=True)

# split into <=12-char (Chinese) cues: 1 char ~ 0.25-0.3s reading; 12 chars ~ 3-4s
final = []
for r in runs_text:
    chars = list(r["text"].replace(" ", ""))
    d = r["end"] - r["start"]
    n = max(1, int(np.ceil(len(chars) / 12.0)))
    per = int(np.ceil(len(chars) / n))
    for j in range(0, len(chars), per):
        part = "".join(chars[j:j+per])
        st = r["start"] + d * (j / len(chars))
        en2 = r["start"] + d * ((j + len(part)) / len(chars))
        if en2 - st >= 0.6:
            final.append({"start": round(st, 2), "end": round(en2, 2), "text": part})

json.dump(final, open(f"{WS}/segments.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(f"{WS}/zh_full.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(r["text"] for r in runs_text))
durs = [x["end"] - x["start"] for x in final]
print(f"DONE: {len(final)} cues, avg {sum(durs)/len(durs):.1f}s, "
      f"coverage {100*sum(durs)/dur:.0f}%, wall {time.time()-t0:.0f}s -> {WS}/segments.json", flush=True)
