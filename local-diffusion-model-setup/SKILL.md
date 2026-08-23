---
name: local-diffusion-model-setup
description: Use when deploying image/video-gen models (Sana, FLUX).
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [comfyui, sana, flux, diffusion, image-generation, video, deployment]
    related_skills: [comfyui, throttled-network-downloads]
---

# Local diffusion model setup (ComfyUI + models)

Deploying text-to-image / video-gen models on Ali's Ubuntu box (RTX 3080
Mobile 8GB VRAM, 30GB RAM, CUDA 12.4 driver 550). Facts verified from
primary sources (HF model cards, NVlabs/BFL GitHub+blogs, ComfyUI docs),
Aug 2026. The general `comfyui` skill covers ComfyUI lifecycle/workflows;
this one covers MODEL SELECTION and the Sana-specific install recipe.

## When to Use
- User asks "can I run model X on my system?" → answer with the verified VRAM
  numbers + this hardware's verdict, not guesses.
- User asks to install a gen model (Sana, FLUX, SDXL...) on this box.

## Hardware verdicts (this box: 8GB laptop GPU, Max-Q)
- Sana 0.6B/1.6B: YES — designed for laptops; Sana 1.6 + Gemma-2B-4bit +
  DC-AE fits ~6GB. Fast.
- FLUX.2 klein 4B: marginal — official figures 8.4–9.2GB VRAM (Comfy docs,
  measured on RTX 5090), ~8GB (BFL README), ~13GB (HF card, bf16 pipeline);
  text encoder is Qwen3-4B (extra 4B!). On 8GB: only GGUF Q4 + heavy offload,
  slow. RTX 3090/4070+ is BFL's own requirement.
- FLUX.2 klein ControlNet claim: NOT in any BFL primary source. Community
  ControlNets exist for klein-9B (ReyChiaro/flux.2-klein-controlnet) only;
  SDXL-ControlNet-ecosystem claims belong to OTHER models. Say so honestly.
- Video streaming models (SANA-Streaming V2V 2B, LongSANA 720p-1min): built
  for RTX 5090-class; not viable on 8GB. Don't promise them locally.
- klein 4B license Apache-2.0; Sana code Apache-2.0; Sana 9B / FLUX.2 dev are
  non-commercial licenses.

## GGUF vs original weights (decision framework)
- GGUF matters ONLY when the model's own weights can't fit VRAM (FLUX-class
  12B/32B). For Sana the big win is the TEXT ENCODER: Sana uses Gemma-2B →
  load unsloth/gemma-2-2b-it-bnb-4bit (bitsandbytes 4-bit, ~2GB, not gated).
  Sana fp16 (~3.2GB) + DCAE fp16 + Gemma-4bit ≈ 6GB → fits, no GGUF needed.
- No official Sana GGUF exists (only low-download unofficial conversions);
  ComfyUI-GGUF's official pre-quants are FLUX/SD3.5. Recommend original.
- General quant guidance: Q8 ≈ visually lossless, Q4 small drop; use GGUF
  when weights alone exceed VRAM or for RAM-constrained loads.

## Sana 1.6 1600M — verified install recipe (ComfyUI)
- DiT: Efficient-Large-Model/Sana_1600M_1024px → checkpoints/Sana_1600M_1024px.pth
  → models/checkpoints/. BOTH it and the `_BF16` repo are 6.4GB — suspicious
  but true; don't assume BF16 is half size.
- VAE: mit-han-lab/dc-ae-f32c32-sana-1.0-diffusers →
  diffusion_pytorch_model.safetensors → models/vae/.
- Text encoder: GemmaLoader node auto-snapshots
  unsloth/gemma-2-2b-it-bnb-4bit into models/text_encoders/models--unsloth--
  gemma-2-2b-it-bnb-4bit. NOTE: `from_pretrained` actually reads the DEFAULT
  HF cache (~/.cache/huggingface/hub/models--unsloth--gemma-2-2b-it-bnb-4bit),
  so pre-download THAT; the local_dir is only a presence check.
- Custom node: git clone lawrence-cj/ComfyUI_ExtraModels → custom_nodes/
  (Sana support; NVlabs/Sana README links it). bitsandbytes must be pip
  installed for the 4-bit Gemma.
- Nodes: SanaCheckpointLoader(ckpt_name, model="SanaMS_1600M_P1_D20", dtype,
  enable_cfg_passthrough), GemmaLoader(model_name, device="cuda", dtype),
  SanaTextEncode(text, GEMMA), SanaResolutionSelect(model, ratio),
  EmptySanaLatentImage, ExtraVAELoader(vae_name, vae_type=
  "dcae-f32c32-sana-1.0-diffusers", dtype), KSampler (euler/normal, 20 steps,
  cfg ~4; Sana is a FLOW model).
