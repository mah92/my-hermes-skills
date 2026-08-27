#!/bin/bash
# =============================================================================
# add-bot.sh — add a new containerized Hermes Bale/Telegram bot profile.
# Companion to the hermes-bot-containers skill (Ali Sani, 2026-08).
#
# DESIGN: "path mirror" — inside the container every path matches the host:
#   HOME=/home/oem, HERMES_HOME=/home/oem/.hermes (profile dir mounted there),
#   miniconda/hermes_files/Basir/workspace mounted at their host paths (ro).
# So the MAIN system's .env + config.yaml work VERBATIM after the single
# Bale-token/user substitution — no in-container path rewriting ever needed.
#
# USAGE:
#   ./add-bot.sh <name> --token 123:ABC... --user <OWNER_ID> [--admins <ID1,ID2>]
#     [--compose-file /path/compose.yaml] [--skip-skills] [--no-start]
#   <name>        : profile & container name, lowercase [a-z0-9-]
#   --token       : Bale bot token (unique per bot)
#   --user        : primary Bale user id allowed to chat with this bot
#   --admins      : extra allowed user(s), comma-separated (default: none)
#   --compose-file: compose file to append the service to (default
#                   /home/oem/profiles-containers/docker-compose.yaml)
#   --skip-skills : don't rsync skills (fresh profile gets empty skills dir)
#   --no-start    : prepare everything but don't docker compose up
#   --resume      : rebuild an existing (possibly partial) profile instead of erroring
#   --force       : purge existing profile (dir + workspace + container) and rebuild from scratch
#   DOCKER_PROXY env: route docker image pulls through an HTTP/SOCKS tunnel
#                    (banned-egress remotes), e.g. socks5://127.0.0.1:1080
# =============================================================================
set -euo pipefail

NAME=""
BALE_TOKEN=""
BALE_USER=""
ADMINS=""
COMPOSE_FILE="/home/oem/profiles-containers/docker-compose.yaml"
SKIP_SKILLS=0
NO_START=0
RESUME=0
FORCE=0
# Derived image = official image + passwordless sudo for the in-container
# hermes user (see skill scripts/sudo-image.Dockerfile). Rebuild with:
#   docker build -t nousresearch/hermes-agent-sudo:<TAG> <dir-with-Dockerfile>
IMAGE="nousresearch/hermes-agent-sudo:20260827"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token)      BALE_TOKEN="$2"; shift 2 ;;
    --user)       BALE_USER="$2";  shift 2 ;;
    --admins)     ADMINS="$2";     shift 2 ;;
    --compose-file) COMPOSE_FILE="$2"; shift 2 ;;
    --skip-skills) SKIP_SKILLS=1;  shift ;;
    --no-start)   NO_START=1;      shift ;;
    --resume)     RESUME=1;        shift ;;
    --force)      FORCE=1;          shift ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *)  NAME="$1"; shift ;;
  esac
done

if [[ -z "$NAME" || -z "$BALE_TOKEN" || -z "$BALE_USER" ]]; then
  echo "Usage: $0 <name> --token <TOKEN> --user <USER_ID> [--admins ...] [--compose-file ...] [--skip-skills] [--no-start]" >&2
  exit 1
fi
if ! [[ "$NAME" =~ ^[a-z0-9-]+$ ]]; then echo "Name must be lowercase [a-z0-9-]" >&2; exit 1; fi

HOST_HOME="${HOME:-/home/oem}"
MAIN_HOME="$HOST_HOME/.hermes"
PROFILE_DIR="$MAIN_HOME/profiles/$NAME"
WS_DIR="$HOST_HOME/workspaces/$NAME"
# shellcheck disable=SC2034  # document the mirror invariant (host path = container path)
HOST_MIRROR="$HOST_HOME"
# shellcheck disable=SC2034
IN_WS="$HOST_HOME/workspaces/$NAME"            # same path inside container

