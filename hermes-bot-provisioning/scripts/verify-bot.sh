#!/bin/bash
# verify-bot.sh <name> — health check for one bot profile. Read-only.
#
# PROFILE checks (counted, decide the exit code): service, platform connection,
# token uniqueness, sandbox, workspace, state.db, config hygiene.
# HOST checks (advisory, labelled "host:"): the shared voice stack and the shared
# MCP servers. They pass for any profile because they exercise the host — a dead
# profile must never look healthy because of them, so they never inflate the
# profile score.
set -uo pipefail
NAME="${1:?usage: verify-bot.sh <name>}"
[[ "$NAME" =~ ^[a-z0-9-]+$ ]] || { echo "invalid profile name: '$NAME'" >&2; exit 2; }
H="${HOME:?HOME is not set}"
MAIN="$H/.hermes"
P="$MAIN/profiles/$NAME"
WS="$H/workspaces/$NAME"
HV="$MAIN/hermes-agent/venv/bin/python"
PASS=0; FAIL=0; HPASS=0; HFAIL=0
ok()  { printf '  %-36s %s\n' "$1" "PASS"; PASS=$((PASS+1)); }
bad() { printf '  %-36s %s\n' "$1" "FAIL${2:+: $2}"; FAIL=$((FAIL+1)); }
okh()  { printf '  %-36s %s\n' "host: $1" "ok${2:+ ($2)}"; HPASS=$((HPASS+1)); }
badh() { printf '  %-36s %s\n' "host: $1" "FAIL${2:+: $2}"; HFAIL=$((HFAIL+1)); }
adv() { printf '  %-36s %s\n' "$1" "$2"; }

[ -d "$P" ] || { echo "no such profile: $P" >&2; exit 2; }
[ -f "$P/config.yaml" ] || { echo "no config.yaml in $P — not a provisioned profile (typo?)" >&2; exit 2; }
[ -x "$HV" ] || { echo "no host hermes venv python at $HV" >&2; exit 2; }

cfg() { "$HV" - "$P/config.yaml" "$1" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
cur = cfg
for part in sys.argv[2].split("."):
    cur = (cur or {}).get(part) if isinstance(cur, dict) else None
print("" if cur is None else cur)
PY
}

LOG="$P/logs/agent.log"
echo "==> 1/6 service + platform"
[ "$(systemctl --user is-active "hermes-gateway-$NAME" 2>/dev/null)" = active ] \
  && ok "service active" || bad "service active" "$(systemctl --user is-active "hermes-gateway-$NAME" 2>&1)"
if [ -f "$LOG" ]; then
  grep -qa 'Connected as' "$LOG" && ok "platform connected" || bad "platform connected" "no 'Connected as' in agent.log"
  if tail -200 "$LOG" | grep -aq 'ERROR'; then
    adv "recent ERROR line" "review: $(tail -200 "$LOG" | grep -a ERROR | tail -1 | cut -c1-70)"
  else adv "recent ERROR line" "none in the last 200 lines"; fi
else
  bad "platform connected" "no $LOG yet (gateway never started?)"
  adv "recent ERROR line" "no log yet"
fi

echo "==> 2/6 token uniqueness (one token = one poller)"
for plat in bale soroush; do
  a=$(grep -m1 "^${plat^^}_BOT_TOKEN=" "$P/.env" 2>/dev/null | cut -d= -f2-)
  b=$(grep -m1 "^${plat^^}_BOT_TOKEN=" "$MAIN/.env" 2>/dev/null | cut -d= -f2-)
  if [ -n "$a" ] && [ "$a" = "$b" ]; then bad "$plat token differs from main" "same token -> double poller"
  elif [ -n "$a" ]; then ok "$plat token is bot-specific"
  else ok "$plat not configured"; fi
done

# Which platforms may poll at all: only ONE should have an active token.
active=$(grep -cE '^[A-Z0-9]+_BOT_TOKEN=' "$P/.env" 2>/dev/null || true)
[ "${active:-0}" -le 1 ] && ok "only one platform token active" || bad "only one platform token active" "$active active *_BOT_TOKEN lines"

if [ ! -f "$P/.env" ]; then bad "profile .env present" "missing"; else ok "profile .env present"; fi

echo "==> 3/6 host voice stack (advisory — shared by every profile)"
if [ -d "$H/.hermes/skills/hermes-persian-tts" ] && [ -d "$H/.hermes/skills/hermes-persian-stt" ]; then
  T=$(mktemp -d); printf 'سلام این یک تست صوتی است\n' > "$T/in.txt"
  if python3 "$H/.hermes/skills/hermes-persian-tts/scripts/tts.py" --speed 1.0 "$T/in.txt" "$T/out.ogg" >/dev/null 2>&1 && [ -s "$T/out.ogg" ]; then
    okh "TTS" "$(stat -c%s "$T/out.ogg") bytes"
    txt=$("$HV" "$H/.hermes/skills/hermes-persian-stt/scripts/stt.py" --quiet "$T/out.ogg" 2>/dev/null | tail -1)
    [ -n "${txt// /}" ] && okh "STT round trip" "${txt:0:24}" || badh "STT round trip" "empty transcript"
  else badh "TTS" "tts.py produced no audio"; fi
  rm -rf "$T"
else adv "host: voice stack" "hermes-persian-tts/stt not installed — skipped"; fi

echo "==> 4/6 host MCP servers (advisory)"
mcp_count=$("$HV" - "$P/config.yaml" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
print(len(cfg.get("mcp_servers") or {}))
PY
)
if [ "$mcp_count" = 0 ]; then adv "host: MCP servers" "none configured"; else adv "host: MCP servers" "$mcp_count configured (check 'MCP: registered' / handshake in the gateway log)"; fi

echo "==> 5/6 terminal backend"
back=$(cfg "terminal.backend")
if [ -z "$back" ]; then bad "terminal backend" "config.yaml defines none"
elif [ "$back" = docker ]; then
  img=$(cfg "terminal.docker_image")
  if [ -z "$img" ]; then bad "sandbox image configured" "terminal.docker_image is empty"
  elif docker image inspect "$img" >/dev/null 2>&1; then ok "sandbox image present ($img)"
  else bad "sandbox image present" "$img missing"; fi
  if [ -n "$img" ]; then
    if docker run --rm --entrypoint sh "$img" -c 'command -v hermes || test -e /opt/hermes' >/dev/null 2>&1; then bad "sandbox is Hermes-free" "hermes found inside $img"
    else ok "sandbox is Hermes-free"; fi
    adv "sandbox containers now" "$(docker ps -aq --filter "label=hermes-profile=$NAME" 2>/dev/null | wc -l) (0 = released while idle)"
  fi
else ok "backend local (no container)"; fi
[ -d "$WS" ] && ok "workspace present" || bad "workspace" "$WS missing"

echo "==> 6/6 config hygiene"
grep -q '/opt/hermes' "$P/config.yaml" "$P/.env" 2>/dev/null && bad "no container-only paths" "found /opt/hermes refs" || ok "no container-only paths"
[ -r "$P/state.db" ] && ok "state.db present" || bad "state.db" "missing"

echo
echo "==> $NAME: $PASS pass / $FAIL fail (profile)   |   $HPASS ok / $HFAIL fail (host, advisory)"
[ "$FAIL" -eq 0 ]
