---
name: hermes-bot-containers
description: "Hermes bot fleet: isolated container bots, image builds, migrations, sync, ops."
version: 3.1.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, docker, containers, bale, profiles, isolation, fleet, migration, tts, stt]
    related_skills: [gateway-restart, hermes-selfhost-firecrawl-skill]
---

# Hermes Bot Fleet (containers + ops)

Umbrella skill: provisioning, maintaining, and operating a fleet of isolated
Hermes bot containers (`hermes-<name>`) alongside a host main agent. Merged
from the former `hermes-bot-fleet-ops` (sync/allowlist/restart/migration) and
`hermes-bot-containers` (provisioning/voice/image). Parametric — replace
`<name>`, `<OWNER_ID>`, `<HERMES_HOME>`, `<COMPOSE_DIR>` with your values; no
personally-identifying configuration is stored here.

## When to use
- Provision a new isolated bot profile/container for another person.
- Recreate/repair/extend a bot container after config, mount, or image changes.
- Mirror the main agent's workspace/memory/sessions/packages into bot profiles.
- Enforce allowlist/security flags fleet-wide.
- Rebuild the fleet image, migrate containers across image tags safely.
- Diagnose broken voice (STT/TTS), suspicious approval prompts, or web backend
  failures inside containers.
- Restart the main gateway or a bot to apply `.env`/config changes.

## Proven environment facts (this class of setup, 2026-08)
- Main gateway runs under **s6 supervision** (`s6-supervise gateway-default`,
  `.../venv/bin/hermes gateway run --replace`, logs via s6-log) even when a
  systemd unit file exists — `systemctl` is NOT the active supervisor.
  Restart = `kill-gateway.py`; s6 auto-restarts. Bots restart with
  `docker restart hermes-<name>` (reloads `.env`).
- Host python is usually NEWER-OLD: host 3.11 vs image 3.13 → venvs are
  ABI-specific per context. Never reuse a host-built venv in a container.
- `.env` at `<HERMES_HOME>/profiles/<name>/.env` IS the container's env
  (mount). Never overwrite it with the main `.env` — every bot has a UNIQUE
  platform token.
- Container pip: python is `/opt/hermes/.venv/bin/python3` (image ABI) — see
  "In-container pip" below.

## Design: path mirroring (the whole point)
Each container is a **mirror of the host filesystem layout**: every path the
main system uses resolves to the same string inside the container, so a copied
`.env` and `config.yaml` work **verbatim** — TTS/STT commands, model paths,
everything — with no path rewriting:

- `HOME=<HOST_USER_HOME>` and `HERMES_HOME=<HOST_USER_HOME>/.hermes`
  (overrides the image default `/opt/data`)
- Profile dir mounted AT `<HOST_USER_HOME>/.hermes` (host:
  `<HERMES_HOME>/profiles/<name>`)
- Shared ro mounts at their host paths: `<HERMES_HOME>/hermes_files`,
  `<HOST_USER_HOME>/.local/share/uv`. The host hermes-agent venv mount is
  **TWO-MODE, auto-detected in add-bot.sh from the image tag**:
  - **Plain image** (e.g. `:20260827`, deps NOT baked):
    mount `<HERMES_HOME>/hermes-agent/venv` ro; PRE-CREATE the mountpoint dir
    in the profile (else root-owned leftover, see pitfalls); STT/PYTHON_BIN
    point at the host venv (`<HERMES_HOME>/hermes-agent/venv/bin/python`).
  - **Baked image** (e.g. `:20260830+`, deps baked into `/opt/hermes/.venv`;
    pull from the VPS fleet via `docker save`/`load` when not built locally):
    NO venv mount; STT/PYTHON_BIN point at `/opt/hermes/.venv/bin/python`;
    no mountpoint dir to pre-create.
- `<HOST_USER_HOME>/workspaces/<name>` mounted rw at the same host path
- Profile-internal symlink: `~/.hermes/models -> <HERMES_HOME>/hermes_files/<model-store>`

## Image building — bake deps INTO the hermes venv (owner requirement)
«همه چیز باید توی venv هرمس نصب بشه» — NOT system python. The image's
`/opt/hermes/.venv/bin/python3` is a SYMLINK to the image python but has its
OWN site-packages. Two-phase offline build, exact-version pins:

