#!/bin/bash
# rm-bot.sh <name> — remove a bot cleanly: gateway service, sandbox containers,
# profile dir, workspace. Never touches the main profile, shared skills, or any
# shared image. Refuses to delete data while the bot's gateway is still running.
set -euo pipefail

NAME="${1:?usage: rm-bot.sh <name>}"
[[ "$NAME" =~ ^[a-z0-9-]+$ ]] || { echo "Name must be lowercase [a-z0-9-]" >&2; exit 2; }
H="${HOME:?HOME is not set}"
MAIN="$H/.hermes"
PROF="$MAIN/profiles/$NAME"
WS="$H/workspaces/$NAME"
HERMES="$MAIN/hermes-agent/venv/bin/hermes"
UNIT="$H/.config/systemd/user/hermes-gateway-$NAME.service"
LEFT=0

if [ ! -e "$PROF" ] && [ ! -e "$WS" ]; then
  echo "nothing to remove: no profile at $PROF and no workspace at $WS"
fi

echo "==> 1/5 stopping the gateway service"
if [ -f "$UNIT" ]; then
  systemctl --user disable --now "hermes-gateway-$NAME" >/dev/null 2>&1 && echo "   stopped + disabled" || echo "   service was not running"
  if [[ -x "$HERMES" ]] && "$HERMES" -p "$NAME" gateway uninstall >/dev/null 2>&1; then echo "   unit uninstalled"
  else rm -f "$UNIT" "$H/.config/systemd/user/default.target.wants/hermes-gateway-$NAME.service" 2>/dev/null \
         && echo "   unit file removed (hermes uninstall unavailable)"; fi
  systemctl --user daemon-reload 2>/dev/null || true
else
  echo "   no unit installed for '$NAME'"
fi

# Refuse BEFORE touching data: a live poller on this profile means something is
# still using it (the service above was stopped, so this is a stray/other poller).
if pgrep -af "profile $NAME gateway run" >/dev/null 2>&1; then
  echo "ERROR: a gateway process for '$NAME' is still running — NO data was deleted." >&2
  pgrep -af "profile $NAME gateway run" >&2
  echo "       stop it (kill <pid> or systemctl --user stop hermes-gateway-$NAME), then re-run." >&2
  exit 1
fi

echo "==> 2/5 sandbox containers for this profile"
mapfile -t CIDS < <(docker ps -aq --filter "label=hermes-profile=$NAME" 2>/dev/null || true)
if [[ ${#CIDS[@]} -gt 0 ]]; then
  docker rm -f "${CIDS[@]}" >/dev/null 2>&1 && echo "   removed ${#CIDS[@]} container(s)" || { echo "   WARNING: could not remove ${#CIDS[@]} container(s)" >&2; LEFT=1; }
else echo "   none"; fi
docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "hermes-$NAME" \
  && { docker rm -f "hermes-$NAME" >/dev/null 2>&1 && echo "   removed legacy container hermes-$NAME"; } || true

echo "==> 3/5 removing profile + workspace"
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

echo "==> 4/5 leftovers"
for p in "$PROF" "$WS"; do [ -e "$p" ] && { echo "   LEFTOVER: $p"; LEFT=1; }; done
if pgrep -af "profile $NAME gateway run" >/dev/null 2>&1; then
  echo "   LEFTOVER: gateway process still running for '$NAME'"; LEFT=1
fi
[ -f "$UNIT" ] && { echo "   LEFTOVER: $UNIT"; LEFT=1; }
[ "$LEFT" -eq 0 ] && echo "   clean"

echo "==> 5/5 summary"
if [ "$LEFT" -eq 0 ]; then
  echo "DONE. Bot '$NAME' removed (service, sandbox containers, profile, workspace)."
  echo "      Shared skills, the main profile and any shared image were NOT touched."
else
  echo "WARNING: leftovers remain (see the LEFTOVER lines above)." >&2; exit 1
fi
