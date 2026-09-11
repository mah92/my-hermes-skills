#!/bin/bash
# rm-bot.sh <name> — remove a bot cleanly: gateway service, sandbox containers,
# profile dir, workspace. Never touches the main profile, shared skills or any
# shared image.
#
# Liveness: a profile must not be deleted while a poller for it is alive. Identity
# is resolved from the process ENVIRONMENT (HERMES_HOME=.../profiles/<name>) and
# from the unit's MainPID — never from an argv substring, which both misses
# (`hermes -p NAME gateway run`) and false-positives (an operator's own shell).
set -euo pipefail

NAME="${1:-}"
[ -n "$NAME" ] || { echo "usage: rm-bot.sh <name>" >&2; exit 2; }
[[ "$NAME" =~ ^[a-z0-9-]+$ ]] || { echo "Name must be lowercase [a-z0-9-]" >&2; exit 2; }
H="${HOME:?HOME is not set}"
MAIN="${HERMES_HOME:-$H/.hermes}"
PROF="$MAIN/profiles/$NAME"
WS="$H/workspaces/$NAME"
HERMES="${HERMES_BIN:-$MAIN/hermes-agent/venv/bin/hermes}"
PY="${HERMES_PY:-$MAIN/hermes-agent/venv/bin/python}"
UNIT="$H/.config/systemd/user/hermes-gateway-$NAME.service"
LEFT=0

# print "pid<TAB>home<TAB>cmdline" for every live gateway of THIS profile,
# excluding our own process tree and the unit's MainPID (which we stop ourselves)
exclude_self=$(awk -v p=$$ 'BEGIN{for(i=0;i<12;i++){print p; p=0}}' )
pollers() {
  "${PY:-python3}" - "$NAME" "$$" "$PPID" "${1:-0}" <<'PY'
import os, sys
name, *self_pids = sys.argv[1:]
for pid in sorted(os.listdir("/proc")):
    if not pid.isdigit() or pid in self_pids: continue
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "replace").replace("\0", " ").strip()
        env = open(f"/proc/{pid}/environ", "rb").read().decode("utf-8", "replace").split("\0")
    except Exception:
        continue
    if "gateway" not in cmd or " run" not in cmd: continue   # not a gateway run
    home = next((kv.split("=", 1)[1] for kv in env if kv.startswith("HERMES_HOME=")), "")
    by_env = home.rstrip("/").endswith("/profiles/" + name)
    by_arg = f"--profile {name}" in cmd or f"-p {name} " in cmd or cmd.endswith(f"-p {name} gateway run")
    if by_env or by_arg:
        print(f"{pid}\t{home or '-'}\t{cmd[:110]}")
PY
}

exists=0
[ -e "$PROF" ] && exists=1
[ -e "$WS" ] && exists=1
[ -f "$UNIT" ] && exists=1
if [ "$exists" -eq 0 ]; then
  echo "nothing to remove: no profile ($PROF), no workspace ($WS), no unit ($UNIT)"
  exit 3
fi

echo "==> 1/5 checking for a live poller (before changing anything)"
MAINPID="$(systemctl --user show -p MainPID --value "hermes-gateway-$NAME" 2>/dev/null || echo 0)"
STRAY="$(pollers "${MAINPID:-0}")"
if [ -n "$STRAY" ]; then
  echo "ERROR: a gateway process for '$NAME' is running outside its unit — NOTHING was changed." >&2
  echo "$STRAY" | sed 's/^/       pid /' >&2
  echo "       stop it (kill <pid>), then re-run." >&2
  exit 1
fi
echo "   no stray poller"

echo "==> 2/5 stopping the gateway service"
UNIT_EXISTED=0
if [ -f "$UNIT" ]; then
  UNIT_EXISTED=1
  systemctl --user disable --now "hermes-gateway-$NAME" >/dev/null 2>&1 && echo "   stopped + disabled" || echo "   service was not running"
  if [[ -x "$HERMES" ]] && "$HERMES" -p "$NAME" gateway uninstall >/dev/null 2>&1; then echo "   unit uninstalled"
  else rm -f "$UNIT" "$H/.config/systemd/user/default.target.wants/hermes-gateway-$NAME.service" 2>/dev/null \
         && echo "   unit file removed (hermes uninstall unavailable)"; fi
  systemctl --user daemon-reload 2>/dev/null || true
else
  echo "   no unit installed for '$NAME'"
fi

# re-check: something that survived the stop is a poller we must not delete under
sleep 1
SURVIVOR="$(pollers 0)"
if [ -n "$SURVIVOR" ]; then
  echo "ERROR: a gateway for '$NAME' survived the stop — the service was stopped, NO data was deleted." >&2
  echo "$SURVIVOR" | sed 's/^/       pid /' >&2
  exit 1
fi

echo "==> 3/5 sandbox containers for this profile"
mapfile -t CIDS < <(docker ps -aq --filter "label=hermes-profile=$NAME" 2>/dev/null || true)
if [[ ${#CIDS[@]} -gt 0 ]]; then
  docker rm -f "${CIDS[@]}" >/dev/null 2>&1 && echo "   removed ${#CIDS[@]} container(s)" || { echo "   WARNING: could not remove ${#CIDS[@]} container(s)" >&2; LEFT=1; }
else echo "   none"; fi
docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "hermes-$NAME" \
  && { docker rm -f "hermes-$NAME" >/dev/null 2>&1 && echo "   removed legacy container hermes-$NAME"; } || true

echo "==> 4/5 removing profile + workspace"
[[ -z "${SUDO_PASSWORD:-}" ]] && SUDO_PASSWORD="$(grep -m1 '^SUDO_PASSWORD=' "$MAIN/.env" 2>/dev/null | cut -d= -f2-)" || true
remove_tree() {
  local p
  for p in "$@"; do
    if [ -e "$p" ] || [ -L "$p" ]; then
      if rm -rf "$p" 2>/dev/null; then echo "   removed $p"
      elif sudo -n rm -rf "$p" 2>/dev/null; then echo "   removed $p (passwordless sudo)"
      elif [ -n "${SUDO_PASSWORD:-}" ]; then
        if echo "$SUDO_PASSWORD" | sudo -S -p "" rm -rf "$p" 2>/dev/null; then echo "   removed $p (sudo)"
        else echo "   CANNOT REMOVE $p (sudo failed) — run: sudo rm -rf $p" >&2; LEFT=1; fi
      else echo "   CANNOT REMOVE $p (root-owned) — run: sudo rm -rf $p" >&2; LEFT=1; fi
    else echo "   already gone: $p"; fi
  done
  return 0
}
remove_tree "$PROF" "$WS"

echo "==> 5/5 leftovers"
for p in "$PROF" "$WS"; do [ -e "$p" ] && { echo "   LEFTOVER: $p"; LEFT=1; }; done
[ -f "$UNIT" ] && { echo "   LEFTOVER: $UNIT"; LEFT=1; }
[ -n "$(pollers 0)" ] && { echo "   LEFTOVER: a gateway process is still running"; LEFT=1; }
[ "$LEFT" -eq 0 ] && echo "   clean"

if [ "$LEFT" -eq 0 ]; then
  echo "DONE. Bot '$NAME' removed (service, sandbox containers, profile, workspace)."
  echo "      Shared skills, the main profile and any shared image were NOT touched."
else
  echo "WARNING: leftovers remain (see the LEFTOVER lines above)." >&2; exit 1
fi