- Dockerfile lives next to the skill: `scripts/sudo-image.Dockerfile`, built
  from a docker dir that also holds `wheels/` (get-pip.py + every pinned wheel).
  `docker build -t <IMAGE>:<TAG> <docker-dir>` (guard flags it long-lived →
  background=true).
- **Phase A (offline)**: `get-pip.py --no-index --find-links=/opt/hermes-wheels`,
  then `pip install --no-index --find-links=/opt/hermes-wheels <pkgs>` into the
  venv. Keep `wheels/` INSIDE the docker dir until the LAST RUN (a mid-file
  `rm -rf /opt/hermes-wheels` before Phase B breaks it).
- Typical baked sets:
  - book-to-skill extraction: `pypdf`, `pdfminer.six`, `ebooklib`,
    `beautifulsoup4`, `soupsieve`, `striprtf`, `trafilatura`, `python-docx`,
    `python-pptx`, `openpyxl`, `pymupdf`, `weasyprint`, `arabic_reshaper`, `python_bidi`
  - STT/TTS libs: `sherpa_onnx`, `numpy`, `soundfile`, `cffi` (stt.py imports
    all three — the first venv-baked build failed on `No module named soundfile`)
  - firecrawl client: `firecrawl-py==<version pinned by web_tools lazy-loader>`,
    `nest-asyncio`, and keep `websockets` at the version hermes-agent requires
    (15.0.1; a newer one breaks the gateway requirement check)
  - AI/doc: `torch==<pinned>+cpu`, `torchvision`, `docling`, `onnxruntime`,
    `transformers`, `tokenizers`, `safetensors`, `accelerate`
- **CPU torch ONLY from download.pytorch.org/whl/cpu** — never let pip pull
  torch from PyPI (2.5GB CUDA bundle). Pin `sympy` to what torch needs
  (host `pip freeze` is the source of truth).
- **Version-pin EVERY wheel to the host venv's `pip freeze`**, single version
  per package — duplicates make pip fall into "dependency graph is too complex"
  backtracking that stalls 15-40+ min and fails.
- **docling's transitive graph is hostile offline**: antlr4-python3-runtime==4.9.*
  exists only as an SDIST tar.gz, omegaconf pins it, semchunk must be `<4`,
  typer `<0.27`, pydantic-core==2.46.x vs pydantic 2.13.4 — walk the pins once,
  write them down, don't re-derive.
- **Both interpreters must see the deps**: venv directly AND plain `python3`
  via a `.pth`: `echo '<venv-site-packages>' > <sys-dist-packages>/hermes-venv.pth`
  → scripts that call bare `python3` (e.g. extract.py without PYTHON_BIN) work too.
- `pdftotext` (poppler) is NOT in the image; pypdf/pdfminer cover PDFs.
- Keep a FULL test of the built image before touching any container: imports
  from BOTH pythons, `extract.py --check`, a real pptx/docx roundtrip,
  `import soundfile, sherpa_onnx`.

## The host-venv ro mount is GONE on baked images
Modern images don't need the host venv mounted ro. Before dropping it from
compose: first migrate every profile's STT/TTS commands from
`<host hermes venv>/bin/python` to `/opt/hermes/.venv/bin/python`
(sed across all `profiles/*/config.yaml`, verify 0 leftovers and N new refs),
then remove the mount line, validate `docker compose config --quiet`, recreate
the fleet, verify `docker inspect … | grep -c venv` → 0.

## In-container pip installs work
- `/opt/hermes/.venv` is writable in every container; `pip install` goes there.
- Network reality (Iran/proxied VM): PyPI/sjtu direct is NOT reachable, and
  pip's socks support is broken (`PoolKey 'key_proxy_ssl_context'` bug). Two
  reliable paths:
  - **offline wheels**: `pip download` on the HOST (host pip + socks proxy),
    `docker cp` wheels in, in-container
    `pip install --no-index --find-links <dir> <pkgs>` (pure-python or
    matching-ABI wheels only — cp311 wheels do NOT install on cp313).
  - **HTTP proxy shim**: `privoxy` on the host forwarded to the SOCKS tunnel
    (`forward-socks5t / 127.0.0.1:1080 .`, listen 8118, systemd service) →
    in-container `https_proxy=http://127.0.0.1:8118 pip install <pkg>` works
    (containers run network_mode=host, so 127.0.0.1 is the host).