if [[ -d "$PROFILE_DIR" ]]; then
  if [[ "$RESUME" -eq 1 ]]; then
    echo "NOTE: profile $NAME already exists — resuming (re-provisioning in place)"
  elif [[ "$FORCE" -eq 1 ]]; then
    echo "NOTE: --force: purging existing profile $NAME (profile dir + workspace + container)"
    rm -rf "$PROFILE_DIR" "$WS_DIR"
    docker rm -f "hermes-$NAME" >/dev/null 2>&1 || true
  else
    echo "ERROR: profile $NAME already exists at $PROFILE_DIR" >&2
    echo "  re-run with --resume (repair) or --force (purge & rebuild from scratch)" >&2
    exit 1
  fi
fi
[[ -d "$MAIN_HOME/skills" ]] || { echo "ERROR: $MAIN_HOME/skills not found" >&2; exit 1; }
[[ -x "$HOST_HOME/.hermes/hermes-agent/venv/bin/python" ]] || { echo "ERROR: host hermes-agent venv python not found ($HOST_HOME/.hermes/hermes-agent/venv/bin/python)" >&2; exit 1; }

echo "==> 1/7 creating profile dirs"
mkdir -p "$PROFILE_DIR" "$WS_DIR"
echo "This workspace belongs to the Hermes bot profile '$NAME' ($([[ -n "$BALE_USER" ]] && echo "Bale user $BALE_USER"))." > "$WS_DIR/README.md"

echo "==> 2/7 .env (copied from main, Bale token/user swapped, secrets stripped)"
cp "$MAIN_HOME/.env" "$PROFILE_DIR/.env"
# escape sed metacharacters in the token (& | \) before substitution
BALE_TOKEN_SED=$(printf '%s' "$BALE_TOKEN" | sed 's/[&|\\]/\\&/g')
BALE_USER_SED=$(printf '%s' "$BALE_USER" | sed 's/[&|\\]/\\&/g')
ADMINS_SED=$(printf '%s' "$ADMINS" | sed 's/[&|\\]/\\&/g')
if [[ -n "$ADMINS" ]]; then ALLOWED_SED="$BALE_USER_SED,$ADMINS_SED"; else ALLOWED_SED="$BALE_USER_SED"; fi
sed -i \
  -e "s|^BALE_BOT_TOKEN=.*|BALE_BOT_TOKEN=$BALE_TOKEN_SED|" \
  -e "s|^BALE_HOME_CHANNEL=.*|BALE_HOME_CHANNEL=$BALE_USER_SED|" \
  -e "s|^BALE_ALLOWED_USERS=.*|BALE_ALLOWED_USERS=$ALLOWED_SED|" \
  -e "s|^BALE_ALLOWED_CHATS=.*|BALE_ALLOWED_CHATS=$ALLOWED_SED|" \
  "$PROFILE_DIR/.env"
# strip admin secrets (keep avalai/deepseek LLM keys + Bale + TTS/STT lines)
for k in SUDO_PASSWORD BROWSERBASE_API_KEY BROWSERBASE_PROJECT_ID BROWSERBASE_PROXIES \
         BROWSERBASE_ADVANCED_STEALTH EXA_API_KEY PARALLEL_API_KEY FAL_KEY \
         FIRECRAWL_API_KEY OPENROUTER_API_KEY VOICE_TOOLS_OPENAI_KEY GROQ_API_KEY \
         ELEVENLABS_API_KEY; do
  sed -i "s|^$k=.*|#$k=|" "$PROFILE_DIR/.env"
done
# shellcheck disable=SC2016
sed -i 's|^HERMES_LOCAL_STT_COMMAND=.*|HERMES_LOCAL_STT_COMMAND='"$HOST_HOME"'/.hermes/hermes-agent/venv/bin/python '"$HOST_HOME"'/.hermes/skills/hermes-persian-stt/scripts/stt.py --quiet|' "$PROFILE_DIR/.env"

