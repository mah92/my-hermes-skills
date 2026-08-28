#!/bin/bash
# verify-bot.sh <name> — full post-deployment verification for a path-mirror
# containerized bot (hermes-bot-containers skill). Run on the HOST.
# Usage: bash verify-bot.sh <bot-name>
set -uo pipefail
NAME="${1:?usage: verify-bot.sh <name>}"
C="hermes-$NAME"
H="/home/oem"
P="$H/.hermes/profiles/$NAME"
FAIL=0

echo "==> 1/3 env + mounts (inside container)"
echo "host time: $(date '+%F %T %Z')"
docker exec -u hermes "$C" bash -lc '
  echo "HOME=$HOME HERMES_HOME=$HERMES_HOME"
  echo "container time: $(date "+%F %T %Z")   (TZ=$TZ)"
  echo "models -> $(readlink ~/.hermes/models)"
  ls ~/.hermes/models >/dev/null 2>&1 && echo "EN store visible OK"
  if [ -w /home/oem/hermes_files ]; then echo "RO-MOUNT-FAIL: hermes_files writable!"; else echo "hermes_files ro OK"; fi
  sudo -n true 2>/dev/null && echo "passwordless sudo OK" || echo "sudo MISSING"
  echo "firecrawl: $(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:3002/ 2>/dev/null)"
  test -x /home/oem/.hermes/hermes-agent/venv/bin/python && echo "hermes-venv OK"
'

echo "==> 2/3 shared TTS store (ro mount, inside container)"
docker exec -u hermes "$C" bash -lc '
  L=/home/oem/hermes_files/tts-libs
  MISS=""
  for f in libonnxruntime.so.1 libespeak-ng.so.1 libicuuc.so.* libicui18n.so.* libicudata.so.* libpcaudio.so.0 libsonic.so.0; do
    ls $L/$f >/dev/null 2>&1 || MISS="$MISS $f"
  done
  [ -d "$L/espeak-ng-data" ] || MISS="$MISS espeak-ng-data/"
  [ -x /home/oem/hermes_files/matcha_tts_infer/build/MatchaTTSInfer ] || MISS="$MISS daemon"
  [ -d /home/oem/hermes_files/matcha_tts_infer/NormalizeText ] || MISS="$MISS NormalizeText/"
  if [ -n "$MISS" ]; then echo "STORE-MISSING:$MISS"; exit 1; else echo "tts-libs ($(ls $L | wc -l) entries) + daemon + NormalizeText OK"; fi
'
if [ $? -ne 0 ]; then FAIL=1; echo "  ^ TTS store check FAILED"; fi

echo "==> 3/3 voice round-trip (TTS->STT, LD_LIBRARY_PATH to shared store)"
docker exec -u hermes "$C" bash -lc '
  set -a; source ~/.hermes/.env 2>/dev/null; set +a
  export LD_LIBRARY_PATH=/home/oem/hermes_files/tts-libs
  case "$MATCHA_TTS_BIN" in
    "$HOME/hermes_files/"*) echo "MATCHA_TTS_BIN OK (hermes_files)";;
    *) echo "ENV-FAIL: MATCHA_TTS_BIN=$MATCHA_TTS_BIN (must point into hermes_files)"; exit 1;;
  esac
  case "$ESPEAK_DATA" in
    "$HOME/hermes_files/"*) echo "ESPEAK_DATA OK (hermes_files)";;
    *) echo "ENV-FAIL: ESPEAK_DATA=$ESPEAK_DATA (must point into hermes_files)"; exit 1;;
  esac
  echo "سلام این یک تست صوتی است" > /tmp/vb.txt
  python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.0 /tmp/vb.txt /tmp/vb.ogg 2>/dev/null || { echo "TTS-FAIL"; exit 1; }
  echo "TTS: $(stat -c %s /tmp/vb.ogg) bytes"
  TEXT=$(/home/oem/.hermes/hermes-agent/venv/bin/python /home/oem/.hermes/skills/hermes-persian-stt/scripts/stt.py --quiet /tmp/vb.ogg 2>/dev/null | tail -1)
  if [ -n "$TEXT" ]; then echo "STT: $TEXT"; else echo "STT-EMPTY-FAIL"; exit 1; fi
  /home/oem/.hermes/hermes-agent/venv/bin/python /home/oem/.hermes/skills/mlops/sherpa-onnx-en-stt/scripts/transcribe_en.py /tmp/vb.ogg >/dev/null 2>&1 && \
    sed "s/^/EN-STT: /" /tmp/vb_transcript.txt 2>/dev/null
'
if [ $? -ne 0 ]; then FAIL=1; echo "  ^ voice round-trip FAILED"; fi

echo "==> bale"
grep "Connected as" "$P/logs/agent.log" 2>/dev/null | tail -1 | sed 's/.*INFO //'
if [ "$FAIL" -eq 0 ]; then
  echo "DONE. All checks passed."
else
  echo "DONE with FAILURES (see above)." >&2
  exit 1
fi