## Package installs: ONLY into the hermes venv (owner rule)
When a package must be installed, it goes into the hermes venv —
`/opt/hermes/.venv` (baked images) or the host hermes-agent venv — NEVER into
the container system python3 and NEVER via `--break-system-packages`. The
in-container gateway interpreter is `/opt/hermes/.venv/bin/python3`; a `.pth`
makes bare `python3` see it too. `HERMES_LAZY_INSTALL_TARGET=/home/oem/.hermes/lazy-packages`
(persistent, rw) is the lazy-install landing pad inside the profile.

## Own pure-py packages → lazy-packages (Ali's box, kept in add-bot.sh)
The main hermes venv holds pure-python packages the bots need but the STOCK
image does NOT have. add-bot.sh provisions them OFFLINE by copying from the
host venv site-packages into the profile's `lazy-packages/` (no pip, no
PyPI — containers have no guarantee of egress). Current list (all pure-py,
ABI-independent; extend in add-bot.sh):
- `firecrawl` / `firecrawl_py-*.dist-info` — web backend client (self-hosted
  Firecrawl at :3002)
- `nest_asyncio.py` / `nest_asyncio-*.dist-info` — firecrawl lazy-loader dep
- websockets at the hermes-agent-pinned version (15.0.1) — must NOT be
  upgraded by firecrawl-py
- `semchunk` (book-to-skill chunking) — pure-py, follows docling's <4 pin
- `pypinyin` — sherpa-zh STT tokenizer (wake-word/tokenize fails silently
  without it)
- `sherpa_onnx`, `soundfile`, `cffi` (cp313 wheels baked into the image when
  using the rebuild path — NOT copyable across ABI; do not lazy-copy)
Verify after add: `PYTHONPATH=~/.hermes/lazy-packages /opt/hermes/.venv/bin/python3 -c 'import firecrawl; import nest_asyncio'`.

## Runtime access model (accepted by the owner)
- **Passwordless `sudo` inside the container** (derived image). Container-root
  only: no docker socket, host mounts ro, default seccomp/caps, isolated PID ns
  → no host escape. Residual: `network_mode: host` + NET_RAW means
  container-root could use raw sockets on the host LAN — accepted for trusted
  setups.
- **Bot user can read its own profile `.env`** (uid 1000, mode 600) — by design
  (gateway loads it; shared LLM keys accepted as readable per bot; platform
  token stays UNIQUE per bot).

## Provisioning — quick start
```bash
<HERMES_HOME>/skills/system-admin/hermes-bot-containers/scripts/add-bot.sh \
  <name> --token <PLATFORM_TOKEN> --user <USER_ID> [--admins <ID1,ID2>] \
  [--compose-file <COMPOSE_DIR>/docker-compose.yaml] [--no-start]
```
Remove: `scripts/rm-bot.sh <name>`.

The script: profile dirs + workspace → `.env` copied from main (token/user
swapped, secrets stripped) → skills rsync as REAL copies with `models/`
symlinks re-created → config.yaml generated with platform overrides → compose
service appended → container up → in-container venv-ai with `mcp<2`.
`--no-start` skips the last two.

Security: prefer token via env var or `read -r -s` over argv (`--token` is
visible in process listings). Tokens live only in the profile `.env` (600).

