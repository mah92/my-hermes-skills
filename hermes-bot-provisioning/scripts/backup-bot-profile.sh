#!/bin/bash
# backup-bot-profile.sh <name> [backup_root] — WAL-safe backup of one bot profile,
# to run BEFORE any migration, image change or removal.
#
# Live SQLite is never raw-copied: the gateway writes continuously, and a plain
# `cp` of a WAL database yields a torn snapshot. Uses the sqlite3 backup API,
# then verifies each snapshot with PRAGMA integrity_check.
#
# Output: <backup_root>/pre-migration-<ts>/{<name>-<db>,<name>-profile-config.tgz,<name>-workspace.tgz}
# Disk guard: check `df -h <backup_root>` first — a big workspace triples the size.
set -euo pipefail
NAME="${1:?usage: backup-bot-profile.sh <name> [backup_root]}"
H="${HOME:?HOME is not set}"
ROOT="${2:-$H/backups}"
TS=$(date +%Y%m%d_%H%M%S)
BK="$ROOT/pre-migration-$TS"
PROFILE="$H/.hermes/profiles/$NAME"
HV="$H/.hermes/hermes-agent/venv/bin/python"
[ -d "$PROFILE" ] || { echo "ERROR: no profile at $PROFILE" >&2; exit 1; }
[[ -x "$HV" ]] || { echo "ERROR: no host hermes venv python at $HV" >&2; exit 1; }
mkdir -p "$BK"
echo "backup dir: $BK"

# 1) live SQLite DBs, via the sqlite3 backup API (WAL-safe)
"$HV" - "$BK" "$PROFILE" <<'PY'
import os, sqlite3, sys
bk, profile = sys.argv[1], sys.argv[2]
for dbname in ("state.db", "memory_store.db", "kanban.db", "projects.db", "verification_evidence.db"):
    src = os.path.join(profile, dbname)
    if not os.path.exists(src):
        print("  skip (absent):", dbname); continue
    dst = os.path.join(bk, f"{os.path.basename(profile)}-{dbname}")
    try:
        s = sqlite3.connect(f"file:{src}?mode=ro", uri=True); d = sqlite3.connect(dst)
        s.backup(d); d.close(); s.close()
        chk = sqlite3.connect(dst); ok = chk.execute("PRAGMA integrity_check").fetchone()[0]; chk.close()
        print(f"  {dbname}: {os.path.getsize(dst)} bytes, integrity={ok}")
    except Exception as e:
        print(f"  FAIL {dbname}: {e}")
PY

# 2) profile config and secrets (no caches/logs)
tar czf "$BK/$(basename "$PROFILE")-profile-config.tgz" \
  -C "$H/.hermes/profiles" "$NAME/.env" "$NAME/config.yaml" "$NAME/SOUL.md" \
  "$NAME/channel_directory.json" "$NAME/gateway_state.json" 2>/dev/null \
  && echo "  profile config archived (contains the bot's .env — keep it private)"

# 3) workspace
if [ -d "$H/workspaces/$NAME" ]; then
  tar czf "$BK/$(basename "$PROFILE")-workspace.tgz" -C "$H/workspaces" "$NAME" 2>/dev/null \
    && echo "  workspace archived: $(du -h "$BK/$(basename "$PROFILE")-workspace.tgz" | cut -f1)"
else
  echo "  no workspace for $NAME (skipped)"
fi

echo "contents:"; ls -lh "$BK"
echo "restore: stop the gateway, put the DBs back (sqlite3 .restore or the python backup API), untar the config/workspace, start again."