echo "==> 3/7 skills + plugins (real copies; models/ re-created as symlinks to the shared store)"
if [[ "$SKIP_SKILLS" -eq 1 ]]; then
  mkdir -p "$PROFILE_DIR/skills"; echo "(--skip-skills: empty skills dir)"
else
  # Copy with -L (dereference ALL symlinks -> every skill becomes a real copy,
  # so host-only links like hermes-persian-tts -> ../../.agents/... never dangle
  # in the container), EXCEPT models/ links which must stay symlinks into the
  # mounted hermes_files store (re-created after the copy).
  cd "$MAIN_HOME/skills"
  mapfile -t MOD_LINKS < <({ find . -type l -name models; for d in */; do d="${d%/}"; [ -L "$d" ] && [ -L "$d/models" ] && echo "./$d/models"; done; } | sort -u)
  EXC=()
  for rel in "${MOD_LINKS[@]}"; do EXC+=(--exclude="${rel#./}"); done
  # dangling symlinks cannot be dereferenced by rsync -L (error 23) - exclude
  # them so a broken leftover link cannot abort the whole skills copy
  while IFS= read -r rel; do EXC+=(--exclude="${rel#./}"); done < <(find . -xtype l 2>/dev/null | sort -u)
  rsync -aL --delete "${EXC[@]}" "$MAIN_HOME/skills/" "$PROFILE_DIR/skills/"
  for rel in "${MOD_LINKS[@]}"; do
    mkdir -p "$PROFILE_DIR/skills/$(dirname "$rel")"
    ln -s "$(readlink -f "$rel")" "$PROFILE_DIR/skills/${rel#./}"
  done
  echo "  skills copied ($(find "$PROFILE_DIR/skills" -mindepth 1 -maxdepth 1 | wc -l) entries)"
fi
# Plugins (e.g. the Bale platform adapter) are profile-local. Without them the
# gateway CANNOT start the platform even when config lists it. Copy ALWAYS
# (even with --skip-skills), excluding embedded .git metadata.
mkdir -p "$PROFILE_DIR/plugins"
rsync -a --exclude='.git/' "$MAIN_HOME/plugins/" "$PROFILE_DIR/plugins/"
echo "  plugins copied ($(find "$PROFILE_DIR/plugins" -mindepth 1 | wc -l) entries)"

echo "==> 4/7 config.yaml (path-mirror design — TTS/STT commands stay VERBATIM)"
mkdir -p "$PROFILE_DIR/mcp/comfy-flux" "$PROFILE_DIR/venv-ai"
if [[ -f "$MAIN_HOME/mcp/comfy-flux/server.py" ]]; then
  cp "$MAIN_HOME/mcp/comfy-flux/server.py" "$PROFILE_DIR/mcp/comfy-flux/server.py"
fi
ln -sfn "$HOST_HOME/hermes_files/sherpa-onnx-en-stt" "$PROFILE_DIR/models"
python3 - "$NAME" "$PROFILE_DIR" "$HOST_HOME" "$BALE_USER" "$ADMINS" <<'PY'
import sys, yaml
name, prof, hh, bale_user, admins = sys.argv[1:6]
cf = f"{prof}/config.yaml"

# start from the MAIN config as the base (identical model/provider/sections)
base = f"{hh}/.hermes/config.yaml"
cfg = yaml.safe_load(open(base))

# --- model: shared avalai custom provider (already in base) ---

# --- platforms: keep only bale, disable api_server ---
cfg["platforms"] = {"api_server": {"enabled": False}}

# --- platform toolsets: bale gets the proven 15-tool list (no cronjob) ---
cfg.setdefault("platform_toolsets", {})["bale"] = [
    "browser", "clarify", "code_execution", "computer_use", "delegation",
    "file", "image_gen", "memory", "session_search", "skills", "terminal",
    "todo", "tts", "vision", "web",
]

