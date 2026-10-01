# Bale require_mention & group-session Configuration

## require_mention (See-All, Respond-to-Mentions)

When `BALE_REQUIRE_MENTION=true` with `group_sessions_per_user: false`:

```bash
# ~/.hermes/.env
BALE_REQUIRE_MENTION=true
```

```yaml
# ~/.hermes/config.yaml
group_sessions_per_user: false
```

The bot receives ALL group messages (must be admin for Privacy Mode off),
buffers non-mention messages silently, and only triggers agent response on
@mentions or replies. DM messages always trigger response.

## `\n` String Literal Pitfall in Adapter Edits

When editing adapter.py via Python that inserts `\n` inside string literals:

```python
# WRONG — \n becomes actual newline, breaking the string:
new_code = '''channel_context = "[Earlier group messages]\n" + "\n".join(lines)'''
# Result: SyntaxError: unterminated string literal

# RIGHT — double-escape:
new_code = '''channel_context = "[Earlier group messages]\\n" + "\\n".join(lines)'''
```

Always verify: `python -c "from plugins.platforms.bale.adapter import BaleAdapter; print('OK')"`

## Channel Context Flow

1. Non-mention messages collected in `_pending_context[chat_id]` (max 50)
2. On mention/reply, buffer flushed as `channel_context` field on MessageEvent
3. Gateway run.py prepends `channel_context` before trigger text (line ~12421):
   ```python
   if getattr(event, "channel_context", None):
       message_text = f"{event.channel_context}\n\n[New message]\n{message_text}"
   ```

## Session Key Patterns

- DM: `agent:main:bale:private:<chat_id>:<user_id>` (chat_id == user_id)
- Group shared: `agent:main:bale:group:<chat_id>`
- Group per-user: `agent:main:bale:group:<chat_id>:<user_id>`
