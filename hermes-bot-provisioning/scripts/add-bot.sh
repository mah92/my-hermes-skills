#!/bin/bash
# add-bot.sh — provision one bot (Bale or Soroush Plus) on a Hermes host.
#
# One profile per bot, gateway as a systemd USER service, optional Hermes-free
# docker sandbox for the profile's commands. No host-specific values inside:
# everything derives from $HOME and the flags you pass.
#
# Usage:
#   add-bot.sh <name> --platform bale|soroush --token <TOKEN> --user <USER_ID>
#              [--admins <ID1,ID2>] [--home <CHAT_ID>] [--skip-skills]
#              [--no-start] [--sandbox-image <IMAGE>:<TAG>]
#   Token/user may also come from the environment: BOT_TOKEN=... BOT_USER_ID=...
#
# Rollback / removal: rm-bot.sh <name>
set -euo pipefail

# Resolve our own directory ONCE, before any cd: later relative "$(dirname $0)"
# lookups break the moment the cwd changes.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

NAME=""; PLATFORM=""; TOKEN="${BOT_TOKEN:-}"; USER_ID="${BOT_USER_ID:-}"
ADMINS=""; HOME_CHAT=""; SKIP_SKILLS=0; NO_START=0; SANDBOX_IMAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)      PLATFORM="$2"; shift 2 ;;
    --token)         TOKEN="$2"; shift 2 ;;
    --user)          USER_ID="$2"; shift 2 ;;
    --admins)        ADMINS="$2"; shift 2 ;;
    --home)          HOME_CHAT="$2"; shift 2 ;;
    --skip-skills)   SKIP_SKILLS=1; shift ;;
    --no-start)      NO_START=1; shift ;;
    --sandbox-image) SANDBOX_IMAGE="$2"; shift 2 ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *)  NAME="$1"; shift ;;
  esac
done

usage() { sed -n '8,18p' "$0" | sed 's/^# \{0,1\}//'; }
[[ -n "$NAME" && -n "$PLATFORM" && -n "$TOKEN" && -n "$USER_ID" ]] || { usage; exit 2; }
case "$PLATFORM" in bale|soroush) ;; *) echo "--platform must be bale or soroush" >&2; exit 2 ;; esac
[[ "$NAME" =~ ^[a-z0-9-]+$ ]] || { echo "Name must be lowercase [a-z0-9-]" >&2; exit 2; }

H="${HOME:?HOME is not set}"
MAIN="$H/.hermes"
PROF="$MAIN/profiles/$NAME"
WS="$H/workspaces/$NAME"
HV="$MAIN/hermes-agent/venv/bin/python"
HERMES="$MAIN/hermes-agent/venv/bin/hermes"
PLAT_UC="$(echo "$PLATFORM" | tr '[:lower:]' '[:upper:]')"

[[ -x "$HV" ]] || { echo "ERROR: no host hermes venv at $HV" >&2; exit 1; }
[[ -x "$HERMES" ]] || { echo "ERROR: no hermes CLI at $HERMES" >&2; exit 1; }
[[ -d "$PROF" ]] && { echo "ERROR: profile $NAME already exists ($PROF) — remove it first: $SCRIPT_DIR/rm-bot.sh $NAME" >&2; exit 1; }
[[ -d "$MAIN/plugins/platforms/$PLATFORM" ]] || echo "WARNING: $MAIN/plugins/platforms/$PLATFORM not found — install the adapter plugin first, or the bot will never connect" >&2
if [[ -n "$SANDBOX_IMAGE" ]] && ! docker image inspect "$SANDBOX_IMAGE" >/dev/null 2>&1; then
  echo "ERROR: sandbox image '$SANDBOX_IMAGE' not found locally (build it first, or drop --sandbox-image)" >&2; exit 1
fi

if ! loginctl show-user "$(id -un)" 2>/dev/null | grep -q 'Linger=yes'; then
  echo "==> enabling user lingering (a user-unit gateway must survive logout)"
  sudo -n loginctl enable-linger "$(id -un)" 2>/dev/null \
    || echo "  WARNING: enable it manually: sudo loginctl enable-linger $(id -un)" >&2
fi

echo "==> 1/6 profile + workspace"
mkdir -p "$PROF" "$WS"
printf 'Workspace for the Hermes bot profile %s (%s bot).\n' "$NAME" "$PLATFORM" > "$WS/README.md"

