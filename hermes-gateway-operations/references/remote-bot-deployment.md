# Remote Bot Deployment & Multi-Bot Setup

Patterns and commands used for deploying Hermes bots on remote servers with
Bale platform (2026-08-01).

## Remote Server Bot Setup

```bash
# 1. Copy Bale plugin files
scp -r ~/.hermes/plugins/platforms/bale/ <USER>@<REMOTE_HOST>:~/.hermes/plugins/platforms/bale/

# 2. Set environment variables on the remote
ssh <USER>@<REMOTE_HOST> 'cat >> ~/.hermes/.env << EOF
BALE_BOT_TOKEN=<BOT_ID>:...
BALE_HOME_CHANNEL=<GROUP_ID>
BALE_ALLOW_ALL_USERS=false
BALE_ALLOWED_USERS=<USER_ID>
BALE_ALLOWED_CHATS=<OTHER_CHAT_ID>,<GROUP_ID>,<USER_ID>
EOF'

# 3. Install and start the gateway
ssh <USER>@<REMOTE_HOST> '~/.hermes/.../hermes gateway install && \
  ~/.hermes/.../hermes gateway restart'

# 4. Single-shot test (no Bale polling needed)
ssh <USER>@<REMOTE_HOST> '~/.hermes/hermes-agent/venv/bin/python \
  ~/.hermes/hermes-agent/hermes -z "سلام! خودت رو معرفی کن."'
```

## Token Rotation

When changing Bale bot tokens on a remote server:

```bash
ssh <USER>@<REMOTE_HOST> "sed -i 's/^BALE_BOT_TOKEN=.*/BALE_BOT_TOKEN=NEW_TOKEN/' ~/.hermes/.env"
ssh <USER>@<REMOTE_HOST> '~/.hermes/.../hermes gateway restart'
```

## Remote STT + Denoiser Integration

When deploying voice-capable Bale bots on remote servers:
- STT: Shenava-Koochik int8 model (126MB), from HuggingFace
- Denoiser: Hush CPP, compiled against matching ONNX Runtime version
- ffmpeg: static binary in ~/local/bin/ (no sudo needed)
- See `persian-stt` skill for full pipeline

### ffmpeg Static (No Sudo Required)

When `sudo apt-get install ffmpeg` isn't possible:

```bash
mkdir -p ~/local/bin
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar xf ffmpeg-release-amd64-static.tar.xz
cp ffmpeg-*-amd64-static/ffmpeg ~/local/bin/
chmod +x ~/local/bin/ffmpeg
```

stt.py automatically adds `~/local/bin` to PATH at startup.

## ONNX Runtime Version Matching (Critical Pitfall)

When building hush_cpp on a different machine, the ONNX Runtime version must match.
Compiling against 1.24.1 and running against 1.27.0 causes:
- Version symbol mismatch (`VERS_1.24.1 not found`)
- Or segfault if the library is cross-copied but CPU-incompatible

**DO NOT SCP .so files across machines** — CPU instruction differences (e.g. AVX-512
on Xeon Gold vs desktop CPU) cause silent segfaults.

**Fix — download matching release and rebuild on target:**

```bash
# 1. Install cmake via pip (no sudo needed):
~/miniconda3/bin/pip install cmake

# 2. Download matching ONNX Runtime (match the pip package version):
# For sherpa-onnx 1.13.4, use ONNX Runtime 1.27.0
wget https://github.com/microsoft/onnxruntime/releases/download/v1.27.0/onnxruntime-linux-x64-1.27.0.tgz
tar xzf onnxruntime-linux-x64-1.27.0.tgz
mkdir -p ~/local/include/onnxruntime ~/local/lib
cp -r onnxruntime-linux-x64-*/include/* ~/local/include/onnxruntime/
cp onnxruntime-linux-x64-*/lib/libonnxruntime.so* ~/local/lib/
ln -sf ~/local/lib/libonnxruntime.so.1.27.0 ~/local/lib/libonnxruntime.so.1

# 3. Sync hush_cpp source and rebuild:
rsync -avz --exclude='build/' --exclude='.git/' ~/STT/hush_cpp/ <USER>@<REMOTE_HOST>:~/STT/hush_cpp/
ssh <USER>@<REMOTE_HOST> 'cd ~/STT/hush_cpp && rm -rf build && mkdir build && cd build && \
  ~/miniconda3/bin/cmake .. \
    -DONNX_RUNTIME_LIB=$HOME/local/lib/libonnxruntime.so \
    -DONNX_RUNTIME_INCLUDE=$HOME/local/include/onnxruntime && \
  make -j$(nproc)'
```

**Verification:** `ldd ~/STT/hush_cpp/build/hush_enhance_onnx | grep onnx` should
show `~/local/lib/libonnxruntime.so.1`.

## Remote pip Not Installed in Hermes venv

The gateway venv may lack pip. Fix:

```bash
~/.hermes/hermes-agent/venv/bin/python -m ensurepip
ln -sf pip3 ~/.hermes/hermes-agent/venv/bin/pip
```

## Slow Internet — Prefer wget on Remote Over SCP

When the remote has slow connectivity, download files directly on the remote
instead of SCP-ing from local:

```bash
# GOOD: download on remote directly
ssh <USER>@<REMOTE_HOST> 'wget https://huggingface.co/<GITHUB_USER>/.../model.int8.onnx -O ~/STT/models/...'

# BAD: SCP 126MB over slow link (times out)
scp /local/path/model.onnx <USER>@<REMOTE_HOST>:~/STT/models/
```