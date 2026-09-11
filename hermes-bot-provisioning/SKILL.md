---
name: hermes-bot-provisioning
description: "Use when adding/removing a Bale or Soroush bot."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, bots, profiles, bale, soroush, provisioning, systemd, gateway]
    related_skills: [hermes-bale-messenger, hermes-soroush-messenger]
---

# Bot Provisioning (Bale / Soroush Plus)

Add or remove a **bot** on a Hermes host: one profile per bot, its own token, its
own allowlist, its own gateway service. Self-contained and parametric — no
host-specific or personal values. Replace `<name>`, `<TOKEN>`, `<USER_ID>`,
`<HOME>` with your own. Long-running details about one particular box (which
profiles exist, image tags, backup infrastructure, migration history) belong in
local notes / a fact store, not in a skill; this one is the portable add/remove
recipe.

## When to use
- A new person (or a new purpose) needs their own bot on Bale or Soroush Plus.
- An existing bot must be removed cleanly (service + profile + workspace).
- A bot exists but does not answer and the operator needs the check order.

## Model: one profile per bot, gateway on the host
- **Profile** = `<HOME>/.hermes/profiles/<name>` (config.yaml, .env, skills/,
  plugins/, state.db). Nothing about the bot lives in a container.
- **Gateway** = a systemd *user* unit `hermes-gateway-<name>.service`, created by
  `hermes -p <name> gateway install`; `add-bot.sh` enables user lingering itself
  (passwordless sudo) and only warns if it cannot.
- **One token = one poller.** Never run two gateways (or a gateway plus a stray
  script/container) on the same token: both poll and messages are lost.
- **Config beats env.** Both adapters read `platforms.<platform>.<key>` from the
  profile's `config.yaml` FIRST and fall back to the `*_<KEY>` env var, so a
  hand-edit of `.env` alone may appear to do nothing.

## Prerequisites
1. A Hermes install with its venv, e.g. `<HOME>/.hermes/hermes-agent/venv`. The
   scripts assume that layout; override with `HERMES_HOME`, `HERMES_PY` or
   `HERMES_BIN` if yours differs (pipx/uv installs, another user, etc.).
2. The platform adapter installed as a **profile-local** plugin:
   ```bash
   git clone <adapter-repo-url> <HOME>/.hermes/plugins/platforms/<platform>
   ```
   (`<platform>` = `bale` or `soroush`; the adapters are public Hermes plugins —
   `hermes-bale-messenger-plugin`, `hermes-soroush-messenger-plugin` — of kind
   `platform`, and they are NOT shared with profiles automatically, which is why a
   fresh profile with no `plugins/` never connects.) Their Python dependency is
   `aiohttp` — install it into the host venv, or the gateway logs `Plugin
   discovery complete` and never connects.
3. A **bot token** from the platform's bot/creator channel (see
   `references/platforms.md`).
4. Two numeric ids: the **owner's user id** and optionally the **home chat id**
   (the chat cron/notifications are delivered to; defaults to the owner's DM):
   send the bot one message as that person, then read `message.from.id` from
   `curl -s https://<api>/bot<TOKEN>/getUpdates`, or read the sender id from the
   profile's `logs/agent.log`. Group ids are negative. A handle (`@name`) is not
   an id and will silently produce a bot that answers nobody.

## Provision
```bash
scripts/add-bot.sh <name> --platform bale|soroush \
  --token <TOKEN> --user <USER_ID> [--admins <ID1,ID2>] [--home <CHAT_ID>] \
  [--skip-skills] [--no-start] [--sandbox-image <IMAGE>:<TAG>]
```
(`BOT_TOKEN` / `BOT_USER_ID` are also read from the environment, so a token need
not appear in `ps`.) What it does, in order:
1. Creates the profile dir and `<HOME>/workspaces/<name>` (with a README).
2. Copies the main `.env`, then rewrites it: chosen platform's token/allowlists/
   home/chat-id set, `*_ALLOW_ALL_USERS=false` and `GATEWAY_ALLOW_ALL_USERS=false`
   forced, **every key of the OTHER platform commented out** (its token would
   start a second poller; its allowlists and chat ids are the host's private
   data), host-only admin secrets commented out (shared LLM keys stay, on
   purpose), `PYTHON_BIN` pointed at the host venv. It then ASSERTS the result
   (no `SUDO_PASSWORD`, no live foreign-prefix key, at most one active token) and
   exits non-zero if the assertions fail.
3. Copies skills (`rsync -aL`, `models/` symlinks re-created) and `plugins/`, and
   warns if `aiohttp` is missing from the host venv.
4. Writes the profile `config.yaml`: only the chosen platform enabled, the other
   disabled, `api_server` off, the platform toolset list, the plugin in
   `plugins.enabled`, an explicit per-profile `hermes-memory-store` path,
   `terminal.cwd` = the workspace; with `--sandbox-image`, the docker backend.
   The whole `plugins:` block is replaced, so host-level plugin settings do not
   carry over.
5. `hermes -p <name> gateway install`, then waits for the platform to connect.
6. Runs `scripts/verify-bot.sh` and exits non-zero if it reports failures
   (except with `--no-start`, where the not-yet-started checks are printed as a
   NOTE).

`--home` sets the home channel in both `.env` and `config.yaml` and adds that chat
id to the allowlists, so a group you point notifications at can also be answered.

## Verify
```bash
scripts/verify-bot.sh <name>
```
**Profile checks** (these decide the exit code): service active, platform
connected with a NON-EMPTY handle, the platform accepting the token (`getMe`),
bot-specific token, only one active token, token unique across profiles,
`terminal.backend` defined, sandbox image present and Hermes-free, workspace
present, `state.db` present, no `/opt/hermes` leftovers in config or `.env`.
**PENDING** (not failures): service/platform/state.db on a profile that was never
started (`--no-start`), because there is no unit and no log yet.
**Host checks** (advisory, labelled `host:`, never counted): the voice round trip,
which runs THIS profile's own configured TTS/STT command providers and is skipped
when they are not command-type, and the count of configured MCP servers (no
handshake is performed; look for `MCP: registered` in the gateway log).
If the bot answers nothing, check in this order: the service, the `Connected as`
line, the allowlists (`<USER_ID>` must be in `*_ALLOWED_USERS` **and**
`*_ALLOWED_CHATS`), `getMe`, then platform reachability (see pitfalls).

## Back up before you change or remove anything
```bash
scripts/backup-bot-profile.sh <name> [backup_root]
```
WAL-safe: live SQLite is snapshotted with the sqlite3 backup API and verified with
`PRAGMA integrity_check` (a plain `cp` of a live WAL database is torn). Outputs a
per-DB snapshot plus `*-profile-config.tgz` (contains the bot's `.env` — keep it
private) and `*-workspace.tgz`. Restore: stop the gateway, put the databases back,
untar config and workspace, start again.

## Remove
```bash
scripts/rm-bot.sh <name>
```
Refuses to delete data while a poller for that profile is alive — and it resolves
"alive" from the process ENVIRONMENT (`HERMES_HOME=.../profiles/<name>`) and the
unit's `MainPID`, not from an argv substring, so it catches a gateway started
with either `-p` or `--profile` and never mistakes the operator's own shell for a
bot. Then it stops and uninstalls the unit, removes sandbox containers labelled
for the profile, and removes the profile dir and workspace with a sudo escalation
ladder. It never touches the main profile, shared skills or the sandbox image.
Exit codes: `0` removed, `1` a poller is running or leftovers remain, `3`
nothing to remove (no profile, no workspace, no unit).

## Operate a running bot
- **Rotate a token** (platform revoked or leaked): edit `<platform>_BOT_TOKEN` in
  the profile's `.env` (and `platforms.<platform>.bot_token` in its `config.yaml`
  if that key is set — config wins), then restart that one gateway. Never have two
  configurations live on the same token at once.
