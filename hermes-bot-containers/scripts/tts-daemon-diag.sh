#!/bin/bash
# tts-daemon-diag.sh — diagnose the MatchaTTS daemon INSIDE a containerized bot.
# Run inside the container (docker exec -u hermes hermes-<name> bash /tmp/tts-daemon-diag.sh)
# or copy it in first. Covers the three classic failures:
#   stale socket (Connection refused), missing LD_LIBRARY_PATH, locale abort.
set -u
export MATCHA_TTS_BIN=/home/oem/Basir/TTS/match_tts_infer/build/MatchaTTSInfer
export ESPEAK_DATA=/home/oem/Basir/TTS/Piper/piper_linux_x86_64/piper/espeak-ng-data
echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-UNSET (set it in compose env!)}"
test -x "$MATCHA_TTS_BIN" || { echo "FAIL: MATCHA_TTS_BIN missing"; exit 1; }
ldd "$MATCHA_TTS_BIN" 2>/dev/null | grep "not found" && echo "FAIL: missing .so's (hermes_files/tts-libs + LD_LIBRARY_PATH)" || echo "libs OK"
# stale socket check (hardened tts.py handles this automatically since 2026-08)
if [ -S /tmp/tts_infer.sock ]; then
  python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(1)
    s.connect("/tmp/tts_infer.sock"); s.close(); print("socket LIVE")
except OSError:
    print("socket STALE (daemon dead) — tts.py will unlink+restart; or rm -f /tmp/tts_infer.sock")
PY
else
  echo "no socket (daemon not running — tts.py starts it on first request)"
fi
# locale sanity (C++ std::locale abort fix = host /usr/lib/locale + /usr/share/i18n mounts)
locale -a 2>/dev/null | grep -E "fa_IR|C.utf8" | head -2 || echo "locale data missing? check mounts"
# functional one-shot synth
echo "تست دیمون" > /tmp/diag.txt
python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.0 /tmp/diag.txt /tmp/diag.ogg 2>&1 | tail -1
ls -la /tmp/diag.ogg 2>/dev/null | awk '{print "synth OK:", $5, "bytes"}' || echo "synth FAILED (paste tts.py output above)"
