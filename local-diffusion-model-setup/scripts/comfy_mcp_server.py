#!/usr/bin/env python3
"""MCP server: generate Sana images via local ComfyUI (127.0.0.1:8188).

Exposes one tool: generate_sana_image(prompt, width, height, ...).
Pipeline: two-pass (sample+save latent -> decode) so any size up to the
8GB-VRAM ceiling (about 2048x2048) works without OOM in the VAE step.
Verified against ComfyUI v0.33.0 + ComfyUI_ExtraModels, 2026-08-22.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

COMFY_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "/home/oem/comfy/ComfyUI/output"
INPUT_DIR = "/home/oem/comfy/ComfyUI/input"
LATENT_SUBDIR = "latents"
CKPT = "Sana_1600M_1024px.pth"
MODEL_CFG = "SanaMS_1600M_P1_D20"
GEMMA_MODEL = "unsloth/gemma-2-2b-it-bnb-4bit"
VAE_NAME = "dc_ae_f32c32_sana_1.0_diffusers.safetensors"
VAE_TYPE = "dcae-f32c32-sana-1.0-diffusers"
DEFAULT_NEGATIVE = "blurry, low quality, distorted, watermark, text"
MAX_PIXELS = 4_200_000  # ~2048x2048; above this the sampler OOMs on 8GB

# Idle auto-stop: ComfyUI is shut down after this much inactivity so it does
# not sit in RAM/VRAM forever (it is auto-started again on the next request).
IDLE_STOP_SECONDS = int(os.environ.get("COMFY_IDLE_STOP", "1800"))  # default 30 min
WATCHDOG_INTERVAL = int(os.environ.get("COMFY_IDLE_CHECK", "60"))
_last_activity = time.time()

mcp = FastMCP("comfy-sana")


def _comfy_up() -> bool:
    try:
        with urllib.request.urlopen(COMFY_URL + "/system_stats", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _start_comfy() -> None:
    """Start the ComfyUI systemd user service (designed to survive reboots).

    Falls back to a detached direct spawn if the user bus is unavailable.
    """
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "comfyui"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        if _comfy_up_wait(30):
            return
    except Exception as e:
        print("systemctl start failed: %s" % e, file=sys.stderr)
    # last-resort direct spawn (detached)
    subprocess.Popen(
        [
            "/home/oem/comfy/ComfyUI/venv/bin/python",
            "/home/oem/comfy/ComfyUI/main.py",
            "--port", "8188", "--listen", "127.0.0.1",
        ],
        cwd="/home/oem/comfy/ComfyUI",
        stdout=open("/tmp/comfyui-standalone.log", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _comfy_up_wait(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _comfy_up():
            return True
        time.sleep(2)
    return False


def _ensure_comfy(timeout: float = 300.0) -> str:
    """Make sure ComfyUI is reachable, starting it if needed."""
    if _comfy_up():
        return ""
    _start_comfy()
    if _comfy_up_wait(timeout):
        return ""
    return ("ComfyUI could not be started automatically (tried systemctl "
            "--user start comfyui, then direct spawn). Check "
            "journalctl --user -u comfyui or /tmp/comfyui-standalone.log")


def _post(payload: dict) -> dict:
    req = urllib.request.Request(
        COMFY_URL + "/prompt",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "prompt_id" not in body:
        raise RuntimeError("ComfyUI rejected prompt: %s" % json.dumps(body)[:500])
    return body


def _wait(prompt_id: str, timeout: float = 1800.0):
    """Poll /history until the prompt finishes. Returns (ok, info)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        try:
            with urllib.request.urlopen(COMFY_URL + "/history/" + prompt_id, timeout=10) as resp:
                hist = json.loads(resp.read().decode("utf-8")).get(prompt_id)
        except Exception:
            continue  # server busy/reloading; keep polling
        if not hist:
            continue
        st = hist.get("status", {})
        if st.get("completed"):
            return True, hist
        if st.get("status_str") == "error":
            msg = "unknown error"
            for m in st.get("messages", []):
                if m[0] == "execution_error":
                    exc = m[1]
                    msg = "%s: %s" % (exc.get("node_type"), exc.get("exception_message", ""))
                    break
            return False, msg
    return False, "timeout after %.0fs" % timeout


def _wf_sampling(prompt, negative, width, height, seed, steps, prefix):
    """Pass A: text-encode + sample + save latent (no VAE)."""
    return {
        "1": {"class_type": "SanaCheckpointLoader", "inputs": {
            "ckpt_name": CKPT, "model": MODEL_CFG, "dtype": "auto",
            "enable_cfg_passthrough": True}},
        "2": {"class_type": "GemmaLoader", "inputs": {
            "model_name": GEMMA_MODEL, "device": "cuda", "dtype": "default"}},
        "3": {"class_type": "SanaTextEncode", "inputs": {"text": prompt, "GEMMA": ["2", 0]}},
        "4": {"class_type": "SanaTextEncode", "inputs": {"text": negative, "GEMMA": ["2", 0]}},
        "5": {"class_type": "EmptySanaLatentImage", "inputs": {
            "width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
            "latent_image": ["5", 0], "seed": seed, "steps": steps, "cfg": 4,
            "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "10": {"class_type": "SaveLatent", "inputs": {
            "samples": ["6", 0], "filename_prefix": "%s/%s" % (LATENT_SUBDIR, prefix)}},
    }