- Sample workflow SanaV1.json (ExtraModels repo assets) is EDITOR format —
  build API format yourself after the server returns /object_info for exact
  input names (ready API-format template: templates/sana_1600m_txt2img_api.json)
- First generate at 512px as a smoke test, then 1024px.

## ComfyUI install notes for this box
- `uv tool install comfy-cli` (no pipx), `comfy --skip-prompt tracking disable`.
- `comfy install --nvidia` runs pip from miniconda base = Python 3.13 (NOT
  system 3.10!) — match wheel tags to whatever venv python it lands in.
- On the throttled link, the stock install stalls 30+ min on torch:
  pre-fetch wheels with aria2 (see throttled-network-downloads) and
  `pip install --no-index --find-links`. torchaudio cu124 cp313 wheel is
  flaky on download.pytorch.org — skip it (PyPI cpu wheel is fine).
- Verify: `curl -s http://127.0.0.1:8188/system_stats` after `comfy launch
  --background`.

## Runtime fixes — ComfyUI v0.33.0 + torch 2.6.0+cu124 (verified 2026-08-22)
All fixes below were required to get the FIRST Sana image out. Driver
550.163 caps CUDA at 12.4; torch 2.7/2.8 have NO cu124 wheels (cu126 needs
driver >=560) — so torch stays 2.6 and the packages must be made to fit.
1. comfy-kitchen==0.2.31 (pinned by requirements.txt) crashes at import on
   torch 2.6: `custom_op` infer_schema rejects lowercase `list[int]` in
   backends/eager/na.py (`_op_na3d`). PATCH site-packages: import List from
   typing, change kernel_size/is_causal annotations to List[int]/List[bool].
2. comfy-kitchen 0.2.31 PyPI LACKS the int8_attention API (only on git main
   via sage_attention.py) yet ComfyUI master calls
   comfy_kitchen.int8_attention_is_available() at startup → AttributeError.
   PATCH: append a shim to comfy_kitchen/__init__.py defining
   int8_attention_is_available=()->False + stubs raising NotImplementedError
   for int8_attention/prequantize_int8_attention/int8_attention_from_prequantized.
   SAFE: ComfyUI gates all int8 usage on the flag (attention.py:876/887).
3. torchaudio must MATCH torch (==2.6.0+cu124 from download.pytorch.org/whl/cu124).
   A mismatched 2.11.0 was present → `OSError: libcudart.so.13 not found` at
   `import torchaudio` (audio_vae.py) — plain crash at server startup.
4. ExtraModels needs diffusers + accelerate>=1.1.0 + timm (its requirements.txt:
   timm, sentencepiece, transformers, accelerate, einops, protobuf — install
   the whole file). CRITICAL: after installing deps, RESTART the server —
   transformers caches package availability; a running server kept raising
   "bitsandbytes 4-bit requires accelerate" until restart.
5. ExtraModels EmptySanaLatentImage (Sana/nodes.py:162) uses `self.device`
   which ComfyUI v0.33's EmptyLatentImage no longer sets (it calls
   comfy.model_management.intermediate_device() inline) → AttributeError
   'no attribute device'. PATCH custom node line to
   device=comfy.model_management.intermediate_device() (add `import
   comfy.model_management`). Not fixed upstream yet (checked 2026-08-22).
6. New /prompt API wants an ENVELOPE: {"prompt": {workflow}, "client_id": ...}
   — posting the raw workflow dict returns 400 no_prompt.
7. SanaCheckpointLoader dtype: use "auto" ("default" is not in the option
   list). GemmaLoader dtype "default" IS valid; device "cuda".
8. First-run pipeline order (each smoke-tested): SanaCheckpointLoader loads
   ~3GB, GemmaLoader pulls unsloth/gemma-2-2b-it-bnb-4bit from the DEFAULT HF
   cache (~/.cache/huggingface), ExtraVAELoader needs diffusers, KSampler 20
   steps euler/normal cfg 4. 512px took <30s sampling once loaded.
9. RESOLUTION CEILING on 8GB (verified): sampling 1024px fine (~1 step/s at
   2K too!); 2048x2048 sampling FITS (SanaMS linear attention, ~1s/it);
   4096x4096 sampling OOMs in KSampler — the DiT does NOT fit, tiling is NOT
   available for the sampler (ExtraModels has no tiled-sampling node). 4K on
   this GPU: not possible in one shot; needs --lowvram gamble or bigger GPU.