echo "==> 2/6 .env for this bot"
cp "$MAIN/.env" "$PROF/.env"
"$HV" - "$PROF/.env" "$PLAT_UC" "$TOKEN" "$USER_ID" "$ADMINS" "$HOME_CHAT" <<'PY'
import sys
path, plat, token, user, admins, home = sys.argv[1:7]
allowed = ",".join(x for x in ([user] + ([admins] if admins else [])) if x)
lines = open(path, encoding="utf-8", errors="surrogateescape").read().split("\n")
out, seen = [], set()
for ln in lines:
    key = ln.split("=", 1)[0].strip() if "=" in ln else ""
    # 1) neutralise every OTHER platform's bot token: a second poller on the same
    #    token makes BOTH bots lose messages.
    if key.endswith("_BOT_TOKEN") and key != f"{plat}_BOT_TOKEN":
        out.append(f"#{ln}"); continue
    if key == f"{plat}_BOT_TOKEN":
        out.append(f"{plat}_BOT_TOKEN={token}"); seen.add(key); continue
    # 2) allowlists + deny-by-default for the chosen platform
    if key in (f"{plat}_ALLOWED_USERS", f"{plat}_ALLOWED_CHATS"):
        out.append(f"{key}={allowed}"); seen.add(key); continue
    if key == f"{plat}_ALLOW_ALL_USERS":
        out.append(f"{plat}_ALLOW_ALL_USERS=false"); seen.add(key); continue
    if key == f"{plat}_HOME_CHANNEL":
        out.append(f"{plat}_HOME_CHANNEL={home or user}"); seen.add(key); continue
    # 3) the gateway-level allow-all switch must never be on for a bot that other
    #    people can message
    if key == "GATEWAY_ALLOW_ALL_USERS":
        out.append("GATEWAY_ALLOW_ALL_USERS=false"); seen.add(key); continue
    # 4) host-only admin secrets. Shared LLM keys are deliberately KEPT: every
    #    profile runs on the host's model credentials (documented in SKILL.md).
    if key in {"SUDO_PASSWORD", "BROWSERBASE_API_KEY", "BROWSERBASE_PROJECT_ID",
               "EXA_API_KEY", "PARALLEL_API_KEY", "FAL_KEY", "FIRECRAWL_API_KEY",
               "OPENROUTER_API_KEY", "VOICE_TOOLS_OPENAI_KEY", "GROQ_API_KEY",
               "ELEVENLABS_API_KEY"}:
        out.append(f"#{ln}"); continue
    out.append(ln)
for key, val in ((f"{plat}_BOT_TOKEN", token), (f"{plat}_ALLOWED_USERS", allowed),
                 (f"{plat}_ALLOWED_CHATS", allowed), (f"{plat}_ALLOW_ALL_USERS", "false"),
                 (f"{plat}_HOME_CHANNEL", home or user),
                 ("GATEWAY_ALLOW_ALL_USERS", "false")):
    if key not in seen:
        out.append(f"{key}={val}")
open(path, "w", encoding="utf-8", errors="surrogateescape").write("\n".join(out))
PY
# host interpreter for anything the profile shells out to
sed -i "s|^PYTHON_BIN=.*|PYTHON_BIN=$HV|" "$PROF/.env"
grep -q '^PYTHON_BIN=' "$PROF/.env" || echo "PYTHON_BIN=$HV" >> "$PROF/.env"

# Assert the .env rules the skill promises, instead of trusting the writer above.
if grep -qE '^SUDO_PASSWORD=' "$PROF/.env"; then
  echo "ERROR: SUDO_PASSWORD leaked into $PROF/.env" >&2; exit 1
fi
if grep -E '^[A-Z0-9]+_BOT_TOKEN=' "$PROF/.env" | grep -qv "^${PLAT_UC}_BOT_TOKEN="; then
  echo "ERROR: a foreign bot token is active in $PROF/.env (double-poller risk):" >&2
  grep -E '^[A-Z0-9]+_BOT_TOKEN=' "$PROF/.env" | grep -v "^${PLAT_UC}_BOT_TOKEN=" | cut -d= -f1 >&2
  exit 1
fi
echo "   .env: ${PLAT_UC}_* set, other platform tokens neutralised, AllowAll=false, secrets stripped"

echo "==> 3/6 skills + plugins (profile-local copies)"
if [[ "$SKIP_SKILLS" -eq 1 ]]; then
  mkdir -p "$PROF/skills"; echo "   (--skip-skills)"
else
  # no cd: every path below is absolute, so $(dirname $0) stays valid later
  mapfile -t MOD_LINKS < <(find "$MAIN/skills" -type l -name models 2>/dev/null | sed "s|^$MAIN/skills/||" | sort -u)
  EXC=()
  for rel in "${MOD_LINKS[@]}"; do EXC+=(--exclude="$rel"); done
  while IFS= read -r rel; do EXC+=(--exclude="$rel"); done < <(find "$MAIN/skills" -xtype l 2>/dev/null | sed "s|^$MAIN/skills/||" | sort -u)
  rsync -aL --delete "${EXC[@]}" "$MAIN/skills/" "$PROF/skills/"
  for rel in "${MOD_LINKS[@]}"; do
    mkdir -p "$PROF/skills/$(dirname "$rel")"
    ln -s "$(readlink -f "$MAIN/skills/$rel")" "$PROF/skills/$rel"
  done
  echo "   skills: $(find "$PROF/skills" -mindepth 1 -maxdepth 1 | wc -l) entries"
