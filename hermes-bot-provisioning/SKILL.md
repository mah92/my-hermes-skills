---
name: hermes-bot-provisioning
description: "Use when adding/removing a Bale or Soroush bot."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, bots, profiles, bale, soroush, provisioning, systemd, gateway]
    related_skills: [hermes-bale-messenger, hermes-soroush-messenger]
---

# Bot Provisioning (Bale / Soroush Plus)

Add or remove a **bot** on a Hermes host: one profile per bot, its own token,
its own allowlist, its own gateway service. Works on any Linux host with a
normal Hermes install and the matching platform adapter plugin.

Self-contained and parametric — no host-specific or personal values. Replace
`<name>`, `<TOKEN>`, `<USER_ID>`, `<HOME>` with your own. For long-running fleet
operations on one specific box (which profiles exist, image tags, backup
infrastructure, migration history) belong in local notes / the fact store, not in
a skill; this one is the portable add/remove recipe.

## When to use
- A new person (or a new purpose) needs their own bot on Bale or Soroush Plus.
- An existing bot must be removed cleanly (service + profile + workspace).
- A bot exists but does not answer and the operator needs the check order.

## Model: one profile per bot, gateway on the host
- **Profile** = `<HOME>/.hermes/profiles/<name>` (config.yaml, .env, skills/,
  plugins/, state.db). Nothing about the bot lives in a container.
- **Gateway** = a systemd *user* unit `hermes-gateway-<name>.service`, created by
  `hermes -p <name> gateway install`. It needs user lingering, or it stops when
  the operator logs out.
- **One token = one poller.** Never run two gateways (or a gateway plus a stray
  script/container) on the same bot token: both poll, and messages are lost.

## Prerequisites
1. A working Hermes install: `<HOME>/.hermes/hermes-agent` with its venv, and the
   `hermes` CLI on PATH.
2. The platform adapter plugin installed as a **profile-local** plugin. Bale and
   Soroush Plus adapters are Hermes plugins of kind `platform`:
   ```bash
   git clone <your-adapter-repo-url> <HOME>/.hermes/plugins/platforms/<platform>
   ```
   (`<platform>` = `bale` or `soroush`). Plugins under `~/.hermes/plugins/` are
   NOT shared with profiles automatically — the provisioning script copies them
   into each profile, which is why a fresh profile with no `plugins/` never
   connects.
3. A **bot token** for that bot (issued by the platform's bot/creator channel —
   see `references/platforms.md`).
4. The **numeric user id** of the person who owns the bot; their private chat
   with the bot becomes the bot's home channel.

## Provision
```bash
scripts/add-bot.sh <name> --platform bale|soroush \
  --token <TOKEN> --user <USER_ID> [--admins <ID1,ID2>] [--home <CHAT_ID>] \
  [--skip-skills] [--no-start] [--sandbox-image <IMAGE>:<TAG>]
```
What it does, in order:
1. Creates the profile dir and `<HOME>/workspaces/<name>`.
2. Copies the main `.env`, then rewrites it for this bot: the chosen platform's
   token/home/allowlists set, `*_ALLOW_ALL_USERS=false` forced, **every other
   platform's `*_BOT_TOKEN` line commented out** (an inherited token would start
   a second poller on the main bot), and admin secrets (sudo password, cloud API
   keys) commented out. Shared LLM keys stay.
3. Copies skills (`rsync -aL`, `models/` symlinks re-created) and `plugins/`.
4. Writes the profile `config.yaml`: only the chosen platform enabled, the other
   disabled; `api_server` off; the platform toolset list; the platform plugin in
   `plugins.enabled`; profile-local memory store; `terminal.cwd` = the workspace.
   With `--sandbox-image`, the terminal backend is set to docker with that image.
5. `hermes -p <name> gateway install` and waits for the platform to connect.
6. Runs `scripts/verify-bot.sh <name>`.

Prefer passing the token through the environment (`BOT_TOKEN=… add-bot.sh …`) if
you care about it appearing in `ps`.

## Verify
```bash
scripts/verify-bot.sh <name>
```
Checks: service active, platform `Connected as` line present, no recent ERROR
lines, TTS/STT round trip (only when those providers are configured), MCP
handshake (only when MCP servers are configured), sandbox image present and free
of Hermes (when the backend is docker), workspace present, idle container count,
and config path hygiene (no leftover absolute container paths).
If the bot answers nothing, check in this order: the service, the `Connected as`
line, the allowlist (`<USER_ID>` must be in both `*_ALLOWED_USERS` and
`*_ALLOWED_CHATS`), then platform reachability (see pitfalls).

## Remove
```bash
scripts/rm-bot.sh <name>
```
Stops and uninstalls the gateway service, removes sandbox containers labelled for
that profile, removes the profile dir and workspace (with a sudo escalation
ladder for root-owned leftovers), and refuses to proceed while that profile's
gateway process is still alive. It never touches the main profile, shared skills,
or the sandbox image.

## Platform reference
`references/platforms.md` holds the Bale and Soroush Plus env-var tables,
endpoints, token sources, group/mention behaviour, voice limits, and the
platforms' own diagnosis steps (`getMe`, `deleteWebhook`, DNS checks).

## Optional: run the bot's commands in a sandbox
A profile can execute its *commands* (terminal/file/execute_code) inside a
Docker container while the gateway and agent stay on the host — the container
contains no Hermes. Build the image from
`references/sandbox-image.Dockerfile`, then provision with
`--sandbox-image <image>:<tag>`. Two rules: the sandbox is disposable (a runtime
package install disappears with the session — bake what you need into the
image), and its mounts mirror host paths, so it must run as the host uid/gid for
files written into bind mounts to stay yours.

## Pitfalls (each one cost a debugging session)
1. **Missing profile-local plugins**: the gateway logs `Plugin discovery
   complete` but never `Connected as`. Copy `plugins/platforms/<platform>` into
   the profile (the script does this).
2. **A fresh profile drifting onto the main bot's token**: every token line in
   the copied `.env` must be neutralised except the new bot's own. Symptom:
   messages vanish for the main bot too.
3. **Empty allowlist = open bot** on most adapters. Always set both
   `*_ALLOWED_USERS` and `*_ALLOWED_CHATS`, and keep `*_ALLOW_ALL_USERS=false`.
4. **Webhook mode blocks polling**: if the token was ever used with a webhook,
   call `<api>/bot<TOKEN>/deleteWebhook` before relying on long polling.
5. **A "dead" bot is often DNS/network**, not the adapter: test
   `<api>/bot<TOKEN>/getMe` before touching config, and do not restart-loop
   during a platform outage.
6. **Lingering**: without `loginctl enable-linger <user>` a user-unit gateway
   dies at logout and the bot "stops by itself".
7. **One token, one poller** — see above. Also applies to a forgotten copy of
   the profile running on another machine.
8. **Wrong interpreter in a bot's config**: a profile's commands must reference
   the *host* interpreter (`<HOME>/.hermes/hermes-agent/venv/bin/python`), never
   a path from another machine or from a container image.
9. **Group chats**: for the bot to answer in a group, the group id must be in the
   allowed lists; leave the mention gate on where members should not summon it
   accidentally.
10. **Verify from the bot's own config**, not with a hand-typed command: run
    `verify-bot.sh` — it exercises the profile's actual providers.