9b. QUALITY vs resolution (user-verified 2026-08-23): the Sana_1600M_1024px
   checkpoint is TRAINED for ~1024px. Sampling >~1280px with it (e.g. 2048)
   looks broken/useless ("به درد نمیخوره") — out-of-distribution. Usable 2K/
   4K needs the dedicated checkpoints Sana_1600M_2Kpx_BF16 / 4Kpx_BF16
   (6.4GB each, separate downloads). Sizes INSIDE the 1024 training range
   (square, portrait, landscape, e.g. 800x600, 1280x768) are fine.
9c. Arbitrary sizes: request any width/height — output is floored to a
   multiple of 32 by EmptySanaLatentImage (latent = W/32, ×32 upscale). E.g.
   800x600 → actual 800x576. To hit an exact height, use the next multiple of
   32 (576 or 608). The MCP tool repeats this flooring; ~576-1920px works.
10. VAE decode OOM at >=2048: ExtraModels `decode_tiled_` exists but (a) the
    OOM fallback in `decode()` only catches model_management.OOM_EXCEPTION —
    torch 2.6 raises plain torch.OutOfMemoryError which does NOT match → the
    fallback never fires (patch: catch Exception, re-raise unless
    isinstance OOM_EXCEPTION/torch.cuda.OutOfMemoryError); (b) upstream tile
    defaults 64 latent (=2048px tiles, ×32 upscale) OOM on 8GB — patch to
    tile_x=32, tile_y=32, overlap=4 (=<=1024px tiles) with orientations
    (16,32)/(32,16)/(32,32). After ANY site-packages/custom-node patch,
    RESTART the server (Python classes are loaded at startup).
11. 2-pass pattern for big images: Pass A = sample + SaveLatent (prefix
    latents/x) WITHOUT the VAE; Pass B = LoadLatent + VAE decode + SaveImage
    in a fresh prompt so Sana/Gemma aren't resident during decode. SaveLatent
    writes to output/, LoadLatent reads from input/ — copy the .latent file
    between them.

