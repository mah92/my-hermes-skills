#!/bin/bash
# verify-bot.sh <name> — health check for one bot profile. Read-only.
#
# PROFILE checks decide the exit code. Checks that cannot be judged yet (a
# --no-start profile has no unit and no log) are reported as PENDING, not FAIL,
# so a clean provision is not reported as broken.
# HOST checks (the shared voice stack and MCP servers) are advisory and labelled;
# a dead profile must never look healthy because of them.
set -uo pipefail
NAME="${1:-}"
[ -n "$NAME" ] || { echo "usage: verify-bot.sh <name>" >&2; exit 2; }
[[ "$NAME" =~ ^[a-z0-9-]+$ ]] || { echo "invalid profile name: '$NAME'" >&2; exit 2; }
H="${HOME:?HOME is not set}"
MAIN="${HERMES_HOME:-$H/.hermes}"
P="$MAIN/profiles/$NAME"
WS="$H/workspaces/$NAME"
PY="${HERMES_PY:-$MAIN/hermes-agent/venv/bin/python}"
UNIT="$H/.config/systemd/user/hermes-gateway-$NAME.service"
PASS=0; FAIL=0; PEND=0; HPASS=0; HFAIL=0
ok()   { printf '  %-36s %s\n' "$1" "PASS"; PASS=$((PASS+1)); }
bad()  { printf '  %-36s %s\n' "$1" "FAIL${2:+: $2}"; FAIL=$((FAIL+1)); }
pend() { printf '  %-36s %s\n' "$1" "PENDING${2:+ ($2)}"; PEND=$((PEND+1)); }
okh()  { printf '  %-36s %s\n' "host: $1" "ok${2:+ ($2)}"; HPASS=$((HPASS+1)); }
badh() { printf '  %-36s %s\n' "host: $1" "FAIL${2:+: $2}"; HFAIL=$((HFAIL+1)); }
adv()  { printf '  %-36s %s\n' "$1" "$2"; }

[ -d "$P" ] || { echo "no such profile: $P" >&2; exit 2; }
[ -f "$P/config.yaml" ] || { echo "no config.yaml in $P — not a provisioned profile (typo?)" >&2; exit 2; }
[ -x "$PY" ] || { echo "no hermes venv python at $PY" >&2; exit 2; }

cfg() { "$PY" - "$P/config.yaml" "$1" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
cur = cfg
for part in sys.argv[2].split("."):
    cur = (cur or {}).get(part) if isinstance(cur, dict) else None
print("" if cur is None else cur)
PY
}

LOG="$P/logs/agent.log"
STARTED=0
[ -f "$UNIT" ] && STARTED=1
[ -f "$LOG" ] && STARTED=1

echo "==> 1/6 service + platform"
if [ -f "$UNIT" ]; then
  [ "$(systemctl --user is-active "hermes-gateway-$NAME" 2>/dev/null)" = active ] \
    && ok "service active" || bad "service active" "$(systemctl --user is-active "hermes-gateway-$NAME" 2>&1)"
  if [ -f "$LOG" ]; then
    if grep -qa 'Connected as @[^ ]' "$LOG"; then ok "platform connected (handle seen)"
    elif grep -qa 'Connected as' "$LOG"; then bad "platform connected" "'Connected as' with an EMPTY handle — the platform did not accept this token"
    else bad "platform connected" "no 'Connected as' in agent.log"; fi
    if tail -200 "$LOG" | grep -aq 'ERROR'; then
      adv "recent ERROR line" "review: $(tail -200 "$LOG" | grep -a ERROR | tail -1 | cut -c1-70)"
    else adv "recent ERROR line" "none in the last 200 lines"; fi
  else
    pend "platform connected" "no agent.log yet"
    adv "recent ERROR line" "no log yet"
  fi
else
  pend "service active" "no unit installed (--no-start?)"
  pend "platform connected" "gateway never started"
fi

echo "==> 2/6 credentials"
ACT_PLAT=""
for plat in bale soroush; do
  a=$(grep -m1 "^${plat^^}_BOT_TOKEN=" "$P/.env" 2>/dev/null | cut -d= -f2-)
  b=$(grep -m1 "^${plat^^}_BOT_TOKEN=" "$MAIN/.env" 2>/dev/null | cut -d= -f2-)
  if [ -n "$a" ]; then ACT_PLAT="$plat"; fi
  if [ -n "$a" ] && [ "$a" = "$b" ]; then bad "$plat token differs from main" "same token -> double poller"
  elif [ -n "$a" ]; then ok "$plat token is bot-specific"
  else ok "$plat not configured"; fi
