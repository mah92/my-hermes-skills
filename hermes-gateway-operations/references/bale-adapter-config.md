# Bale Adapter Configuration Patterns

Session-specific adapter patterns learned during Bale bot deployment and
troubleshooting.

## Filter Ordering

The adapter applies filters in this order (all must pass):

1. allowed_chats — `BALE_ALLOWED_CHATS` (from .env or `extra` dict)
2. Group mention filter — if present, skip non-@mention messages in groups
3. allowed_users — `BALE_ALLOWED_USERS` or `BALE_BLOCKED_USERS` (variant-dependent)

## Two Adapter Variants

The Bale adapter exists in two user-filtering variants. Both use `allowed_chats`
for chat-level filtering but differ in user-level filtering:

### Allowlist Variant (Recommended for Production)

```python
# In __init__:
self._allowed_users: set[str] = set()
users_env = _get_env("BALE_ALLOWED_USERS") or ""

# In _handle_update:
if self._allowed_users and user_id not in self._allowed_users:
    logger.info("[bale] Ignoring message from non-allowed user %s", user_id)
    return
```

Env vars: `BALE_ALLOWED_USERS=id1,id2`

### Blocklist Variant

```python
# In __init__:
self._blocked_users: set[str] = set()
blocked_env = _get_env("BALE_BLOCKED_USERS") or ""

# In _handle_update:
if self._blocked_users and user_id in self._blocked_users:
    return  # silent drop
```

Env vars: `BALE_BLOCKED_USERS=id1,id2`

To convert between variants: rename the env var, change the attribute name,
and flip the comparison (`in` → `not in` or vice versa).

## Voice vs Audio Message Types

Bale API sends two distinct audio message types — both should be handled:

```python
elif msg.get("audio"):
    mt = MessageType.AUDIO    # music/audio files
elif msg.get("voice"):
    mt = MessageType.VOICE    # voice messages
```

Do NOT use `MessageType.AUDIO` for voice messages — STT may not trigger.
Both types are passed to the STT pipeline for transcription when configured.

## Group Mention Filter

Optional filter that makes the bot only process @mention or reply-to-bot
messages in groups. Add after allowlist checks, before message type detection:

```python
if chat_type in ("group", "supergroup"):
    bot_mention = f"@{self._bot_username}"
    reply_to = msg.get("reply_to_message", {})
    is_reply_to_bot = (
        str(reply_to.get("from", {}).get("id", "")) == self._bot_id
    )
    if bot_mention.lower() not in text.lower() and not is_reply_to_bot:
        return
```

When active, non-mentioned messages are completely dropped — they never\nenter the session context.\n\n### require_mention with channel_context Buffering (See-All, Respond-Only-When-Called)\n\nA more sophisticated pattern than the simple mention filter: buffer non-mention\nmessages and prepend them as `channel_context` to the next trigger. The bot\nsees full group context but only responds to @mentions/replies.\n\nImplementation:\n\n```python\n# __init__: parse env var + init buffer\n_rm = extra.get(\"require_mention\") or _get_env(\"BALE_REQUIRE_MENTION\")\nself._require_mention = str(_rm).strip().lower() in (\"true\", \"1\", \"yes\", \"on\")\nself._pending_context: dict[str, list[tuple[str, str]]] = {}\n\n# _handle_update: gate + buffer + flush\nchannel_context = None\nif chat_type in (\"group\", \"supergroup\") and self._require_mention:\n    is_mention = bot_mention.lower() in text.lower()\n    if not is_mention and not is_reply_to_bot:\n        self._pending_context.setdefault(chat_id, []).append((user_name, text))\n        if len(self._pending_context[chat_id]) > 50:\n            self._pending_context[chat_id] = self._pending_context[chat_id][-50:]\n        return  # buffer only, no trigger\n    else:\n        buf = self._pending_context.pop(chat_id, [])\n        if buf:\n            lines = [f\"[{un}] {tx}\" for un, tx in buf]\n            channel_context = \"[Earlier group messages]\\n\" + \"\\n\".join(lines)\n\n# Pass to MessageEvent\nMessageEvent(..., channel_context=channel_context, ...)\n```\n\nEnable via: `BALE_REQUIRE_MENTION=true` in `.env`.\n\nThe gateway's `run.py` (line ~12421) prepends `channel_context` before the\n`[New message]` marker, so the bot sees buffered context as prior conversation\nbefore the current trigger.

## Session Sharing

`group_sessions_per_user: false` in config.yaml → all group users share one
session. `true` → each user gets an isolated session.

For a bot that should have full group context awareness, use `false`.

## Hardcoded `extra` Pitfall

The most common silent-gateway failure: `_env_enablement()` hardcodes a value
in `extra` that overrides `.env`:

```python
extra = {"allowed_chats": <OTHER_CHAT_ID>}  # ← silently overrides BALE_ALLOWED_CHATS
```

Because `extra.get("allowed_chats")` is checked first, the `.env` value is
never reached. Fix: comment out or remove the hardcoded line.

## Log Patterns for Filter Debugging

```
[bale] Ignoring message from non-allowed chat X (user=Y)    → chat allowlist
[bale] Ignoring message from non-allowed user X (Name)      → user allowlist/blocklist
```

Both can fire for the same message — chat filter runs first.

## Recommended Production Config

```bash
# ~/.hermes/.env
BALE_ALLOW_ALL_USERS=false
BALE_ALLOWED_USERS=<USER_ID>               # only this user
BALE_ALLOWED_CHATS=<USER_ID>,<GROUP_ID>    # DM + group
```

Group mention filter: enabled (bot only responds when called).
Group sessions: `group_sessions_per_user: false` (shared context).