def _wf_decode(latent_name, prefix):
    """Pass B: load latent + tiled-safe VAE decode + save image."""
    return {
        "11": {"class_type": "LoadLatent", "inputs": {"latent": latent_name}},
        "7": {"class_type": "ExtraVAELoader", "inputs": {
            "vae_name": VAE_NAME, "vae_type": VAE_TYPE, "dtype": "FP16"}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["7", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {
            "images": ["8", 0], "filename_prefix": prefix}},
    }


@mcp.tool()
def generate_sana_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str = DEFAULT_NEGATIVE,
    seed: int = -1,
    steps: int = 20,
) -> str:
    """Generate an image with the local Sana 1.6B model (RTX 3080 8GB).

    Args:
        prompt: English text description of the image to generate.
        width: output width in pixels. Floored to a multiple of 32. Max ~2048.
        height: output height in pixels. Floored to a multiple of 32.
        negative_prompt: what to avoid (good default provided).
        seed: RNG seed; -1 for a random seed.
        steps: diffusion steps (default 20, works well at 1024 and below).
    Returns:
        Path of the generated PNG and its real pixel size.
    """
    width = max(32, int(width) // 32 * 32)
    height = max(32, int(height) // 32 * 32)
    if width * height > MAX_PIXELS:
        return "error: %dx%d = %d pixels exceeds the 8GB-VRAM ceiling (~%d). Use <=2048 per side." % (
            width, height, width * height, MAX_PIXELS)
    if seed == -1:
        seed = int(time.time() * 1000) % (2**31)
    stamp = "sana_mcp_%d_%d" % (int(time.time()), seed % 100000)
    latent_prefix = "%s/%s" % (LATENT_SUBDIR, stamp)

    # Auto-start ComfyUI if it is not running (survives reboots).
    start_err = _ensure_comfy()
    if start_err:
        return "error: " + start_err
    global _last_activity
    _last_activity = time.time()

    try:
        # Pass A: sample
        pid = _post({"prompt": _wf_sampling(prompt, negative_prompt, width, height, seed, steps, stamp),
                     "client_id": "mcp-comfy-sana"})["prompt_id"]
        ok, info = _wait(pid)
        if not ok:
            return "sampling failed: %s (prompt_id=%s)" % (info, pid)
        latent_rel = os.path.join(LATENT_SUBDIR, stamp + "_00001_.latent")
        latent_src = os.path.join(OUTPUT_DIR, latent_rel)
        if not os.path.exists(latent_src):
            return "error: sampling finished but latent not found: %s" % latent_src
        latent_name = os.path.basename(latent_src)
        shutil.copy(latent_src, os.path.join(INPUT_DIR, latent_name))

        # Pass B: decode
        pid2 = _post({"prompt": _wf_decode(latent_name, "SanaMCP"),
                      "client_id": "mcp-comfy-sana"})["prompt_id"]
        ok2, info2 = _wait(pid2)
        if not ok2:
            return "decoding failed: %s (prompt_id=%s)" % (info2, pid2)
    except urllib.error.URLError as e:
        return "error: cannot reach ComfyUI at %s (%s). Is the ComfyUI server running?" % (COMFY_URL, e)
    except Exception as e:
        return "error: %s" % e

    out_files = sorted(
        f for f in os.listdir(OUTPUT_DIR)
        if f.startswith("SanaMCP_") and f.endswith(".png")
    )
    if not out_files:
        return "error: decode finished but no PNG found in %s" % OUTPUT_DIR
    latest = os.path.join(OUTPUT_DIR, out_files[-1])
    _last_activity = time.time()
    return "generated %s (seed=%d, steps=%d)" % (latest, seed, steps)


def _stop_comfy() -> bool:
    """Stop ComfyUI. Prefers the systemd user unit; falls back to a direct
    SIGTERM of the ComfyUI process when the user bus is absent (headless
    boot)."""
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
    try:
        r = subprocess.run(
            ["systemctl", "--user", "stop", "comfyui"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return True
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["pgrep", "-f", "comfy/ComfyUI/main.py"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        for pid in out.split():
            try:
                os.kill(int(pid), 15)  # SIGTERM
            except (ProcessLookupError, ValueError):
                pass
        return True
    except Exception as e:
        print("stop fallback failed: %s" % e, file=sys.stderr)
    return False


def _idle_watchdog():
    """Stop ComfyUI after IDLE_STOP_SECONDS without any generate call."""
    global _last_activity
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        if time.time() - _last_activity < IDLE_STOP_SECONDS:
            continue
        if not _comfy_up():
            continue
        if _stop_comfy():
            print("idle watchdog: comfyui stopped after %.0fs idle" %
                  (time.time() - _last_activity), file=sys.stderr)
        _last_activity = time.time()  # back off; don't hammer stop every interval


threading.Thread(target=_idle_watchdog, daemon=True).start()


if __name__ == "__main__":
    mcp.run()
