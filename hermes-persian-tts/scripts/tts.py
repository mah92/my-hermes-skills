#!/usr/bin/env python3
"""
Persian TTS: MatchaTTS daemon client → OGG OPUS.
Hermes command provider. Reads text from {input_path}, writes OGG to {output_path}.

Uses the MatchaTTSInfer daemon on Unix socket /tmp/tts_infer.sock.
Models loaded once by daemon — requests ~200ms instead of 2.5s.
"""
import sys
import os
import json
import socket
import subprocess
import tempfile
import time
import argparse

SOCKET_PATH = "/tmp/tts_infer.sock"
MAX_RETRIES = 3  # try 3 times total
DEFAULT_SPEED = 1.5

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
MODELS_DIR = os.path.join(SKILL_DIR, "models")

# Paths come from environment — no hardcoded machine-specific locations.
BIN = os.environ.get("MATCHA_TTS_BIN", "")
ESPEAK_DATA = os.environ.get("ESPEAK_DATA", "")

# Model paths — passed explicitly to the binary (no hardcoded defaults in C++).
MATCHA_MODEL = os.path.join(MODELS_DIR, "matcha-fa_en-zahra-22050-5.onnx")
VOCODER_MODEL = os.path.join(MODELS_DIR, "vocos22.onnx")
TOKENS_FILE = os.path.join(MODELS_DIR, "tokens_sherpa_with_fa.txt")