- **Upgrade the adapter**: `git pull` in `<HOME>/.hermes/plugins/platforms/<platform>`
  and then re-copy it into every profile that uses it — profiles keep their own
  copy, so a pull in the shared dir does nothing for existing bots.
- **Several bots for one owner**: run `add-bot.sh` once per bot with the same
  `--user`; each needs its own token, profile and service. Different tokens only —
  `verify-bot.sh` fails a duplicated one.
- **Move a bot to another host**: `backup-bot-profile.sh` on the old host, copy the
  tarballs plus the profile's `config.yaml`/`.env`, `add-bot.sh` on the new host
  (same name/token), then restore the `*-{state,memory_store,kanban}.db` snapshots
  with the gateway stopped, and make sure the OLD profile's gateway is stopped so
  only one poller exists.

## Platform reference
`references/platforms.md` — env-var tables, endpoints, token sources,
group/mention behaviour, voice limits, the `config.yaml` precedence rule, and the
diagnosis order (`getMe`, `deleteWebhook`, DNS checks).

## Optional: run the bot's commands in a sandbox
A profile can execute its *commands* (terminal/file/execute_code) inside a Docker
container while the gateway and agent stay on the host — the container contains no
Hermes. Build the image from `references/sandbox-image.Dockerfile` (it takes
`--build-arg UID=... GID=...`, default 1000, to match the host user), then provision
with `--sandbox-image <image>:<tag>`. Two rules: the sandbox is disposable (a
runtime package install disappears with the session — bake what you need into the
image), and its mounts mirror host paths, so it must run as the host uid/gid for
files written into bind mounts to stay yours.

## Pitfalls (each one cost a debugging session)
1. **Missing profile-local plugins**: the gateway logs `Plugin discovery
   complete` but never `Connected as`. Copy `plugins/platforms/<platform>` into
   the profile (the script does this) — and check `aiohttp` is installed.
2. **A fresh profile drifting onto the main bot's token**: every key of the other
   platform must be neutralised in the copied `.env`. Symptom: messages vanish
   for the main bot too.
3. **Empty allowlist = open bot** on most adapters. Always set both
   `*_ALLOWED_USERS` and `*_ALLOWED_CHATS`, and keep `*_ALLOW_ALL_USERS=false`
   (and `GATEWAY_ALLOW_ALL_USERS=false`).
4. **Webhook mode blocks polling**: if the token was ever used with a webhook,
   call `<api>/bot<TOKEN>/deleteWebhook` before relying on long polling.
5. **A "dead" bot is often DNS/network**, not the adapter: test
   `<api>/bot<TOKEN>/getMe` before touching config, and do not restart-loop
   during a platform outage.
6. **Lingering**: without `loginctl enable-linger <user>` a user-unit gateway
   dies at logout and the bot "stops by itself".
7. **One token, one poller** — see above. Also applies to a forgotten copy of the
   profile running on another machine.
8. **Wrong interpreter in a bot's config**: a profile's commands must reference
   the *host* interpreter (`<HOME>/.hermes/hermes-agent/venv/bin/python`), never a
   path from another machine or from a container image.
9. **Group chats**: for the bot to answer in a group, the group id must be in the
   allowed lists; leave the mention gate on where members should not summon it
   accidentally (on Bale the bot must be an admin for that gate to work).
10. **A green "Connected as" is not proof**: some adapters log it with an empty
    handle for a token the platform rejected. `verify-bot.sh` therefore probes
    `getMe`; a connection line with `@ (id=)` means the token is wrong.
11. **Verify from the bot's own config**, not with a hand-typed command: run
    `verify-bot.sh` — it exercises the profile's actual files and the platform.
