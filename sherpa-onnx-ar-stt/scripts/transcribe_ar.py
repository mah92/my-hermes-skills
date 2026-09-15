#!/usr/bin/env python3
"""Transcribe Arabic audio/video to text locally (sherpa-onnx / NeMo FastConformer).

Usage:
    python3 transcribe_ar.py <input.mp4|wav|ogg|m4a...> [out.txt]

Auto-extracts 16k mono WAV when the input isn't a WAV (needs ffmpeg).
Model auto-downloads from HuggingFace if missing (mah92 org, int8, 174 MB).
Output: text file with ~90-word paragraphs + full text on stdout.

Arabic-specific: the FastConformer export is decoded via sherpa-onnx
OfflineRecognizer.from_transducer (encoder/decoder/joiner are all the same
bundled graph? No — this repo ships ONE model.onnx graph, so we use the
k2-fsa NeMo-transducer offline path only if split files exist; otherwise we
decode CTC-style with onnxruntime exactly like the HF repo's test.py).
"""
import os, re, subprocess, sys, tempfile, time, wave
import numpy as np
import sherpa_onnx

MDIR = os.path.expanduser("~/.hermes/models/sherpa-onnx-ar-fastconformer-int8")
BASE = ("https://huggingface.co/mah92/sherpa-onnx-nemo-ctc-ar-fastconformer-"
        "hybrid-large-pcd-v1.0-non-streaming-int8-2024-12-25/resolve/main/")
MODEL, TOKENS = os.path.join(MDIR, "model.int8.onnx"), os.path.join(MDIR, "tokens.txt")
BLANK = 1024


def ensure_model():
    if os.path.exists(MODEL) and os.path.getsize(MODEL) > 100_000_000 and os.path.exists(TOKENS):
        return
    os.makedirs(MDIR, exist_ok=True)
    print("Model missing — downloading Arabic FastConformer int8 (174 MB)...", file=sys.stderr)
    for f in ("model.int8.onnx", "tokens.txt"):
        subprocess.run(["curl", "-sL", "--retry", "5", "-C", "-", "-o", os.path.join(MDIR, f), BASE + f],
                       check=True)


def to_wav_16k_mono(path):
    if path.lower().endswith(".wav"):
        try:
            with wave.open(path, "rb") as w:
                if w.getframerate() == 16000 and w.getnchannels() == 1 \
                        and w.getcomptype() == "NONE":
                    return path
        except wave.Error:
            pass  # float32 WAVs etc. — fall through to ffmpeg
    tmp = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp],
                   check=True)
    return tmp


def build_transcriber():
    """ sherpa-onnx OfflineRecognizer for the NeMo transducer export.
    The bundled export keeps all sub-graphs; sherpa accepts it as a
    single-file NeMo transducer (encoder==decoder==joiner==model.onnx is NOT
    valid) — so instead we run CTC-head-style greedy decode via onnxruntime,
    mirroring the HF repo's test.py which is verified against references.
    """
    import onnxruntime as ort
    import torch  # feature normalization helper only

    sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])

    def transcribe(samples_16k):
        import kaldi_native_fbank as knf
        opts = knf.FbankOptions()
        opts.frame_opts.dither = 0
        opts.frame_opts.remove_dc_offset = False
        opts.frame_opts.window_type = "hann"
        opts.mel_opts.low_freq = 0
        opts.mel_opts.num_bins = 80
        opts.mel_opts.is_librosa = True
        fbank = knf.OnlineFbank(opts)
        fbank.accept_waveform(16000, samples_16k)
        frames = []
        i = 0
        while i < fbank.num_frames_ready:
            frames.append(np.array(fbank.get_frame(i)))
            i += 1
        feats = np.stack(frames)
        t = torch.from_numpy(feats)
        feats = ((t - t.mean(0, keepdims=True)) / (t.std(0, keepdims=True) + 1e-5)).numpy()
        x = torch.from_numpy(feats).t().unsqueeze(0).numpy()
        outs = sess.run(None, {"audio_signal": x,
                               "length": np.array([x.shape[-1]], dtype=np.int64)})
        ids = np.argmax(outs[0][0], axis=-1)
        prev = -1
        hyp = []
        for k in ids:
            if k != prev and k != 0 and k != BLANK:
                hyp.append(int(k))
            prev = k
        return "".join(id2tok.get(i, "") for i in hyp).replace("▁", " ").strip()

    return transcribe


def load_tokens():
    id2tok = {}
    with open(TOKENS, encoding="utf-8") as f:
        for line in f:
            tok, idx = line.rsplit(None, 1)
            id2tok[int(idx)] = tok
    return id2tok


if len(sys.argv) < 2:
    sys.exit(__doc__)
src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + "_transcript.txt"

ensure_model()
id2tok = load_tokens()
transcribe = build_transcriber()

wav = to_wav_16k_mono(src)
with wave.open(wav, "rb") as w:
    n = w.getnframes()
    data = np.frombuffer(w.readframes(n), dtype=np.int16)
samples = data.astype(np.float32) / 32768.0
if wav != src:
    os.unlink(wav)

t0 = time.time(); nsec = len(samples) / 16000
print(f"audio: {nsec:.0f}s, decoding...", file=sys.stderr)

# long audio: split at silences-free fixed 30s; the graph is dynamic in T.
chunk_len = int(30 * 16000)
segments = []
for start in range(0, len(samples), chunk_len):
    seg = samples[start:start + chunk_len]
    if len(seg) < int(0.05 * 16000):
        continue
    t = transcribe(seg)
    if t:
        segments.append(t)
    if start == 0 or int(start / 16000) % 120 == 0:
        print(f"[{int(start/16000)}s/{int(nsec)}s]", file=sys.stderr, flush=True)

full = " ".join(segments)
words = full.split()
paras = [" ".join(words[i:i+90]) for i in range(0, len(words), 90)]
out_text = "\n\n".join(p for p in paras if p) + "\n"
with open(out, "w") as f:
    f.write(out_text)
print(f"WORDS={len(words)} RTF={(time.time()-t0)/nsec:.2f} "
      f"({time.time()-t0:.0f}s wall) -> {out}", file=sys.stderr)
print(out_text)
