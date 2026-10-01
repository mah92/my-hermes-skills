# Bale Fresh Install — End-to-End Recipe

Verified working 2026-08-08. Every step confirmed against live gateway logs.

## 1. Clone Plugin

```bash
mkdir -p ~/.hermes/plugins/platforms
git clone git@github.com:<GITHUB_USER>/hermes-bale-messenger-plugin.git \
  ~/.hermes/plugins/platforms/bale
hermes plugins enable hermes-bale-messenger
```

Requires: SSH key authorized on GitHub (verify: `ssh -T git@github.com`).

## 2. Set Environment Variables (~/.hermes/.env)

```env
BALE_BOT_TOKEN=<BOT_ID>:...
BALE_HOME_CHANNEL=<USER_ID>
BALE_ALLOWED_CHATS=<USER_ID>
BALE_ALLOWED_USERS=<USER_ID>
```

**Critical:** ALL THREE of `BALE_HOME_CHANNEL`, `BALE_ALLOWED_CHATS`, AND
`BALE_ALLOWED_USERS` must be set. Setting only `BALE_ALLOWED_CHATS` causes
"Unauthorized user" on every message — chat allowlist and user allowlist
are separate checks.

## 3. Restart Gateway

```bash
python3 ~/.hermes/scripts/kill-gateway.py
```

## 4. Verify

```bash
tail -20 ~/.hermes/logs/gateway.log
```

Expected output:
```
[bale] Connected as @<bot> (id=<BOT_ID>)
[bale] Polling started
✓ bale connected
Gateway running with 1 platform(s)
```

**Failure signs to look for in logs:**
- `Unauthorized user: X (Name) on bale` → missing/broken `BALE_ALLOWED_USERS`
- `Ignoring message from non-allowed chat X` → missing `BALE_ALLOWED_CHATS`
- `Dropping message from unauthorized user` → both allowlists missing/wrong

## 5. Send /start from Bale App

The bot must receive `/start` from the allowed user before it can DM them.
