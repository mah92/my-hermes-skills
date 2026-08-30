#!/bin/bash
# verify-bot.sh <name> — full post-deployment verification for a path-mirror
# containerized bot (hermes-bot-containers skill). Run on the HOST.
# Works with BOTH image modes: plain (host-venv mount) and baked
# (deps in /opt/hermes/.venv). Two-mode detection happens inside the container.
# Usage: bash verify-bot.sh <bot-name>
set -uo pipefail
NAME="${1:?usage: verify-bot.sh <name>}"
C="hermes-$NAME"
H="${HOME:-/home/oem}"
P="$H/.hermes/profiles/$NAME"
echo "==> 1/2 env + mounts (inside container)"
docker exec -u hermes "$C" bash -lc '
  echo "HOME=$HOME HERMES_HOME=$HERMES_HOME"
  echo "models -> $(readlink ~/.hermes/models)"
  ls ~/.hermes/models >/dev/null 2>&1 && echo "EN store visible OK"
  if [ -w /home/oem/hermes_files ]; then echo "RO-MOUNT-FAIL: hermes_files writable!"; else echo "hermes_files ro OK"; fi
  sudo -n true 2>/dev/null && echo "passwordless sudo OK" || echo "sudo MISSING"
  echo "firecrawl: $(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:3002/ 2>/dev/null)"
  if [ -e /opt/hermes/tools/web_tools.py ]; then
    echo "web-tools shim: $(grep -c search_tool_name /opt/hermes/tools/web_tools.py 2>/dev/null) occurrences (expect 3)"
  else
    echo "web-tools shim: not mounted (host has no web_tools_patch/web_tools.py) — OK"
  fi
  echo "tts-libs: $(ls /home/oem/hermes_files/tts-libs/ 2>/dev/null | wc -l) files"
  # baked → gateway interpreter; plain → mounted host venv python
  if [ -d /opt/hermes/.venv/lib/python3.*/site-packages/pypdf ]; then
    PY=/opt/hermes/.venv/bin/python3
    echo "image mode: baked (/opt/hermes/.venv)"
  else
    PY=/home/oem/.hermes/hermes-agent/venv/bin/python
    echo "image mode: plain (host-venv mount)"
  fi
  PYTHONPATH=~/.hermes/lazy-packages "$PY" -c "import firecrawl, nest_asyncio" 2>/dev/null && echo "lazy-packages OK (firecrawl+nest_asyncio)" || echo "lazy-packages MISSING"
  test -x "$PY" && echo "gateway python OK ($PY)"
'
echo "==> 2/2 voice round-trip (verbatim host commands)"
docker exec -u hermes "$C" bash -lc '
  set -a; source ~/.hermes/.env 2>/dev/null; set +a
  export LD_LIBRARY_PATH=/home/oem/hermes_files/tts-libs
  if [ -d /opt/hermes/.venv/lib/python3.*/site-packages/pypdf ]; then
    PY=/opt/hermes/.venv/bin/python3
  else
    PY=/home/oem/.hermes/hermes-agent/venv/bin/python
  fi
  echo "سلام این یک تست صوتی است" > /tmp/vb.txt
  python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.0 /tmp/vb.txt /tmp/vb.ogg 2>/dev/null && \
    echo "TTS: $(stat -c %s /tmp/vb.ogg) bytes"
  "$PY" /home/oem/.hermes/skills/hermes-persian-stt/scripts/stt.py --quiet /tmp/vb.ogg 2>/dev/null | tail -1 | sed "s/^/STT: /"
'
echo "==> bale"
grep "Connected as" "$P/logs/agent.log" 2>/dev/null | tail -1 | sed 's/.*INFO //'
echo "DONE. Any line above (other than empty STT text) that is missing = check that item."