## Manual steps (same as the script)
1. **Profile**: `mkdir -p <HERMES_HOME>/profiles/<name>`.
2. **.env**: copy main; swap token/home-channel/allowlist (owner + extra
   admins explicitly); scrub secrets (SUDO_PASSWORD, BROWSERBASE_*, EXA_KEY,
   PARALLEL_KEY, FAL_KEY, FIRECRAWL_API_KEY, OPENROUTER, VOICE_TOOLS_OPENAI_KEY,
   GROQ_KEY, ELEVENLABS_KEY). Keep shared LLM keys + platform token + TTS/STT.
   Force `BALE_ALLOW_ALL_USERS=false` and `GATEWAY_ALLOW_ALL_USERS=false`.
   TTS normalization: force `MATCHA_TTS_BIN` and `ESPEAK_DATA` to the shared
   store paths (main's values may point at host-only paths).
3. **Skills + plugins**: `rsync -aL --delete` main skills (dereference links),
   excluding `models/` symlinks (find them INCLUDING inside top-level skill
   symlinks), then re-create those links to absolute shared-store targets.
   Copy `plugins/` too (`rsync -a --exclude='.git/'`) — the platform adapter
   lives there and the gateway CANNOT start without it.
4. **Memory/soul**: fresh profile = no admin data.
5. **config.yaml**: platform overrides (api_server disabled; platform toolsets
   WITHOUT cronjob; plugins.enabled as a LIST; memory-store db path; terminal
   cwd → that bot's workspace; TTS/STT provider commands; mcp_servers with
   in-profile server files).
6. **Compose service** (network_mode: host for localhost MCP like firecrawl):
```yaml
  <name>:
    image: <IMAGE>:<TAG>
    container_name: hermes-<name>
    restart: unless-stopped
    network_mode: host
    working_dir: <HOST_USER_HOME>/workspaces/<name>
    environment:
      - PUID=1000
      - PGID=1000
      - HERMES_UID=1000
      - HERMES_GID=1000
      - HOME=<HOST_USER_HOME>
      - HERMES_HOME=<HOST_USER_HOME>/.hermes
      - HERMES_WRITE_SAFE_ROOT=<HOST_USER_HOME>
      - API_SERVER_ENABLED=false
      - TZ=<YOUR_TZ>
    volumes:
      - <HERMES_HOME>/profiles/<name>:<HOST_USER_HOME>/.hermes
      - <HERMES_HOME>/hermes_files:<HOST_USER_HOME>/hermes_files:ro
      - <HOST_USER_HOME>/workspaces/<name>:<HOST_USER_HOME>/workspaces/<name>
      - <shared stores as needed>:ro
    command: ["gateway", "run"]
    mem_limit: 2g      # fleet policy: 1 CPU core + 2 GB per bot
    cpus: 1            # keep add-bot.sh template in sync when changing
```
7. **Per container**: `python3 -m venv ~/.hermes/venv-ai` IN the container +
   `pip install "mcp<2"` (only if MCP servers are used; venv-ai is
   container-ABI-specific — host-built venvs dangle).

## Hard rules (each cost a debugging session)
1. **Copying main's state.db into a profile requires neutralizing resume**
   before boot: `UPDATE sessions SET ended_at=?, end_reason='completed'
   WHERE ended_at IS NULL` and `DELETE FROM gateway_routing`. Otherwise the bot
   resumes main's most recent OPEN session and replays its dangling tool calls
   (files in bot workspace, messages to main's chats, "Recovered dangling
   side-effecting tool call(s) as UNKNOWN").
2. **Never `cp` live SQLite DBs** (WAL-backed, gateway writing). Use Python
   `src.backup(dst)` (or `VACUUM INTO`); remove stale `-wal`/`-shm`/lock files
   when overwriting targets.
3. **Verify after any mirror**: byte-compare memory files; in-container
   `PRAGMA integrity_check` + row counts equal to snapshot; workspace
   `rsync -n` diff empty.
4. **`BALE_ALLOW_ALL_USERS` / `GATEWAY_ALLOW_ALL_USERS` must be `false`
   everywhere.** GATEWAY_ALLOW_ALL_USERS is a REAL global allow-all
   short-circuit. Sweep: `grep -HnE "^(BALE|GATEWAY)_ALLOW_ALL_USERS"
   <HERMES_HOME>/.env <HERMES_HOME>/profiles/*/.env`, fix with backup, restart.
5. **Removing groups entirely**: repoint `BALE_HOME_CHANNEL` to the owner's DM
   or scheduled deliveries land in a now-forbidden chat.
6. **Trust decisions can reverse** (previously-blocked user becomes trusted):
   apply the owner's allowlist instruction EXACTLY, flag security history,
   update memory/fact_store.
7. **Restarting the main gateway while the agent runs INSIDE it**: a child
   process dies with the gateway and the terminal tool rejects setsid/&
   wrappers. Use the cron-armed one-shot (below).

## Restarting the main gateway from inside (cron-armed one-shot)
1. Script: `[ -f /tmp/gw-restart-flag ] || exit 0; rm -f /tmp/gw-restart-flag;
   sleep 75; python3 ~/.hermes/scripts/kill-gateway.py; sleep 55;
   <verify "Connected as">; curl Bot API sendMessage → owner DM`.
2. Append crontab line (dedupe by grepping the name first).
3. `touch /tmp/gw-restart-flag`; reply delivers first; cron runs OUTSIDE the
   gateway's process group → kill survives, supervisor restarts, confirmation
   lands in the owner's DM. Clean up the one-shot afterwards.

## Long background jobs & delegations (owner behaviour, verified)
- `delegate_task` subagents run IN-PROCESS inside the gateway: no separate OS
  process to kill; their file writes keep landing even after `rm -rf` of the
  target dir (the worker re-creates it).
- Stopping per owner «قطع کن»: (1) purge worker's output immediately; expect
  re-creation; (2) bounded delegation finishes in minutes — purge once more
  when its result arrives; (3) the ONLY hard stop is the cron-armed gateway
  restart (kills the session too) — say so honestly, offer it, don't sneak it.
- Prevention: present cost/effort estimate and get explicit go BEFORE
  delegating long LLM-heavy jobs (owners cancel mid-flight otherwise).

## Resource limits (fleet policy)
Every bot container is `cpus: 1` + `mem_limit: 2g` (compose AND add-bot.sh
template — keep both in sync). Fleet-wide changes:
- `docker update --cpus 1 --memory 2g hermes-*` does NOT work (shell glob
  matches cwd files). Use IDs:
  `docker update --cpus 1 --memory 2g --memory-swap 2g $(docker ps -q --filter name=hermes-)`.
- Containers with `memswap_limit` set refuse a standalone `--memory` update —
  pass `--memory-swap` in the same command.
- Scope discipline: apply to exactly the containers named, nothing else.
- Compose-edit → `docker compose up -d` recreates only changed services
  (~seconds blip); the terminal guard flags compose as long-lived →
  background=true. Always verify via `docker inspect` (NanoCpus, Memory) —
  never trust compose alone.
- When asked "what does Hermes recommend?": cite OFFICIAL docs — 1 GB/1 core
  minimum, 2–4 GB/2 cores recommended; browser automation raises the floor to ≥2 GB.

## Fleet image MIGRATION runbook (canary → batch → priority-user-last)
**NEVER delete containers during a migration.** The rule: migrate = recreate,
never remove. NO `docker rm`, NO `docker compose down`, NO `rm-bot.sh` for a
migration — the bots keep their names, compose services, profiles, and
workspaces; only the image/container is replaced. `docker compose up -d` with
a changed image tag recreates ONLY the containers whose config changed
(`--force-recreate` forces it even when the tag is unchanged). A fresh
`docker-compose.yaml` written by add-bot.sh must never start by deleting
services — it appends/updates in place.

1. `docker images <IMAGE>` FIRST — the running compose may reference a tag that
   was deleted externally (e.g. any later `compose up` would fail). Back up
   compose; `sed -i 's|image: …:OLD|image: …:NEW|g'`; `docker compose config --quiet`.
2. **Backup before touching anything** — WAL-safe via python
   `sqlite3 src.backup(dst)` for every state/memory/kanban/projects/verification
   DB + config tgz + workspace tgz. Reusable: `scripts/backup-bot-profile.sh <name>`.
   Run `PRAGMA integrity_check` AFTER backup.
3. **Canary one low-stakes container** (NOT the priority/heaviest user):
   recreate it; verify new tag, gateway process alive, gateway_state = running +
   platform connected, key imports from BOTH pythons.
4. **Batch the rest**, excluding the priority user.
5. **Priority user last**: fresh backup immediately before; recreate; verify
   image+gateway+platform connected+open sessions preserved
   (`SELECT id,title,source FROM sessions WHERE ended_at IS NULL`) + the
   operation that was broken before now works end-to-end.
6. All containers on new tag, every `gateway_state.json` = running + connected.

## Web backend: firecrawl self-host + Tavily removal
- Hermes web tools backend = **firecrawl self-hosted**; see
  `hermes-selfhost-firecrawl-skill` for the full stack (3 ghcr images + redis/
  rabbitmq/foundationdb; compose must use prebuilt images, NOT source build; the
  DAEMON needs the socks proxy to pull ghcr; containers must egress through the
  host socks relay — a scrape of `https://api.ipify.org` returning the proxy
  exit IP in the body is the real egress proof).
- Firecrawl containers need `--restart unless-stopped` (they had none →
  stack vanished after reboot).
- **Tavily is DISABLED by owner decision (2026-08-30)** — strip ALL refs when
  working in such envs: remove `TAVILY_API_KEY`/`TAVILY_BASE_URL` from every
  profile `.env`, set `web.search_backend: firecrawl`, drop
  `tavily-search`/`tavily-search-advanced` tool listings. Restart containers.
- If `web_extract` complains "Feature 'search.firecrawl' unavailable: pip
  install failed", the lazy-loader needs `firecrawl-py==<exact pinned version>`
  in the venv — bake it into the image (with `nest-asyncio`, and `websockets`
  pinned to what hermes-agent requires; a `--force-reinstall` of firecrawl-py
  silently upgrades websockets → re-pin it).

## Container book-to-skill: NEVER --break-system-packages
Container SYSTEM python3 is PEP 668 and lacks pypdf; extract.py then falls
through every parser and the agent reaches for
`pip install --break-system-packages` (→ suspicious approval prompt). Run:
`PYTHON_BIN=/opt/hermes/.venv/bin/python3 … extract.py <book> --mode text --install-missing no`
— zero installs.

## Container voice stack (TTS/STT) repair
- **Test correctly first**: `docker exec` lacks the gateway env — always
  `set -a; source ~/.hermes/.env; set +a; export LD_LIBRARY_PATH=<tts-libs>` before
  running tts.py/stt.py by hand, else a false "MATCHA_TTS_BIN is not set".
- **Profile .env holds host-only paths** — MATCHA_TTS_BIN must be a WORKSPACE or
  shared-store copy (rw mount), not a host-only path; ESPEAK_DATA must point at
  the shared tts-libs espeak-ng-data.
- **tts-libs must contain**: libonnxruntime.so.1, libicu*.so.<hostver> (host
  version, NOT hardcoded), libespeak-ng.so.1, libpcaudio.so.0, libsonic.so.0,
  espeak-ng-data/. Verify `ldd <bin> | grep "not found"` = 0 in-container;
  copy with `cp -aL` (cp -av copies dangling symlinks).
- **"file lost"/"STT not installed" complaints need reality checks**: platforms
  save attachments under their ORIGINAL filename, and "voice" files can be
  byte-identical non-audio copies (check magic bytes/md5).

## Bot session forensics & suspicious-approval triage
Read-only sqlite queries against `<HERMES_HOME>/profiles/<name>/state.db`
(schema: messages uses `id` not `session_id`; `effect_disposition` =
pending/intercepted). Distinguish `"approved by the user"` vs
`"auto-approved by smart approval"` in tool outputs. Common root cause of
"approve?" for book tasks: the agent hit the PEP 668 system python → see
book-to-skill section.

## Owner care/trust notes
- Owners may do EXTERNAL cleanup between sessions («از بیرون یکم پاک کردم»).
  After such a message: RE-VERIFY images/compose/containers before resuming —
  never assume the image you built earlier still exists.
- Owners are ALARMED by destructive-looking commands (e.g. a plain
  `docker run --rm` once drew «داشتی چی رو پاک میکردی؟»). Before any
  delete/override/`--rm`, state exactly what is being removed and that it's
  non-destructive; prefer explicit non-destructive probes; always back up
  before writes.

## Verification checklist (`scripts/verify-bot.sh <name>` on the host)
```bash
docker exec -u hermes hermes-<name> bash -lc 'echo $HOME $HERMES_HOME'   # correct overrides
docker exec -u hermes hermes-<name> bash -lc 'apt-get install -y sl 2>&1 | tail -1'      # must fail
docker exec -u hermes hermes-<name> bash -lc 'curl -s -o /dev/null -w "%{http_code}" http://localhost:3002/'  # 200 (firecrawl)
docker exec -u hermes hermes-<name> bash -lc '<tts round trip: tts.py → stt.py with env loaded>'
grep "Connected as" <HERMES_HOME>/profiles/<name>/logs/agent.log | tail -1   # platform connected
```

## Common ops
```bash
docker restart hermes-<name>                                          # reload config/.env
cd <COMPOSE_DIR> && docker compose up -d --force-recreate              # mount changes
docker logs --tail 100 hermes-<name> 2>&1
tail -f <HERMES_HOME>/profiles/<name>/logs/agent.log
```

## Disk-space guard (Ali's box: / at 95%+ — CHECK BEFORE big ops)
The host disk fills up fast (models, wheels, image builds, backups). Before
anything heavy — image build, wheel downloads, backup tars, migration —
run `df -h /` and DO NOT proceed past ~90% (leave >=20G for docker + builds):
- builds: keep wheels out of the image layers (`rm -rf /opt/hermes-wheels`
  in the LAST RUN) and prune with `docker image prune` after tag bumps
  (OLD tags like :20260827 can be removed once every service is on the new tag).
- backups: `backup-bot-profile.sh` tars the workspace too — a big workspace
  (~100M+) triples backup size; use `--no-workspace`/ROOT on a different FS
  when the profile is huge and the disk is tight.
- hermes_files store: ONE tar (see Nightly backup) — do not re-tar per bot.
- `docker system df` to see what is actually eating space before pruning.

## Nightly backup
Push `<HERMES_HOME>` — INCLUDING all bot profiles — to an offsite git remote
(cron). Details:
- Live SQLite inside profiles is NEVER raw-git-added: `git rm --cached` them
  from backup history; commit consistent snapshots per bot via the python
  sqlite3 backup API under `profiles-db-snapshots/<bot>/*.db`.
- Excluded from git: live DBs, venv-ai/, logs/, cache/, bin/, home/, state/,
  cron/ticker_*, gateway runtime files, ALL model binaries (re-downloadable;
  root-level catch-all REQUIRED — nested .gitignore does NOT stop `git add -A`).
- Profile `.env` (tokens) backed up offsite — consistent with main.
- Verify after backup: `git status -sb` clean, `git ls-files 'profiles/*/state.db'`
  and `'*.onnx'` are 0, snapshot count sane.
- **Offline store backup** (models/libs are NOT in git): manual tar of the
  shared store — the only full recovery path if it's wiped.

## Pitfalls (each one cost a debugging session)
1. **Image defaults** set `HERMES_HOME=/opt/data` and shell `HOME=/root` —
   override BOTH in compose or skills/models land in the wrong place (a
   duplicate 220MB model download happened exactly this way).
2. **Relative symlinks in main skills** dangle in profiles — rsync `-L` and
   re-link `models/` AFTER (targets are absolute into the shared ro store).
3. **Copying .env verbatim is mostly safe** — except tokens/secrets swap; do
   NOT delete `HERMES_LOCAL_STT_COMMAND` or change its value.
4. **MatchaTTSInfer** needs host-built shared libs + `LD_LIBRARY_PATH` +
   host locale ro mounts or the C++ daemon aborts on `std::locale`.
5. **`pip install mcp` (v2)** breaks `from mcp.server.fastmcp import FastMCP` → pin `mcp<2`.
6. **Stale TTS daemon socket after `docker restart`** → Connection refused;
   hardened tts.py probes/unlinks/restarts — keep it in sync (main + profiles).
7. **"Previous gateway life exited UNCLEANLY"** after `--force-recreate` is EXPECTED.
8. **`hermes config set plugins.enabled`** may write a string instead of a
   list → gateway breaks; verify with grep; repair with python yaml.
9. **Gateway initializes the profile** on first boot (SOUL.md, backups/,
   cache/, gateway.pid) — NORMAL, not corruption.
10. Gateway writes `.env.bak`/`config.yaml.bak` at boot — profile needs rw,
    everything shared is ro.
11. Test scripts in container `/tmp` vanish on recreate — keep them on the host.
12. `docker restart` reloads config/.env; `--force-recreate` only for
    mount/env changes.
13. **web_extract lazy-loader needs EXACT firecrawl-py version** — see web
    backend section; verify `import firecrawl` from
    `/opt/hermes/.venv/bin/python3` (bare `python3` is NOT the gateway
    interpreter for import tests... actually with the bake + .pth both work).
14. **Allow-all flags propagate on manual .env copies** — always re-audit:
    the env sweep command in Hard rules.
15. **Suspicious approve for book tasks** = PEP 668 system python — see
    book-to-skill section.