# --- plugins: only platforms/bale ---
cfg["plugins"] = {
    "disabled": [],
    "enabled": ["platforms/bale"],
    "entries": {"platforms/bale": {"allow_tool_override": False}},
    "hermes-memory-store": {"auto_extract": "true",
                            "db_path": f"{hh}/.hermes/memory_store.db",
                            "default_trust": "0.4", "hrr_dim": "1024"},
}

# --- TTS/STT providers: VERBATIM main-style commands (paths now mirror host) ---
if "tts" in cfg and "providers" in cfg["tts"] and "matcha" in cfg["tts"]["providers"]:
    cfg["tts"]["provider"] = "matcha"
    cfg["tts"]["providers"]["matcha"]["command"] = (
        f"python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.5 "
        f"{{input_path}} {{output_path}}"
    )
if "stt" in cfg and "providers" in cfg["stt"] and "shenava" in cfg["stt"]["providers"]:
    cfg["stt"]["provider"] = "shenava"
    cfg["stt"]["providers"]["shenava"]["command"] = (
        f"{hh}/.hermes/hermes-agent/venv/bin/python "
        f"{hh}/.hermes/skills/hermes-persian-stt/scripts/stt.py --quiet {{input_path}}"
    )

# --- MCP comfy-flux: in-container venv + server copy inside the profile ---
mcp = cfg.setdefault("mcp_servers", {}).get("comfy-flux")
if mcp:
    mcp["command"] = f"{hh}/.hermes/venv-ai/bin/python"
    mcp["args"][0] = f"{hh}/.hermes/mcp/comfy-flux/server.py"

# --- terminal cwd: workspace (host-identical path) ---
cfg.setdefault("terminal", {})["cwd"] = f"{hh}/workspaces/{name}"

# --- memory store db — same absolute path inside/outside container ---
cfg.setdefault("plugins", {})["hermes-memory-store"]["db_path"] = f"{hh}/.hermes/memory_store.db"

# --- session_reset (harmless in container) ---
cfg["session_reset"] = {"at_hour": 4, "idle_minutes": 1440, "mode": "none"}

yaml.safe_dump(cfg, open(cf, "w"), allow_unicode=True, sort_keys=False)
print(f"  wrote {cf}")
PY

echo "==> 5/7 compose service block (path-mirror mounts — profile at /home/oem/.hermes)"
python3 - "$NAME" "$COMPOSE_FILE" "$PROFILE_DIR" "$WS_DIR" "$HOST_HOME" <<'PY'
import sys, os, yaml
name, cf, prof_dir, ws_dir, hh = sys.argv[1:6]
# the compose dir may not exist on this host (e.g. remote VPS) - create it
os.makedirs(os.path.dirname(cf), exist_ok=True)
doc = yaml.safe_load(open(cf)) if (os.path.exists(cf) and open(cf).read().strip()) else {"services": {}}
doc.setdefault("services", {})
if name in doc["services"]:
    print(f"  service {name} already in {cf} — skipping compose append"); sys.exit(0)
IM = "nousresearch/hermes-agent-sudo:20260827"
doc["services"][name] = {
    "image": IM,
    "container_name": f"hermes-{name}",
    "restart": "unless-stopped",
    "network_mode": "host",
    "working_dir": f"/home/oem/workspaces/{name}",
    "environment": [
        f"PUID=1000", f"PGID=1000", f"HERMES_UID=1000", f"HERMES_GID=1000",
        f"HOME={hh}", f"HERMES_HOME={hh}/.hermes",
        f"HERMES_WRITE_SAFE_ROOT={hh}",
        f"HERMES_LAZY_INSTALL_TARGET={hh}/.hermes/lazy-packages",
        "API_SERVER_ENABLED=false",
        "LD_LIBRARY_PATH=/home/oem/hermes_files/tts-libs",
    ],
    "volumes": [
        f"{prof_dir}:/home/oem/.hermes",
        f"{hh}/hermes_files:/home/oem/hermes_files:ro",
        f"{hh}/.hermes/hermes-agent/venv:/home/oem/.hermes/hermes-agent/venv:ro",
        f"{hh}/.local/share/uv:/home/oem/.local/share/uv:ro",
        f"{hh}/Basir:/home/oem/Basir:ro",
        "/usr/lib/locale:/usr/lib/locale:ro",
        "/usr/share/i18n:/usr/share/i18n:ro",
        f"{ws_dir}:/home/oem/workspaces/{name}",
    ],
    "command": ["gateway", "run"],
    "mem_limit": "4g",
}
yaml.safe_dump(doc, open(cf, "w"), allow_unicode=True, sort_keys=False)
print(f"  appended service '{name}' to {cf}")
PY

