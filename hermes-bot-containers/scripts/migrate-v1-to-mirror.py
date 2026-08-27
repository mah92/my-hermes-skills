#!/usr/bin/env python3
"""Migrate containerized bot profiles from the v1 (/opt/data layout) to the
v2 path-mirror layout (/home/oem/.hermes inside the container).
Edit PROFILES below before running."""
import sys, shutil, os

PROFILES = []  # e.g. ["mom-bot", "kids-bot"] - one-time v1->v2 migration
BASE = "/home/oem/.hermes/profiles"

REPLACEMENTS_CFG = [
    # tts provider command (multi-part string spans a line break; replace the prefix)
    ("python3 /opt/data/skills/hermes-persian-tts/scripts/tts.py --speed",
     "python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed"),
    ("/opt/data/venv-ai/bin/python /opt/data/skills/hermes-persian-stt/scripts/stt.py",
     "/home/oem/miniconda3/envs/vits2/bin/python /home/oem/.hermes/skills/hermes-persian-stt/scripts/stt.py"),
    ("db_path: /opt/data/memory_store.db",
     "db_path: /home/oem/.hermes/memory_store.db"),
    ("command: /opt/data/venv-ai/bin/python",
     "command: /home/oem/.hermes/venv-ai/bin/python"),
    ("- /opt/data/mcp/comfy-flux/server.py",
     "- /home/oem/.hermes/mcp/comfy-flux/server.py"),
]

for name in PROFILES:
    prof = f"{BASE}/{name}"
    # ---- config.yaml ----
    cfgp = f"{prof}/config.yaml"
    text = open(cfgp, encoding="utf-8").read()
    for old, new in REPLACEMENTS_CFG:
        n = text.count(old)
        if n == 0:
            print(f"[{name}] WARN: pattern NOT FOUND: {old[:60]}...")
        elif n > 1:
            print(f"[{name}] WARN: pattern found {n}x (expected 1): {old[:60]}...")
        text = text.replace(old, new)
    # terminal cwd (per-profile)
    old_cwd = "cwd: /workspace"
    new_cwd = f"cwd: /home/oem/workspaces/{name}"
    n = text.count(old_cwd)
    text = text.replace(old_cwd, new_cwd)
    print(f"[{name}] terminal.cwd: {n} replacement(s)")
    # verify no /opt/data remains
    left = text.count("/opt/data")
    if left:
        print(f"[{name}] ERROR: {left} leftover '/opt/data' in config.yaml!")
        sys.exit(1)
    open(cfgp, "w", encoding="utf-8").write(text)
    print(f"[{name}] config.yaml written, zero /opt/data refs")

    # ---- .env ----
    envp = f"{prof}/.env"
    env = open(envp, encoding="utf-8").read()
    old_env = "HERMES_LOCAL_STT_COMMAND="
    i = env.find(old_env)
    assert i >= 0, f"[{name}] HERMES_LOCAL_STT_COMMAND missing"
    end = env.find("\n", i)
    new_line = ("HERMES_LOCAL_STT_COMMAND=/home/oem/miniconda3/envs/vits2/bin/python "
                "/home/oem/Basir/STT/stt.py --quiet")
    env = env[:i] + new_line + env[end:]
    open(envp, "w", encoding="utf-8").write(env)
    print(f"[{name}] .env HERMES_LOCAL_STT_COMMAND -> verbatim main value")

    # ---- models symlink at profile root (container ~/.hermes/models) ----
    os.symlink("/home/oem/hermes_files/sherpa-onnx-en-stt", f"{prof}/models")
    print(f"[{name}] profile/models -> hermes_files/sherpa-onnx-en-stt")

    # ---- remove stale .hermes (old bind-mountpoint with empty models/ only) ----
    hermes_dir = f"{prof}/.hermes"
    if os.path.isdir(hermes_dir):
        children = os.listdir(hermes_dir)
        if children == ["models"]:
            md = f"{hermes_dir}/models"
            if os.path.isdir(md) and not os.listdir(md):
                shutil.rmtree(hermes_dir)
                print(f"[{name}] removed stale empty {hermes_dir}")
            else:
                print(f"[{name}] WARN: {hermes_dir}/models not empty, left as-is")
        else:
            print(f"[{name}] WARN: {hermes_dir} has unexpected children {children}, left as-is")

print("DONE")