fi
mkdir -p "$PROF/plugins"
rsync -a --exclude='.git/' "$MAIN/plugins/" "$PROF/plugins/"
echo "   plugins: $(find "$PROF/plugins" -mindepth 1 | wc -l) entries"

echo "==> 4/6 config.yaml"
"$HV" - "$NAME" "$PLATFORM" "$PROF" "$H" "$SANDBOX_IMAGE" "$USER_ID" <<'PY'
import os, sys, yaml
name, plat, prof, h, sandbox_image, user_id = sys.argv[1:7]
main_cfg = os.path.join(h, ".hermes", "config.yaml")
cfg = yaml.safe_load(open(main_cfg, encoding="utf-8")) if os.path.isfile(main_cfg) else {}
other = "soroush" if plat == "bale" else "bale"
cfg["platforms"] = {
    "api_server": {"enabled": False},
    plat: {"enabled": True, "home_channel": {"platform": plat, "chat_id": str(user_id), "user_id": str(user_id)}},
    other: {"enabled": False},
}
cfg.setdefault("platform_toolsets", {})[plat] = [
    "browser", "clarify", "code_execution", "file", "image_gen", "memory",
    "session_search", "skills", "terminal", "todo", "tts", "vision", "web",
]
cfg["plugins"] = {"disabled": [], "enabled": [f"platforms/{plat}"],
                  "entries": {f"platforms/{plat}": {"allow_tool_override": False}}}
cfg["session_reset"] = {"at_hour": 4, "idle_minutes": 1440, "mode": "none"}
term = cfg.setdefault("terminal", {})
term.update({"cwd": os.path.join(h, "workspaces", name), "timeout": 180, "home_mode": "auto"})
if sandbox_image:
    term.update({
        "backend": "docker", "docker_image": sandbox_image,
        "docker_run_as_host_user": True, "docker_mount_cwd_to_workspace": True,
        "container_cpu": 1, "container_memory": 2048, "container_disk": 0,
        "container_persistent": False, "lifetime_seconds": 300,
        # mount the profile's OWN skills (never the shared main tree) so a bot
        # cannot read other profiles' material
        "docker_volumes": [f"{h}/workspaces/{name}:{h}/workspaces/{name}",
                           f"{h}/.hermes/profiles/{name}:{h}/.hermes/profiles/{name}:ro",
                           f"{h}/.hermes/profiles/{name}/skills:{h}/.hermes/skills:ro"],
    })
else:
    term.update({"backend": "local"})
yaml.safe_dump(cfg, open(os.path.join(prof, "config.yaml"), "w"), allow_unicode=True, sort_keys=False)
print(f"   wrote config.yaml (platform={plat}, terminal.backend={term.get('backend')})")
PY

echo "==> 5/6 gateway service"
if [[ "$NO_START" -eq 1 ]]; then
  echo "   (--no-start) install later: $HERMES -p $NAME gateway install"
else
  "$HERMES" -p "$NAME" gateway install 2>&1 | tail -2
  echo "   waiting for the platform to connect (up to 90s)..."
  for _ in $(seq 1 18); do sleep 5; grep -qa 'Connected as' "$PROF/logs/agent.log" 2>/dev/null && break; done
  grep -qa 'Connected as' "$PROF/logs/agent.log" 2>/dev/null \
    && echo "   CONNECTED: $(grep -a 'Connected as' "$PROF/logs/agent.log" | tail -1 | cut -c1-90)" \
    || echo "   WARNING: no 'Connected as' yet — check $PROF/logs/agent.log" >&2
fi

echo
echo "DONE. profile=$PROF workspace=$WS"
echo "  remove: $SCRIPT_DIR/rm-bot.sh $NAME"
echo
echo "==> 6/6 verification"
if ! bash "$SCRIPT_DIR/verify-bot.sh" "$NAME"; then
  echo
  echo "WARNING: verification reported failures for '$NAME' — the profile was created, but fix it before relying on the bot." >&2
  if [[ "$NO_START" -ne 1 ]]; then
    exit 1
  fi
  echo "NOTE: --no-start, so the service/platform FAILs above are expected until you run:"
  echo "      $HERMES -p $NAME gateway install"
fi
