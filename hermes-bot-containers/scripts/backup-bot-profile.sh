#!/usr/bin/env bash
# backup-bot-profile.sh <name> — WAL-safe backup of one bot profile before any
# migration/recreate/overwrite. Verified 2026-08-30 on a live fleet container.
#
# Usage: bash backup-bot-profile.sh <name> [backup_root]
# Output: <backup_root>/pre-migration-<ts>/  (default root: <HOME>/backups)
# Disk guard: profiles can be 100M+ (state.db ~230M on heavy bots) — check
# `df -h <backup_root>` first; keep >=20G free on the target filesystem.
set -u
NAME="${1:?usage: backup-bot-profile.sh <bot-name> [backup_root]}"
ROOT="${2:-${HOME:-/home/oem}/backups}"
TS=$(date +%Y%m%d_%H%M%S)
BK="$ROOT/pre-migration-$TS"
PROFILE="${HOME:-/home/oem}/.hermes/profiles/$NAME"
mkdir -p "$BK"
echo "backup dir: $BK"

# 1) Live SQLite DBs via the python sqlite3 backup API (WAL-safe) — NEVER raw cp
#    (gateway writes continuously; a plain cp yields a torn snapshot).
"${HOME:-/home/oem}/.hermes/hermes-agent/venv/bin/python" - "$BK" "$PROFILE" <<'PY'
import sqlite3, sys, os
bk, profile = sys.argv[1], sys.argv[2]
for dbname in ('state.db', 'memory_store.db', 'kanban.db', 'projects.db', 'verification_evidence.db'):
    src = os.path.join(profile, dbname)
    if not os.path.exists(src):
        print("skip (absent):", dbname); continue
    dst = os.path.join(bk, os.path.basename(profile) + '-' + dbname)
    try:
        s = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
        d = sqlite3.connect(dst)
        s.backup(d)
        d.close(); s.close()
        chk = sqlite3.connect(dst)
        ok = chk.execute('PRAGMA integrity_check').fetchone()[0]
        chk.close()
        print(f"backed up: {dbname} -> {os.path.getsize(dst)} bytes, integrity={ok}")
    except Exception as e:
        print(f"FAIL {dbname}: {e}")
PY

# 2) profile dotfiles & config (no live DBs, no cache/logs)
tar czf "$BK/$(basename "$PROFILE")-profile-config.tgz" \
  -C "${HOME:-/home/oem}/.hermes/profiles" "$NAME/.env" "$NAME/config.yaml" \
  "$NAME/SOUL.md" "$NAME/channel_directory.json" "$NAME/gateway_state.json" 2>/dev/null \
  && echo "profile config backed up"

# 3) workspace (rw mount — user files)
if [ -d "${HOME:-/home/oem}/workspaces/$NAME" ]; then
  tar czf "$BK/$(basename "$PROFILE")-workspace.tgz" -C "${HOME:-/home/oem}/workspaces" "$NAME" 2>/dev/null \
    && echo "workspace backed up: $(du -h "$BK/$(basename "$PROFILE")-workspace.tgz" | cut -f1)"
fi

echo "=== backup contents ==="
ls -lh "$BK"
echo "NOTE: restore = sqlite3 .restore / python src.backup back; tar -xzf per file set."
