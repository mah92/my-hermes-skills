# Per-bot avalai API key rotation (tested 2026-08-28)

The bots share ONE avalai key by default, stored per profile in
`~/.hermes/profiles/<name>/.env` under **TWO variables that hold the SAME value**:

- `HERMES_CUSTOM_API_AVALAI_IR_API_KEY` — the LLM key (config.yaml:
  `model.base_url: https://api.avalai.ir/v1`, `model.default: deepseek-v4-flash`,
  `model.provider: custom`, `model.api_key: ${HERMES_CUSTOM_API_AVALAI_IR_API_KEY}`)
- `TAVILY_API_KEY` — avalai's Tavily-compatible web-search key; same `aa-...` string,
  `TAVILY_BASE_URL=https://api.avalai.ir/v1`

**Gotcha**: rotating only the avalai var breaks each bot's web search silently (Tavily
keeps the old key). ALWAYS rotate both vars together per profile.

## Steps (verified end-to-end)

1. **Plan**: the owner supplies `name<space>key` pairs — one per bot, all 14 (names must
   exactly match `~/.hermes/profiles/*` dirs). Verify no missing/extra profiles BEFORE
   writing.
2. **Backup**: copy every `.env` to `/tmp/apikey_backup_<ts>/<name>.env`, then
   `chmod 700` the dir and `600` the files (they contain secrets).
3. **Update in place** (Python, never sed -i blindly — values may contain `=`, `/`, `+`):
   split each line once on `=`, replace the value for BOTH vars where the line starts
   `<VAR>=`; append missing vars at EOF if absent. Preserve `chmod 600` afterward.
4. **Verify before restart**: re-parse the file and assert both vars == expected key;
   print only masked prefixes (`key[:8]..`) — never echo full keys.
5. **Restart** each bot: `docker restart hermes-<name>` (gateway re-reads `.env` at boot).
6. **Live test** a random sample (owner may say «دو تا رو رندوم تست کن» — use `shuf -n 2`):
   `curl -s --max-time 25 -X POST https://api.avalai.ir/v1/chat/completions -H
   "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d
   '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"OK"}],"max_tokens":20}'`
   avalai is reachable DIRECT (no socks proxy); if the direct call times out/empty, retry
   via `--socks5-hostname 127.0.0.1:1080`.
   **Judge the test by HTTP 200 + response shape, NOT content**: deepseek-v4-flash is a
   reasoning model — with `max_tokens: 20` the ENTIRE budget goes to `reasoning_content`
   and `message.content` comes back `""` with `finish_reason: "length"`. That is a PASS.
   A rejected key returns a 401-style error object, not a chat.completion.
7. **Cleanup**: delete any script that embeds the plaintext keys; keep the backup dir
   (masked/mode-600) until the owner confirms, then remove it on request.

## Official Hermes Docker resource guidance (docs, hermes-agent.nousresearch.com/docs/user-guide/docker)

| Resource        | Minimum    | Recommended         |
|-----------------|-----------|---------------------|
| Memory          | 1 GB      | 2–4 GB              |
| CPU             | 1 core    | 2 cores             |
| Disk (data vol) | 500 MB    | 2+ GB                |

Browser automation (Playwright/Chromium) is the most memory-hungry feature: without
browser tools 1 GB suffices; with them allocate ≥2 GB. Security doc also suggests
`terminal.container_cpu: 1`, `container_memory: 5120` MB default in config.yaml.

## Firecrawl stack resource layout (host /home/oem/firecrawl/docker-compose.yaml — do NOT change unless the owner says so)

- `api`: cpus 4.0, mem_limit 8G, memswap_limit 8G
- `playwright-service`: cpus 2.0, mem_limit 4G, memswap_limit 4G
- `redis`, `rabbitmq`, `nuq-postgres`, `foundationdb`: no explicit limits
- `foundationdb-init`: one-shot, `Exited (1)` is by design
- Host box: 4 vCPU (Broadwell VM), 9.7 GB RAM, NO swap. 13→14 bot containers
  exist fleet-wide (each new bot appended by add-bot.sh).
