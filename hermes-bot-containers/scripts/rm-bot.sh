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

echo "==> 2/3 removing profile + workspace"
rm -rf "/home/oem/.hermes/profiles/$NAME" "/home/oem/workspaces/$NAME"
echo "  removed ~/.hermes/profiles/$NAME and ~/workspaces/$NAME"

echo "==> 3/3 removing compose service"
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

echo
echo "DONE. Bot '$NAME' fully removed."
