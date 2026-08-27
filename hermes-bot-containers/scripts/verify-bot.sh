#!/bin/bash
# verify-bot.sh <name> — full post-deployment verification for a path-mirror
# containerized bot (hermes-bot-containers skill). Run on the HOST.
# Usage: bash verify-bot.sh <bot-name>
set -uo pipefail
NAME="${1:?usage: verify-bot.sh <name>}"
C="hermes-$NAME"
H="/home/oem"
P="$H/.hermes/profiles/$NAME"
echo "==> 1/2 env + mounts (inside container)"
docker exec -u hermes "$C" bash -lc '
  echo "HOME=$HOME HERMES_HOME=$HERMES_HOME"
  echo "models -> $(readlink ~/.hermes/models)"
  ls ~/.hermes/models >/dev/null 2>&1 && echo "EN store visible OK"
  if [ -w /home/oem/hermes_files ]; then echo "RO-MOUNT-FAIL: hermes_files writable!"; else echo "hermes_files ro OK"; fi
  sudo -n true 2>/dev/null && echo "passwordless sudo OK" || echo "sudo MISSING"
  echo "firecrawl: $(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:3002/ 2>/dev/null)"
  test -x /home/oem/miniconda3/envs/vits2/bin/python && echo "conda vits2 OK"
'
echo "==> 2/2 voice round-trip (verbatim host commands)"
docker exec -u hermes "$C" bash -lc '
  set -a; source ~/.hermes/.env 2>/dev/null; set +a
  echo "سلام این یک تست صوتی است" > /tmp/vb.txt
  python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.0 /tmp/vb.txt /tmp/vb.ogg 2>/dev/null && \
    echo "TTS: $(stat -c %s /tmp/vb.ogg) bytes"
  /home/oem/miniconda3/envs/vits2/bin/python /home/oem/Basir/STT/stt.py --quiet /tmp/vb.ogg 2>/dev/null | tail -1 | sed "s/^/STT: /"
  /home/oem/miniconda3/envs/vits2/bin/python /home/oem/.hermes/skills/mlops/sherpa-onnx-en-stt/scripts/transcribe_en.py /tmp/vb.ogg >/dev/null 2>&1 && \
    sed "s/^/EN-STT: /" /tmp/vb_transcript.txt 2>/dev/null
'
echo "==> bale"
grep "Connected as" "$P/logs/agent.log" 2>/dev/null | tail -1 | sed 's/.*INFO //'
echo "DONE. Any line above (other than empty STT text) that is missing = check that item."
