> Platform reference for `hermes-bot-provisioning`. No tokens or ids belong in
> a skill: the tables below use placeholders only. Every key here was checked
> against the adapters' own `plugin.yaml` and code.

**Precedence:** both adapters resolve `platforms.<platform>.<key>` from the
profile's `config.yaml` FIRST and fall back to the `*_<KEY>` env vars. A change
made only in `.env` can therefore appear to do nothing if `config.yaml` still
carries the old value.

# Bale (بله)

- API: Telegram-compatible REST at `https://tapi.bale.ai/bot<TOKEN>/<method>`.
- Transport: long polling (`getUpdates`) over `aiohttp`; no third-party SDK in the
  shipped adapter (its `plugin.yaml` still advertises `python-bale-bot`, and the
  manifest also declares `BALE_WEBHOOK_URL`, but the code always long-polls and
  clears any webhook with `deleteWebhook` on connect).
- Token source: the bot's creator channel (@BotFather equivalent).
- Adapter: a Hermes plugin of kind `platform` at
  `~/.hermes/plugins/platforms/bale/`.

| Env var | Required | Meaning |
|---|---|---|
| `BALE_BOT_TOKEN` | yes | token, `<id>:<secret>` |
| `BALE_ALLOWED_USERS` | no | comma-separated user ids allowed to chat |
| `BALE_ALLOWED_CHATS` | no | comma-separated chat ids (DMs and groups) |
| `BALE_ALLOW_ALL_USERS` | no | `false` always for a real bot |
| `BALE_HOME_CHANNEL` | no | default chat for cron/notifications |
| `BALE_REQUIRE_MENTION` | no | require @mention in groups (the bot must be an admin) |
| `BALE_MAX_VOICE_DURATION` | no | max voice/audio length fed to STT, in **seconds** (default 30, `0` = no limit) |
| `BALE_WEBHOOK_URL` | no | declared in the manifest for webhook mode; the current adapter ignores it and polls |

# Soroush Plus (سروش پلاس)

- API: official Bot API at `https://api.splus.ir/bot<TOKEN>/<method>`
  (Telegram-compatible REST, `aiohttp`; the shipped adapter does not use the
  third-party SDK its README mentions).
- Transport: long polling.
- Token source: the platform's official bot/creator channel (splus.ir/botfather).
- Adapter: `~/.hermes/plugins/platforms/soroush/`.

| Env var | Required | Meaning |
|---|---|---|
| `SOROUSH_BOT_TOKEN` | yes | token |
| `SOROUSH_ALLOWED_USERS` | no | comma-separated user ids |
| `SOROUSH_ALLOWED_CHATS` | no | comma-separated chat ids |
| `SOROUSH_ALLOW_ALL_USERS` | no | `false` always for a real bot |
| `SOROUSH_HOME_CHANNEL` | no | default chat for cron/notifications |
| `SOROUSH_REQUIRE_MENTION` | no | require @mention in groups (read by the adapter, not declared in its manifest) |

# Both platforms

- **Allowlist semantics:** an empty allowlist means the bot answers anyone who can
  reach it. Always set users **and** chats, and keep `*_ALLOW_ALL_USERS=false`.
- **Home channel:** cron jobs and background deliveries go to
  `*_HOME_CHANNEL` (or `platforms.<plat>.home_channel.chat_id`, which wins).
  Put that chat in the allowlists too if the bot should also *answer* there —
  `add-bot.sh --home` does that for you.
- **Groups:** group ids must be in the allowlists and are negative; keep the
  mention gate on when the bot should not answer every message.
- **Voice notes:** incoming voice is transcribed by whatever STT provider the
  profile has configured; replies can be synthesized by a TTS command provider.
  Both live in the profile's `config.yaml` under `stt:` / `tts:`.

# Diagnosis order when a bot “does not answer”

1. `systemctl --user is-active hermes-gateway-<name>` — is it running at all?
2. `grep 'Connected as' <profile>/logs/agent.log | tail -1` — did the adapter log
   in? An empty handle (`Connected as @ (id=)`) means the token was rejected.
3. Allowlists — is the sender's id in both `*_ALLOWED_USERS` and `*_ALLOWED_CHATS`?
4. Credentials, straight from the platform:
   `curl -s https://<api>/bot<TOKEN>/getMe` (Bale: `tapi.bale.ai`,
   Soroush: `api.splus.ir`) — `"ok":true` means the token is good. `ok:false` is a
   token problem; no answer at all is a network/DNS problem.
5. `deleteWebhook` if the token was ever used in webhook mode, otherwise
   `getUpdates` returns nothing and polling never advances.
6. Logs: `<profile>/logs/agent.log` (INFO+) and `errors.log` (WARNING+).