def _start_daemon() -> bool:
    """Start the MatchaTTSInfer daemon with explicit model paths."""
    if not BIN:
        print("Error: MATCHA_TTS_BIN is not set. Point it to the MatchaTTSInfer binary.",
              file=sys.stderr)
        return False
    norm_dir = os.path.join(os.path.dirname(BIN), "..", "NormalizeText")
    cmd = [
        BIN, "--daemon",
        "--matcha-model", MATCHA_MODEL,
        "--vocoder-model", VOCODER_MODEL,
        "--tokens", TOKENS_FILE,
    ]
    if ESPEAK_DATA:
        cmd += ["--espeak-data", ESPEAK_DATA]
    try:
        subprocess.Popen(
            cmd,
            cwd=norm_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception as e:
        print(f"Error: failed to start daemon: {e}", file=sys.stderr)
        return False


def _send_request(text: str, output_wav: str, speed: float = 1.5) -> dict:
    """Send a synthesis request to the daemon. Retries up to MAX_RETRIES times."""
    request = json.dumps({
        "text": text,
        "output": output_wav,
        "speed": speed,
    }, ensure_ascii=False)

    last_error = ""
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            time.sleep(1)
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(300)
            sock.connect(SOCKET_PATH)
            sock.sendall((request + "\n").encode("utf-8"))

            response = b""
            while True:
                ch = sock.recv(1)
                if not ch or ch == b"\n":
                    break
                response += ch
            sock.close()

            if not response:
                last_error = "no response from daemon"
                continue

            result = json.loads(response.decode("utf-8"))
            if result.get("status") == "ok":
                return result
            last_error = result.get("message", "unknown error")
            continue
        except (socket.error, ConnectionRefusedError, OSError) as e:
            last_error = str(e)
            continue

    return {"status": "error", "message": last_error}


def _wav_to_ogg(wav_path: str, ogg_path: str) -> None:
    """Convert WAV to OGG OPUS (mono 16kHz, voip-optimized). Retries on failure."""
    import wave as _wave
    try:
        with _wave.open(wav_path, "rb") as wf:
            wav_seconds = wf.getnframes() / max(wf.getframerate(), 1)
    except Exception:
        wav_seconds = 0
    last_err = None
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            time.sleep(1)
        try:
            # Allow enough time for long audio (30s base + 0.1s per wav second)
            subprocess.run([
                "ffmpeg", "-y", "-i", wav_path,
                "-c:a", "libopus", "-b:a", "32k",
                "-ar", "16000", "-ac", "1",
                "-application", "voip", ogg_path,
            ], capture_output=True, check=True, timeout=max(30, wav_seconds * 0.2 + 30))
            return
        except subprocess.CalledProcessError as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("ffmpeg failed after retries")


def _daemon_dead() -> bool:
    """True if the socket file exists but nothing is listening (stale socket
    left behind when a previous daemon died — e.g. container restart)."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(SOCKET_PATH)
        s.close()
        return False
    except OSError:
        return True


def _split_text(text: str, max_chars: int = 2000) -> list:
    """Split long text into chunks <= max_chars at sentence boundaries.

    The MatchaTTSInfer daemon hangs/explodes in memory on long inputs
    (>~3500 chars), so break at . ! ? : ; ، « » ( ) and newlines first,
    then hard-split any single overly long sentence.
    """
    if len(text) <= max_chars:
        return [text]
    # Sentence-level split points: punctuation that ends a natural pause.
    boundaries = ".!?:؛،;«»()\n"
    pieces, buf = [], ""
    for ch in text:
        buf += ch
        if ch in boundaries:
            pieces.append(buf)
            buf = ""
    if buf.strip():
        pieces.append(buf)

    chunks, cur = [], ""
    for p in pieces:
        # Hard-split any single piece still longer than max_chars.
        while len(p) > max_chars:
            cut = p.rfind(" ", 0, max_chars)
            if cut < max_chars // 2:
                cut = max_chars
            head, p = p[:cut], p[cut:]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(head)
        if cur and len(cur) + len(p) > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur += p
    if cur.strip():
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


def main():
    parser = argparse.ArgumentParser(description="Persian TTS via MatchaTTS daemon")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                        help=f"Speaking speed multiplier (default: {DEFAULT_SPEED})")
    parser.add_argument("input_path", nargs="?", help="Text input file path")
    parser.add_argument("output_path", nargs="?", help="OGG output file path")
    args = parser.parse_args()

    if not args.input_path or not args.output_path:
        parser.print_help()
        sys.exit(1)

    with open(args.input_path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        sys.exit(1)

    # Start daemon if not running (remove stale socket from a dead daemon first)
    if not os.path.exists(SOCKET_PATH) or _daemon_dead():
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        if not _start_daemon():
            sys.exit(1)
        # Wait for daemon to be ready (up to 15s for model loading)
        for _ in range(150):
            if os.path.exists(SOCKET_PATH):
                break
            time.sleep(0.1)
        if not os.path.exists(SOCKET_PATH):
            print("Error: daemon did not start within 15s", file=sys.stderr)
            sys.exit(1)

    # Synthesize via daemon — split long text to avoid daemon hang/OOM
    chunks = _split_text(text)
    if len(chunks) == 1:
        _synthesize(chunks[0], args)
    else:
        # Multiple chunks: concatenate WAVs, convert once → single OGG file.
        # (Hermes delivers one voice message instead of N fragments.)
        import wave
        wavs = []
        try:
            for i, chunk in enumerate(chunks):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    chunk_wav = f.name
                result = _send_request(chunk, chunk_wav, speed=args.speed)
                if result.get("status") != "ok":
                    print(f"Error: chunk {i+1}/{len(chunks)}: "
                          f"{result.get('message', 'unknown')}", file=sys.stderr)
                    sys.exit(1)
                wav_output = result.get("output", "") or chunk_wav
                if not wav_output or not os.path.exists(wav_output) \
                        or os.path.getsize(wav_output) < 100:
                    print(f"Error: chunk {i+1}/{len(chunks)} produced no audio",
                          file=sys.stderr)
                    sys.exit(1)
                wavs.append(wav_output)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                merged_wav = f.name
            with wave.open(merged_wav, "wb") as out:
                for j, w in enumerate(wavs):
                    with wave.open(w, "rb") as src:
                        if j == 0:
                            out.setparams(src.getparams())
                        out.writeframes(src.readframes(src.getnframes()))
            _wav_to_ogg(merged_wav, args.output_path)
        finally:
            for w in wavs:
                try:
                    os.unlink(w)
                except OSError:
                    pass
            try:
                os.unlink(merged_wav)
            except (OSError, NameError):
                pass


def _synthesize(text, args):
    """Single-chunk synthesis path (original behavior)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_wav = f.name
    try:
        result = _send_request(text, tmp_wav, speed=args.speed)
        if result.get("status") != "ok":
            print(f"Error: {result.get('message', 'unknown')}", file=sys.stderr)
            sys.exit(1)

        wav_output = result.get("output", tmp_wav)
        if not os.path.exists(wav_output) or os.path.getsize(wav_output) < 100:
            print("Error: daemon produced no audio", file=sys.stderr)
            sys.exit(1)

        # Convert to OGG
        _wav_to_ogg(wav_output, args.output_path)
    finally:
        try:
            os.unlink(tmp_wav)
        except OSError:
            pass


if __name__ == "__main__":
    main()
