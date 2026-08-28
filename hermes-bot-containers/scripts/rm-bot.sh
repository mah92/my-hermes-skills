#!/bin/bash
# rm-bot.sh <name> — remove a containerized bot created by add-bot.sh.
# Deletes: container, profile dir, workspace, and its compose service block.
# Companion to the hermes-bot-containers skill.
set -euo pipefail

NAME="${1:?usage: rm-bot.sh <name>}"
COMPOSE_FILE="${COMPOSE_FILE:-/home/oem/profiles-containers/docker-compose.yaml}"
[[ "$NAME" =~ ^[a-z0-9-]+$ ]] || { echo "Name must be lowercase [a-z0-9-]" >&2; exit 1; }

echo "==> 1/3 removing container hermes-$NAME"
docker rm -f "hermes-$NAME" >/dev/null 2>&1 && echo "  container removed" || echo "  no running container"

echo "==> 2/3 removing compose service (deterministic — do this before anything can abort)"
if [[ -f "$COMPOSE_FILE" ]]; then
  python3 - "$NAME" "$COMPOSE_FILE" <<'PY'
import sys, yaml, os
name, cf = sys.argv[1:3]
doc = yaml.safe_load(open(cf)) if os.path.exists(cf) else {}
if doc and "services" in doc and name in doc["services"]:
    del doc["services"][name]
    if not doc.get("services"):
        doc.pop("services", None)
    yaml.safe_dump(doc, open(cf, "w"), allow_unicode=True, sort_keys=False)
    print(f"  removed service '{name}' from {cf}")
else:
    print(f"  no service '{name}' in {cf}")
PY
else
  echo "  compose file not found ($COMPOSE_FILE) — skipped"
fi

echo "==> 3/3 removing profile + workspace"
# The container's first boot (as root, before dropping to the hermes user)
# leaves ROOT-OWNED dirs in the profile (e.g. hermes-agent/venv -> observed on
# Ali's box 2026-08). Plain rm fails there and with `set -e` it aborted the
# whole script, leaving the compose service behind. Escalation ladder:
#   plain rm -> sudo -n (NOPASSWD) -> SUDO_PASSWORD from main .env -> manual.
remove_tree() {
  local p
  for p in "$@"; do
    if [ -e "$p" ] || [ -L "$p" ]; then
      if rm -rf "$p" 2>/dev/null; then
        echo "  removed $p"
      elif sudo -n rm -rf "$p" 2>/dev/null; then
        echo "  removed $p (passwordless sudo)"
      elif [ -n "${SUDO_PASSWORD:-}" ]; then
        echo "  removed $p (sudo -S)"
        echo "$SUDO_PASSWORD" | sudo -S -p "" rm -rf "$p"
      else
        echo "  CANNOT REMOVE $p (root-owned) — run manually: sudo rm -rf $p" >&2
        LEFT=1
      fi
    else
      echo "  already gone: $p"
    fi
  done
}
# SUDO_PASSWORD is stripped from bot envs but lives in the MAIN .env — read it
# directly. NEVER `source` the whole .env under set -e: its command
# substitutions execute and can fail (e.g. stt.py on a ro path -> 126 abort).
if [ -n "${SUDO_PASSWORD:-}" ]; then :; else
  SUDO_PASSWORD="$(grep -m1 '^SUDO_PASSWORD=' /home/oem/.hermes/.env 2>/dev/null | cut -d= -f2-)" || true
fi
LEFT=0
remove_tree "/home/oem/.hermes/profiles/$NAME" "/home/oem/workspaces/$NAME"
for p in "/home/oem/.hermes/profiles/$NAME" "/home/oem/workspaces/$NAME"; do
  if [ -e "$p" ] || [ -L "$p" ]; then echo "  LEFTOVER: $p"; LEFT=1; fi
done
if python3 - "$NAME" "$COMPOSE_FILE" <<'PY' | grep -q '^yes$'
import sys, yaml, os
name, cf = sys.argv[1:3]
try:
    doc = yaml.safe_load(open(cf)) if os.path.exists(cf) else {}
except Exception:
    doc = {}
print("yes" if doc and "services" in doc and name in doc["services"] else "no")
PY
then
  echo "  LEFTOVER: service '$NAME' still in $COMPOSE_FILE"; LEFT=1
else
  echo "  compose service gone"
fi
[ "$LEFT" -eq 0 ] && echo "  all clean"

echo
if [ "$LEFT" -eq 0 ]; then
  echo "DONE. Bot '$NAME' fully removed."
else
  echo "WARNING: leftovers remain — inspect the LEFTOVER lines above." >&2
  exit 1
fi
