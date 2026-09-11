> Platform reference for `hermes-bot-provisioning`. No tokens or ids belong in
> a skill: the tables below use placeholders only.

# Bale (بله)

- API: Telegram-compatible REST at `https://tapi.bale.ai/bot<TOKEN>/<method>`.
- Transport: long polling (`getUpdates`). No SDK, no user account.
- Token source: the bot's creator channel (@BotFather equivalent).
- Adapter: Hermes plugin of kind `platform`, installed at
  `~/.hermes/plugins/platforms/bale/` (clone your adapter repo into that path).

| Env var | Required | Meaning |
|---|---|---|
| `BALE_BOT_TOKEN` | yes | token, `<id>:<secret>` |
| `BALE_ALLOWED_USERS` | no | comma-separated user ids allowed to chat |
| `BALE_ALLOWED_CHATS` | no | comma-separated chat ids (DMs and groups) |
| `BALE_ALLOW_ALL_USERS` | no | `false` always for a real bot |
| `BALE_HOME_CHANNEL` | no | default chat for cron/notifications |
| `BALE_REQUIRE_MENTION` | no | require @mention in groups |
| `BALE_MAX_VOICE_DURATION` | no | max voice/audio ms fed to STT (`0` = unlimited) |

# Soroush Plus (سروش پلاس)

- API: official Bot API at `https://api.splus.ir/bot<TOKEN>/<method>`
  (Telegram-compatible REST).
- Transport: long polling, `aiohttp`, no third-party SDK.
- Token source: the platform's official bot/creator channel (splus.ir/botfather).
- Adapter: `~/.hermes/plugins/platforms/soroush/`.

| Env var | Required | Meaning |
|---|---|---|
| `SOROUSH_BOT_TOKEN` | yes | token |
| `SOROUSH_ALLOWED_USERS` | no | comma-separated user ids |
| `SOROUSH_ALLOWED_CHATS` | no | comma-separated chat ids |
| `SOROUSH_ALLOW_ALL_USERS` | no | `false` always for a real bot |
| `SOROUSH_HOME_CHANNEL` | no | default chat for cron/notifications |
| `SOROUSH_HOME_CHANNEL_THREAD_ID` | no | forum/topic thread id, if any |
| `SOROUSH_REQUIRE_MENTION` | no | require @mention in groups |

# Both platforms

- **Allowlist semantics:** an empty allowlist means the bot answers anyone who
  can reach it. Always set users **and** chats, and keep `*_ALLOW_ALL_USERS=false`.
- **Home channel:** cron jobs and background deliveries go to
  `*_HOME_CHANNEL`; point it at the owner's DM (or a group) that is itself in the
  allowlists, or scheduled messages will be dropped.
- **Groups:** group ids must be in the allowlists; keep the mention gate on when
  the bot should not answer every message.
- **Voice notes:** incoming voice is transcribed by whatever STT provider the
  profile has configured; replies can be synthesized by a TTS command provider.
  Both live in the profile's `config.yaml` under `stt:` / `tts:`.

# Diagnosis order when a bot “does not answer”

1. `systemctl --user is-active hermes-gateway-<name>` — is it running at all?
2. `grep 'Connected as' <profile>/logs/agent.log | tail -1` — did the platform
   adapter log in?
3. Allowlists — is the sender's id in both `*_ALLOWED_USERS` and `*_ALLOWED_CHATS`?
4. Platform reachability and credentials:
   `curl -s https://<api>/bot<TOKEN>/getMe` (Bale: `tapi.bale.ai`,
   Soroush: `api.splus.ir`). A DNS/network outage looks exactly like a broken
   adapter — do not edit config during an outage.
5. `deleteWebhook` if the token was ever used in webhook mode, otherwise
   `getUpdates` returns nothing and polling never advances.
6. Logs: `<profile>/logs/agent.log` (INFO+) and `errors.log` (WARNING+).