done
active=$(grep -cE '^[A-Z0-9]+_BOT_TOKEN=' "$P/.env" 2>/dev/null || true)
[ "${active:-0}" -le 1 ] && ok "only one platform token active" || bad "only one platform token active" "$active active *_BOT_TOKEN lines"
dup=""
for other in "$MAIN"/profiles/*/.env; do
  [ -f "$other" ] || continue
  case "$other" in "$P/.env") continue ;; esac
  o=$(grep -m1 "^${ACT_PLAT^^}_BOT_TOKEN=" "$other" 2>/dev/null | cut -d= -f2- || true)
  a=$(grep -m1 "^${ACT_PLAT^^}_BOT_TOKEN=" "$P/.env" 2>/dev/null | cut -d= -f2- || true)
  [ -n "$o" ] && [ "$o" = "$a" ] && dup="$other"
done
if [ -n "$dup" ]; then bad "token unique across profiles" "same token also in ${dup##*/profiles/}" ; else ok "token unique across profiles"; fi
if [ ! -f "$P/.env" ]; then bad "profile .env present" "missing"; else ok "profile .env present"; fi

# getMe: a green 'Connected as' can be a lie (some adapters log it for a bad
# token with an empty handle), so ask the platform directly when we can.
tok=$(grep -m1 "^${ACT_PLAT^^}_BOT_TOKEN=" "$P/.env" 2>/dev/null | cut -d= -f2- || true)
api=""
case "$ACT_PLAT" in bale) api="https://tapi.bale.ai" ;; soroush) api="https://api.splus.ir" ;; esac
if [ -n "$tok" ] && [ -n "$api" ] && command -v curl >/dev/null 2>&1; then
  resp=$(curl -s -m 12 "$api/bot$tok/getMe" 2>/dev/null || true)
  case "$resp" in
    *'"ok":true'*) ok "platform accepts the token (getMe)" ;;
    *'"ok":false'*) bad "platform accepts the token (getMe)" "$(printf '%s' "$resp" | tr -d '\n' | cut -c1-70)" ;;
    *) adv "platform accepts the token" "no answer from $api (network/outage? not counted)" ;;
  esac
else
  adv "platform accepts the token" "skipped (no token/curl)"
fi

echo "==> 3/6 host voice stack (advisory — runs THIS profile's configured providers)"
mapfile -t TTS_INFO < <("$PY" - "$P/config.yaml" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
tts = cfg.get("tts") or {}
prov = (tts.get("providers") or {}).get(tts.get("provider")) or {}
cmd = prov.get("command") if prov.get("type") == "command" else ""
print((cmd or "").replace("\n", " ")); print(prov.get("output_format") or "ogg")
PY
)
mapfile -t STT_INFO < <("$PY" - "$P/config.yaml" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
stt = cfg.get("stt") or {}
prov = (stt.get("providers") or {}).get(stt.get("provider")) or {}
cmd = prov.get("command") if prov.get("type") == "command" else ""
print((cmd or "").replace("\n", " "))
PY
)
TTS_CMD="${TTS_INFO[0]:-}"; TTS_FMT="${TTS_INFO[1]:-ogg}"; STT_CMD="${STT_INFO[0]:-}"
if [ -n "$TTS_CMD" ]; then
  T=$(mktemp -d); printf 'test 1 2 3\n' > "$T/in.txt"
  tts_run=$(sed -e "s|{input_path}|$T/in.txt|g" -e "s|{output_path}|$T/out.$TTS_FMT|g" <<<"$TTS_CMD")
  if bash -c "$tts_run" >/dev/null 2>&1 && [ -s "$T/out.$TTS_FMT" ]; then
    okh "TTS (profile's own provider)" "$(stat -c%s "$T/out.$TTS_FMT") bytes"
    if [ -n "$STT_CMD" ]; then
      stt_run=$(sed -e "s|{input_path}|$T/out.$TTS_FMT|g" <<<"$STT_CMD")
      txt=$(bash -c "$stt_run" 2>/dev/null | tail -1)
      [ -n "${txt// /}" ] && okh "STT round trip" "${txt:0:24}" || badh "STT round trip" "empty transcript"
    else adv "host: STT round trip" "STT provider is not command-type — skipped"; fi
  else badh "TTS (profile's own provider)" "the configured command produced no audio"; fi
  rm -rf "$T"
else adv "host: voice" "no command-type TTS provider configured — skipped"; fi

echo "==> 4/6 host MCP servers (advisory — count only, no handshake)"
mcp_count=$("$PY" - "$P/config.yaml" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
print(len(cfg.get("mcp_servers") or {}))
PY
)
if [ "$mcp_count" = 0 ]; then adv "host: MCP servers" "none configured"; else adv "host: MCP servers" "$mcp_count configured — see 'MCP: registered' in the gateway log"; fi

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
if [ -r "$P/state.db" ]; then ok "state.db present"
elif [ "$STARTED" -eq 0 ]; then pend "state.db present" "gateway never started"
else bad "state.db" "missing"; fi

echo
echo "==> $NAME: $PASS pass / $FAIL fail / $PEND pending (profile)   |   $HPASS ok / $HFAIL fail (host, advisory)"
[ "$FAIL" -eq 0 ]
