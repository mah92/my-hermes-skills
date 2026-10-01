# API Provider Diagnostics for Remote Hermes

Pattern for diagnosing provider API errors (502, 401, connection failures)
on remote Hermes gateway instances.

## Example Error

```
⚠️  API call failed: InternalServerError [HTTP 502]
   Provider: custom  Model: glm-5.2
   Endpoint: https://api.avalai.ir/v1
   Error: HTTP 502 — 502 Bad Gateway
```

## Diagnostic Path

1. Check provider config on remote:
```bash
ssh user@remote "grep -A5 '^model:' ~/.hermes/config.yaml"
```

2. Verify API key env var in running gateway process:
```bash
ssh user@remote 'cat /proc/$(systemctl --user show -p MainPID hermes-gateway | cut -d= -f2)/environ 2>/dev/null | tr "\\0" "\\n" | grep API_KEY'
```
If missing/empty: the systemd service file is not exporting it. 
Check: `grep 'API_KEY' ~/.config/systemd/user/hermes-gateway.service`

3. Test API directly from remote (isolates config issues from API issues):
```bash
ssh user@remote 'curl -s -w "\nHTTP:%{http_code}" \
  https://api.avalai.ir/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY_VAR" \
  -d "{\"model\":\"glm-5.2\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":5}" \
  --connect-timeout 20 --max-time 30'
```

Response codes:
- 200: API works → problem is Hermes config/env
- 401: API key invalid/expired/empty (most common root cause)
- 502: upstream provider down (nothing you can fix; try different model/provider)
- Connection timeout: network/firewall

4. If curl works but Hermes doesn't: env var is set in your SSH session but
   NOT in the systemd service that runs the gateway. systemd has its own env.

## Fix: DO NOT edit the systemd service file — it gets REWRITTEN

**CRITICAL: Hermes gateway rewrites the systemd service file on every start.**
The log shows: `↻ Updated gateway user service definition to match the current Hermes install`.
Any `Environment=` lines you add to the service file will be wiped on the next restart.

### The right fix: embed the API key directly in config.yaml

Instead of referencing an env var that the service file can't reliably hold:
```yaml
# BEFORE (broken — env var missing from systemd)
api_key: ${HERMES_CUSTOM_API_AVALAI_IR_API_KEY}

# AFTER (works — key lives in config, survives gateway restarts)
api_key: sk-abc123...
```

Update with sed directly on the config file:
```bash
ssh user@remote "sed -i 's|api_key: \${ENV_VAR_NAME}|api_key: actual-key-value|' ~/.hermes/config.yaml"
ssh user@remote "grep 'api_key:' ~/.hermes/config.yaml"  # verify
ssh user@remote "systemctl --user restart hermes-gateway"
```

**Why this works:** The gateway does NOT rewrite config.yaml — it only rewrites the
systemd unit file. Config changes persist across restarts.

### Alternative: use a .env file that config.yaml reads

If you must use an env var, set it in `~/.hermes/.env` which the gateway reads at
startup via python-dotenv. But this has its own pitfalls (the agent can't read .env
files directly, and the env var must be set before the gateway starts).

### Verification

After the fix, test the API directly from the remote to confirm:
```bash
cat << 'PYEOF' | ssh user@remote ~/.hermes/hermes-agent/venv/bin/python
from openai import OpenAI
client = OpenAI(base_url='https://api.provider.com/v1', api_key='key')
r = client.chat.completions.create(model='model-name', messages=[{'role':'user','content':'hi'}], max_tokens=10)
print('OK:', r.choices[0].message.content)
PYEOF
```

Always verify the config survived the restart:
```bash
ssh user@remote "head -6 ~/.hermes/config.yaml"

## Testing with realistic payload size

API may return 200 for 5-token tests but 502 for ~6K-token production
requests. Test with padding:
```python
import urllib.request, json
data = json.dumps({
    'model': 'glm-5.2',
    'messages': [
        {'role': 'system', 'content': 'padding' * 3000},
        {'role': 'user', 'content': 'hi'}
    ],
    'max_tokens': 10
}).encode()
req = urllib.request.Request('https://api.avalai.ir/v1/chat/completions',
    data=data, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ...'})
resp = urllib.request.urlopen(req, timeout=60)
print(f'HTTP:{resp.status}')
```

If large requests fail but small succeed → try different model or provider.

### Pitfall: Some models return 502 only with large context

Model `glm-5.2` on api.avalai.ir returned HTTP 200 for small requests (10 tokens)
but consistently returned HTTP 502 for production requests (~6,400 tokens with
system prompt). The model works — the backend just can't handle the large payload.

**Fix:** switch to a proven model. `deepseek-v4-pro` on the same provider worked
reliably for both small and large requests.

```bash
ssh user@remote "sed -i 's/default: glm-5.2/default: deepseek-v4-pro/' ~/.hermes/config.yaml"
# Also update the custom_providers model entry if one exists
ssh user@remote "sed -i 's/model: glm-5.2$/model: deepseek-v4-pro/' ~/.hermes/config.yaml"
ssh user@remote "systemctl --user restart hermes-gateway"
```

### Session Reference

Remote server: <USER>@<OLD_VPS>, provider api.avalai.ir
- Model glm-5.2: HTTP 200 for small requests, HTTP 502 for ~6K token requests
- Model deepseek-v4-pro: HTTP 200 for both small and large requests
- Config path: `~/.hermes/config.yaml` on remote
- Service: `hermes-gateway.service` (user systemd)

## Pitfall: sed with \s through SSH

`sed -i "/pattern/i line"` with `\s*` is unreliable through SSH:
- `\s` is a GNU extension, needs `-E` flag
- Double-quote escaping across SSH layers silently corrupts the pattern
- Command exits 0 but file is unchanged

Always use Python str.replace() for simple insertions through SSH.
Always grep immediately after any sed to confirm the edit landed.

## Real Session Example (Updated)

Remote server: <USER>@<OLD_VPS>, provider api.avalai.ir, model glm-5.2
- Symptom: every agent response got HTTP 502 after 3 retries
- Root cause 1: `HERMES_CUSTOM_API_AVALAI_IR_API_KEY` env var was EMPTY (length 0)
  in systemd service — config.yaml referenced `${HERMES_CUSTOM_API_AVALAI_IR_API_KEY}`
  but the service file had no `Environment=` line for it
- Root cause 2: Editing the systemd service file to add env vars is FUTILE because
  Hermes gateway rewrites the service file on every start
- Root cause 3: After fixing the key (by embedding it directly in config.yaml),
  model `glm-5.2` still returned 502 for ~6K-token production requests
- Final fix: embedded API key directly in config.yaml AND switched default model
  from `glm-5.2` to `deepseek-v4-pro` — both small and large requests work
