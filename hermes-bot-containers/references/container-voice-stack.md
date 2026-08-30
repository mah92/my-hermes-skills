# Container voice stack (TTS/STT) — diagnostics & repair

Symptom: a bot tells its user "STT engine not installed / voice broken", or the TTS daemon
errors `failed to start daemon` / `daemon did not start within 15s` inside a container while
the main host voice works fine. Verified end-to-end 2026-08-28 (a heavy-user profile complaint).

## Trap #1 — `docker exec` lacks the gateway env
`docker exec bash -lc` does NOT carry the gateway's environment. ALWAYS source the profile
env before hand-testing voice inside a container:
```
docker exec -u hermes hermes-<name> bash -lc 'set -a; source ~/.hermes/.env; set +a; export LD_LIBRARY_PATH=/home/oem/hermes_files/tts-libs; ...'
```
Without sourcing, tts.py fails with a misleading `Error: MATCHA_TTS_BIN is not set` — a
false alarm, not a real bug.

## Trap #2 — profile .env keeps HOST-ONLY paths copied from main
- `MATCHA_TTS_BIN=/home/oem/matcha_tts_infer/build/MatchaTTSInfer` is **not mounted** into
  containers. The visible copy lives per-bot at
  `/home/oem/workspaces/<name>/matcha_tts_infer/build/MatchaTTSInfer` (rw workspace mount;
  the `../NormalizeText` sibling the daemon derives exists there too).
- `ESPEAK_DATA=/usr/lib/x86_64-linux-gnu/espeak-ng-data` is host-only → repoint to the
  ro-shared `/home/oem/hermes_files/tts-libs/espeak-ng-data` (a copy of the host dir).
Fix both lines in `~/.hermes/profiles/<name>/.env`, then `docker restart hermes-<name>`
(reloads .env; no recreate needed).

## Required shared libs (`hermes_files/tts-libs`)
`LD_LIBRARY_PATH=/home/oem/hermes_files/tts-libs` is set by compose; the dir must actually
contain ALL of:
- libonnxruntime.so.1 — copy from `/usr/local/lib` or the hermes-agent venv
  (`.../venv/lib/python3.11/site-packages/onnxruntime/capi/libonnxruntime.so.1.28.0`)
- libicuuc.so.<hostver> / libicui18n.so.<hostver> / libicudata.so.<hostver> — the HOST's
  version (e.g. `.74` on Ubuntu 24.04). Do NOT hardcode `.70`.
- libespeak-ng.so.1
- **libpcaudio.so.0 and libsonic.so.0** — espeak-ng's audio deps, easy to miss; the daemon
  fails with `not found` on these AFTER the obvious libs are fixed.
- espeak-ng-data/ (≈13M, full dir copy)

Verify from inside the container: `ldd <workspace-bin> | grep "not found"` must be empty;
copy-more-and-recheck until it is. Copy real files with `cp -aL` / `cp -a <versioned-file>` —
`cp -av` on the system's `.so` symlinks copies DANGLING symlinks (libs that resolve to
nothing).

## Restore when hermes_files is empty / wiped
The shared ro-store `/home/oem/hermes_files` can be found empty and root-owned (wiped
2026-08-27 20:37). It is NOT in the git backup (model binaries excluded by design), so
restore from live host copies:
```
sudo mkdir -p /home/oem/hermes_files/tts-libs
sudo cp -aL /usr/local/lib/libonnxruntime.so.1 /lib/x86_64-linux-gnu/libicuuc.so.74 \
  /lib/x86_64-linux-gnu/libicui18n.so.74 /lib/x86_64-linux-gnu/libicudata.so.74 \
  /lib/x86_64-linux-gnu/libespeak-ng.so.1 /usr/lib/x86_64-linux-gnu/libpcaudio.so.0 \
  /usr/lib/x86_64-linux-gnu/libsonic.so.0 /home/oem/hermes_files/tts-libs/
sudo cp -a /usr/lib/x86_64-linux-gnu/espeak-ng-data /home/oem/hermes_files/tts-libs/
# models
mkdir -p hermes_files/{sherpa-onnx-en-stt,hermes-persian-stt/models,hermes-persian-tts/models}
cp -a /home/oem/.hermes/models/sherpa-onnx-paraformer-en-2023-09-16  hermes_files/sherpa-onnx-en-stt/
cp -a /home/oem/.hermes/skills/hermes-persian-stt/models/{shenava-koochik,hush_cpp}  hermes_files/hermes-persian-stt/models/
cp -a /home/oem/.hermes/skills/hermes-persian-tts/models/*  hermes_files/hermes-persian-tts/models/
sudo chown -R oem:oem /home/oem/hermes_files/
```
Then verify from INSIDE any container (`ls /home/oem/hermes_files/tts-libs/libsonic.so.0`,
`ls ~/.hermes/models/`) — the ro mount picks the restored files up instantly.

## Roundtrip verification (the correct way)
```
docker exec -u hermes hermes-<name> bash -lc 'set -a; source ~/.hermes/.env; set +a; export LD_LIBRARY_PATH=/home/oem/hermes_files/tts-libs; echo "سِلام، این یک تست تبدیل صدا به متن است" > /tmp/t.txt; python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.2 /tmp/t.txt /tmp/t.ogg && /home/oem/.hermes/hermes-agent/venv/bin/python /home/oem/.hermes/skills/hermes-persian-stt/scripts/stt.py --quiet /tmp/t.ogg'
```
Expect the exact same sentence back (proved after the tts-libs rebuild).

## Red herrings seen in the field (save hours)
- **Bale attachments arrive with the ORIGINAL filename** (e.g. QA_Manager_JD_draft.pdf) in
  the bot's workspace/cwd — NOT the numeric upload ID. A bot that `find`s by the numeric ID
  concludes "file lost" and asks the user to resend while the file sits on disk. Remediate:
  search by content/mtime; insert a memory fact into the bot profile's memory_store.db
  (facts table: content/category/tags/trust_score/created_at/updated_at) —
  "attachments arrive by original name; use find, never claim a file is lost".
- **"Voice" files can be byte-identical copies of the PDF** (identical md5, `.ogg` name,
  magic bytes `%PDF`): run `head -c 8 <file> | od -c` (OggS vs %PDF) BEFORE debugging STT —
  garbage in, garbage out; the STT failure was correct, the "engine missing" conclusion wasn't.
- **Reasoning LLMs return content:"" at low max_tokens** (deepseek-v4-flash,
  finish_reason=length, tokens consumed by reasoning_content). When live-testing API keys,
  judge by HTTP 200 + echoed model name, NOT by content.