# If the host can only reach Docker Hub through a tunnel (banned-egress remotes),
# export DOCKER_PROXY (e.g. socks5://127.0.0.1:1080) to configure the daemon once.
if [[ -n "${DOCKER_PROXY:-}" ]]; then
  DROP=/etc/systemd/system/docker.service.d/http-proxy.conf
  if ! sudo grep -q "$DOCKER_PROXY" "$DROP" 2>/dev/null; then
    echo "==> 5b/7 configuring docker daemon proxy ($DOCKER_PROXY)"
    sudo mkdir -p "$(dirname "$DROP")"
    printf '[Service]\nEnvironment="HTTP_PROXY=%s"\nEnvironment="HTTPS_PROXY=%s"\nEnvironment="NO_PROXY=localhost,127.0.0.1,192.168.0.0/16,10.0.0.0/8"\n' \
      "$DOCKER_PROXY" "$DOCKER_PROXY" | sudo tee "$DROP" >/dev/null
    sudo systemctl daemon-reload
    echo "  restarting docker daemon (containers with restart policies return automatically)..."
    sudo systemctl restart docker
    sleep 5
  fi
fi

echo "==> 6/7 starting container"
if [[ "$NO_START" -eq 1 ]]; then
  echo "  (--no-start: done)"
else
  docker compose -f "$COMPOSE_FILE" up -d
  echo "  waiting for gateway (s6 boot ~20-40s)..."
  for i in $(seq 1 24); do
    sleep 5
    if grep -qE "Connected as|gateway is now running" "$PROFILE_DIR/logs/agent.log" 2>/dev/null; then break; fi
  done
  if grep -q "Connected as" "$PROFILE_DIR/logs/agent.log" 2>/dev/null; then
    echo "  BALE: $(grep 'Connected as' "$PROFILE_DIR/logs/agent.log" | tail -1 | sed 's/.*INFO //')"
  else
    echo "  WARNING: gateway running but not yet 'Connected as' — check $PROFILE_DIR/logs/agent.log" >&2
  fi
fi

echo "==> 7/7 optional in-container venv (MCP comfy-flux needs mcp<2)"
if [[ "$NO_START" -eq 0 ]]; then
  docker exec -u hermes "hermes-$NAME" bash -lc '
    python3 -m venv /home/oem/.hermes/venv-ai 2>/dev/null || true
    /home/oem/.hermes/venv-ai/bin/pip install --quiet "mcp<2" 2>/dev/null || true
    echo "  venv-ai: $(test -x /home/oem/.hermes/venv-ai/bin/python && echo ok || echo skip)"' 2>/dev/null || true
fi

echo
echo "DONE. Profile: $PROFILE_DIR | Workspace: $WS_DIR"
echo "Bale user $BALE_USER${ADMINS:+ (+$ADMINS)} can now chat with the bot."
echo "Quick voice check:"
echo "  docker exec -u hermes hermes-$NAME bash -lc 'echo سلام > /tmp/x.txt && python3 ~/.hermes/skills/hermes-persian-tts/scripts/tts.py --speed 1.0 /tmp/x.txt /tmp/x.ogg'"