## MCP server for Hermes (expose Sana as an agent tool) — verified 2026-08-22
Turn the local ComfyUI Sana pipeline into a Hermes MCP tool so the agent
can generate images with ONE tool call (no hand-built API workflows).
ComfyUI models stay warm in VRAM between calls, so repeat generations are fast.
1. MCP server script (stdio protocol only, never print()): FastMCP from the
   `mcp` package — `from mcp.server.fastmcp import FastMCP;
   mcp = FastMCP("comfy-sana")`. Known-good copy:
   templates/comfy_sana_mcp_server.py (two-pass: sample+SaveLatent -> copy
   output/latents/*.latent to input/ -> LoadLatent+VAEDecode+SaveImage;
   validates <=~4.2M pixels; seed -1 -> random; returns final PNG path).
   Run it with the HERMES venv python (/home/oem/.hermes/hermes-agent/venv/bin/python
   — it has the mcp package; system python3 does not).
2. Register: `echo "Y" | hermes mcp add comfy-sana --command
   /home/oem/.hermes/hermes-agent/venv/bin/python --args
   /home/oem/.hermes/mcp/comfy-sana/server.py`
   PITFALL: `hermes mcp add` ends with an interactive "Enable all N tools?
   [Y/n/select]:" prompt — with no piped stdin it prints "Cancelled." and
   saves NOTHING. Pipe `echo "Y" |` to confirm.
3. Verify: `hermes mcp list` shows it enabled; `hermes mcp test comfy-sana`
   spawns+discovers tools. E2E truth test: drive the server with a tiny
   stdio client (mcp.ClientSession + stdio_client) and call the tool once.
4. Activation: MCP tools are discovered at agent/session start — NO hot
   reload. Either start a new chat, or restart the gateway via
   ~/.hermes/scripts/kill-gateway.py.
5. ComfyUI as a systemd USER unit: ~/.config/systemd/user/comfyui.service
   (ExecStart=venv/bin/python main.py --port 8188 --listen 127.0.0.1,
   Restart=on-failure, WantedBy=default.target), daemon-reload + manage with
   systemctl --user. NOTE: keep it DISABLED (do NOT `enable`) — Ali wants
   on-demand only; the MCP server starts it on the first image request.
   From a non-login shell systemctl --user fails with "DBUS_SESSION_BUS_ADDRESS
   and XDG_RUNTIME_DIR not defined" — first export
   XDG_RUNTIME_DIR=/run/user/$(id -u) and
   DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus.
   Kill any Hermes-background ComfyUI proc BEFORE starting the service (port
   8188 conflict). A Hermes background process dies with the gateway — a
   systemd user service does not.

## ComfyUI lifecycle / auto-start (systemd user service + MCP)
- ComfyUI runs as a systemd USER unit: ~/.config/systemd/user/comfyui.service
  (ExecStart=/home/oem/comfy/ComfyUI/venv/bin/python main.py --port 8188
  --listen 127.0.0.1). Control: systemctl --user {start,stop,restart,status}
  comfyui, logs: journalctl --user -u comfyui. REQUIRES the user bus env in
  shells: export XDG_RUNTIME_DIR=/run/user/$(id -u) (DBus addr defaults to
  $XDG_RUNTIME_DIR/bus). Gateway restarts do NOT kill it (that's why it's a
  service, not a background process).
- ON-DEMAND ONLY (Ali's explicit preference, 2026-08-23): the unit is
  DISABLED — NOT enabled, and LINGER stays OFF. Nothing runs at boot/login
  (zero idle RAM/CPU). ComfyUI starts only when the FIRST image request
  arrives: MCP's _ensure_comfy() runs `systemctl --user start comfyui`
  (works fine on a disabled unit — disable only removes the WantedBy
  symlink), with a detached direct Popen fallback for headless boots where
  the user bus is absent. Verified 2026-08-23 with a real cold reboot:
  nothing was running afterwards, the first MCP tool call brought ComfyUI up
  (~40s cold model load) and then produced 10 images in a row.
  Do NOT "fix" this back to enabled/linger without asking Ali — he wants the
  box quiet at boot.
- Timing reality: cold start (first call after reboot/stop) ~35-45s — model
  load dominates. Warm calls (server up, models resident) are fast (~1s/it
  at <=1024px; a 20-step generation + 2-pass decode ~3-10s). If the user
  complains about slowness, first ask whether the server was cold — and note
  the 4s /history poll adds latency granularity.
- MCP server ~/.hermes/mcp/comfy-sana/server.py AUTO-STARTS ComfyUI on
  demand: the generate_sana_image tool calls _ensure_comfy() first — if
  /system_stats is unreachable it runs `systemctl --user start comfyui`
  (fallback: detached Popen with start_new_session=True). Verified twice:
  service stopped -> tool call brought it back and generated; and after a
  cold reboot with nothing enabled.
- Registration: hermes mcp add comfy-sana --command <hermes venv python>
  --args ~/.hermes/mcp/comfy-sana/server.py --connect-timeout 60 (interactive
  "Enable all tools?" needs piped 'Y'). MCP tools load on the next session.
- IDLE AUTO-STOP (added 2026-08-23): the MCP server runs a watchdog thread
  that stops ComfyUI after 30 min without any generate call
  (COMFY_IDLE_STOP env overrides, e.g. for tests; COMFY_IDLE_CHECK = poll
  interval). Stop path: systemctl --user stop comfyui, falling back to
  pgrep -f "comfy/ComfyUI/main.py" + SIGTERM when the user bus is absent
  (headless boot — /run/user/<uid> may not exist). Next request auto-starts
  it again (verified: stop in ~10s idle, port down). NOTE: do NOT use
  pkill/pgrep patterns that ALSO appear in your own command line (skill:
  throttled-network-downloads). Watchdog pitfalls: module-level mutable
  state shared between the tool function and the watchdog thread MUST use
  `global` in the function that writes it (UnboundLocalError otherwise);
  Hermes spawns MCP servers with a FILTERED env (PATH/HOME/USER/... only),
  so COMFY_IDLE_* only works if set in the unit's env or in config env.
- MCP server file: ~/.hermes/mcp/comfy-sana/server.py (auto-start +
  idle-stop + two-pass sampling/decode + size/VRAM guards). A bundled copy
  for (re)installation lives in this skill: scripts/comfy_mcp_server.py —
  install with `mkdir -p ~/.hermes/mcp/comfy-sana && cp scripts/comfy_mcp_server.py ~/.hermes/mcp/comfy-sana/server.py`.

## Pitfalls
- Sending generated images to Bale: use ONE curl per terminal call
  (sendPhoto with photo=@<png>). Shell FOR-LOOPS that wrap curl (for f in ...;
  do curl ...; done) came back http=000 / empty responses in this
  environment (loop context appears network-sandboxed) — the same single
  curl works when run standalone. Batch by issuing several independent
  terminal calls in one turn instead of a loop; if a response is empty or
  not ok:true, retry that one file after a few seconds (Bale rate-limits
  rapid photo bursts). Token: grep BALE_BOT_TOKEN ~/.hermes/.env.
- VRAM claims differ wildly across official sources (8 vs 9.2 vs 13GB for the
  same model) — quote the source AND the GPU it was measured on.
- ComfyUI core has NO Sana/Gemma nodes — they come from the ExtraModels
  custom node, not core.
- Custom-node loaders auto-download from HF at runtime and can silently
  re-download big files into a second location (cache vs local_dir) —
  pre-download BOTH targets to avoid a surprise 2.3GB download at first run.
- Iranian link: multi-GB HF pulls take hours; a 0.6B test model can deliver a
  first result much sooner — offer it when the requested model is huge.
