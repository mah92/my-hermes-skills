# Bale Gateway Diagnostics — Session Notes

## Common Failure Patterns

### Pattern 1: Hardcoded DM block in adapter (SILENT — group OK, DMs dropped)

**Symptom:** Group messages work perfectly. DMs from ALL users (including allowed
users) never arrive. `getUpdates?offset=-1` via curl catches DMs — proving Bale
delivers them — but the gateway never logs the inbound message.

**Root cause:** The installed `~/.hermes/plugins/platforms/bale/adapter.py` has a
hardcoded DM filter in `_handle_update()`:

```python
# Security: only process group messages — ignore private DMs
# (the owner's policy: members are banned from DMing the bot)
if chat_type == "private":
    logger.debug("[bale] Ignoring private message from %s (group-only policy)", sender.get("id"))
    return
```

This silently drops ALL private messages before they reach the gateway's message
pipeline. Group messages flow normally, making diagnosis misleading.

**Fix:** Delete or comment out the block, restart gateway.

**Evidence from July 2026 session:**
- Gateway log: 0 DM inbound messages since 16:30, group messages normal
- Curl `getUpdates?timeout=30` caught `chat_id=<USER_ID> type=private text="الو"` — DM arrived at Bale
- Gateway never logged it — consumed by polling but dropped in `_handle_update`
- Adapter line 280: `if chat_type == "private": return`

### Pattern 2: Gateway "doesn't answer" but is actually running

**Symptom:** User reports no responses. Gateway status shows active, Bale connected,
polling started.

**Root cause found in July 2026 session:** `getUpdates?offset=-1` returned 0 results
and gateway log had no inbound messages since 16:38. The gateway was healthy — user
messages were simply not reaching Bale's servers. Possible causes:
- User messaging wrong bot
- Bale client network issue
- Bale server delay

**Diagnostic commands used:**

```bash
# getMe — token validity
curl -s "https://tapi.bale.ai/bot${TOKEN}/getMe" | python3 -m json.tool
# → OK, bot found

# getUpdates — are messages arriving?
curl -s "https://tapi.bale.ai/bot${TOKEN}/getUpdates?offset=-1&limit=3"
# → 0 results — Bale has no messages for this bot

curl -s "https://tapi.bale.ai/bot${TOKEN}/getUpdates?offset=0&limit=100"
# → 0 results — no messages ever (or all consumed)

# sendMessage — can bot send?
curl -s -X POST "https://tapi.bale.ai/bot${TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":<USER_ID>,"text":"test"}'
# → OK, message_id 615 — send works

# Gateway inbound check
grep "inbound message" ~/.hermes/logs/gateway.log | tail -10
# → Last message at 16:38:34, nothing since
```

### Pattern 3: Unauthorized user despite ALLOW_ALL_USERS=true

**Root cause:** Dynamic Platform enum (Bale not in `gateway/config.py` Platform enum).
Authz path in `authz_mixin._is_user_authorized()` fails to resolve `allow_all_env` from
`platform_registry`.

**Fix:** Explicit allowlist:
```
BALE_ALLOWED_USERS=<USER_ID>,<OTHER_USER_ID>
```

### Pattern 4: Auth config changes break the gateway

**Root cause:** Changing `BALE_ALLOW_*` or adding `GATEWAY_ALLOW_ALL_USERS` can
trigger unexpected authz behavior. Gateway appears to connect and poll but drops
messages.

**Fix:** Revert to the last known-working `.env` state. Do NOT add more flags.

### Pattern 5: Constant gateway restarts kill sessions

Every `sudo hermes gateway restart --system` kills the gateway process and all
in-flight agent sessions. When the user says "restart again" repeatedly, each
restart creates a new PID and loses any conversation context. Check logs for
`Stopping gateway for restart...` entries to confirm.

## Bale API Endpoints

- Base: `https://tapi.bale.ai/bot{TOKEN}/`
- getMe: `GET /getMe`
- getUpdates: `GET /getUpdates?offset=N&limit=N&timeout=N`
- sendMessage: `POST /sendMessage` (JSON body: chat_id, text)
- deleteMessage: `POST /deleteMessage` (JSON body: chat_id, message_id)
- deleteWebhook: `POST /deleteWebhook`
