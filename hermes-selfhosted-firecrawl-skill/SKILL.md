---
name: hermes-selfhost-firecrawl-skill
description: "Use when self-hosting Firecrawl or pulling its 3 images."
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [firecrawl, docker, self-host, web, ghcr, iran, hermes]
    related_skills: [gateway-restart, hermes-agent]
---

# Firecrawl Self-Host (prebuilt images)

Self-hosting Firecrawl as the Hermes web backend using the OFFICIAL PREBUILT
images. Never build from source — the build downloads Chrome for Testing which
is blocked on this network (Iran), and no mirror reliably has the exact
revision.

## When to Use
- Firecrawl containers missing after reboot / user wants Firecrawl running
- Need `docker pull` of the 3 official images (ghcr.io is blocked without VPN)
- Hermes web backend should point at a self-hosted Firecrawl

## The 3 images (ghcr.io/firecrawl)
```bash
docker pull ghcr.io/firecrawl/firecrawl:latest          # API (search + scrape + crawl)
docker pull ghcr.io/firecrawl/playwright-service:latest # JS rendering
docker pull ghcr.io/firecrawl/nuq-postgres:latest       # postgres + pg_cron
```
Redis, RabbitMQ, FoundationDB pull normally from Docker Hub.

## Iran/VPN caveat
- ghcr.io is NOT reachable for docker from this box without VPN.
- The VPN must cover the DOCKER DAEMON traffic (tunnel-all mode, not a
  browser-only proxy) or `docker pull` still fails.
- If the VPN is a LOCAL SOCKS5 proxy (e.g. tunproxy listening on
  127.0.0.1:1080), point the daemon at it via /etc/docker/daemon.json
  (requires `systemctl restart docker`):
```json
{ "proxies": { "http-proxy": "socks5://127.0.0.1:1080",
               "https-proxy": "socks5://127.0.0.1:1080",
               "no-proxy": "localhost,127.0.0.1,::1" } }
```
  Verify with `docker info | grep -A2 Proxy`.
- Docker Hub IS reachable (base images fine). `dl.google.com` also reachable.
- Flaky tunnels interrupt big pulls mid-layer. NEVER rely on `docker compose
  up` to pull — it aborts and re-pulls everything every time. Pull each image
  in a retry loop until `docker images` shows it, then `up` once:
```bash
for img in redis:alpine rabbitmq:3-management foundationdb/foundationdb:7.3.63 \
           ghcr.io/firecrawl/firecrawl:latest \
           ghcr.io/firecrawl/playwright-service:latest \
           ghcr.io/firecrawl/nuq-postgres:latest; do
  for a in $(seq 1 60); do docker pull $img >/dev/null 2>&1 && break; sleep 4; done
done
```
  Completed layers cache, so repeated attempts converge.
- Pitfall: `pkill -f "compose up"` over SSH matches your OWN remote shell
  (exit 255). Use `pgrep -f "cli-plugins/docker-compos[e]"` to kill compose.

## Docker-compose changes (required once, before first `docker compose up`)

The official docker-compose.yaml comes with `build:` ACTIVE and the image lines
COMMENTED OUT. Flip all three so it runs the prebuilt images (no source build):

```yaml
# x-common-service (api) — was:
#   image: ghcr.io/firecrawl/firecrawl
#   build: apps/api
# now:
  image: ghcr.io/firecrawl/firecrawl:latest
  # build: apps/api

# playwright-service — was:
#   image: ghcr.io/firecrawl/playwright-service:latest
#   build: apps/playwright-service-ts
# now:
    image: ghcr.io/firecrawl/playwright-service:latest
    # build: apps/playwright-service-ts

# nuq-postgres — was:
#   image: ghcr.io/firecrawl/nuq-postgres:latest
#   build: apps/nuq-postgres
# now:
    image: ghcr.io/firecrawl/nuq-postgres:latest
    # build: apps/nuq-postgres
```
Also create `.env` in the compose project dir (api stays unauthenticated on
the trusted LAN — generate a strong POSTGRES_PASSWORD):
```
USE_DB_AUTHENTICATION=false
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<32+ random chars>
POSTGRES_DB=postgres
```

## Does it need to clone firecrawl?

NO for runtime. With the image lines active, NOTHING from the source tree is
used at runtime — only docker-compose.yaml + .env + the 5 pulled images
(3 ghcr + redis/rabbitmq/foundationdb). You need the compose file only:
- keep an existing checkout (`/home/oem/firecrawl`, pinned v2.11.162) and use
  it as the compose project dir, or
- copy `docker-compose.yaml` (+ .env) to any folder — `docker compose up -d`
  works from there, and the checkout can be deleted.
git clone is only needed to OBTAIN docker-compose.yaml (it is not shipped
separately). Pin a release tag (`git checkout v2.11.162`) so the compose
contract matches the images.

## Bring the stack up (after the compose flip)
```bash
cd /home/oem/firecrawl && docker compose up -d
```

## Hermes wiring
~/.hermes/.env (add):
```
FIRECRAWL_API_URL=http://localhost:3002
```
API key NOT needed when self-hosted with USE_DB_AUTHENTICATION=false; leave
any cloud FIRECRAWL_API_KEY line commented out.

~/.hermes/config.yaml (set via `hermes config set`, never hand-edit):
```yaml
web:
  backend: firecrawl
  use_gateway: false   # only if not using the Nous Tool Gateway
```

## Verify
```bash
docker images | grep firecrawl                                # 3 images present
curl --silent http://localhost:3002/v0/health/readiness       # {"status":"ok"}
docker compose ps                                             # services up
# Hermes-side check (shows which backend is active):
cd ~/.hermes/hermes-agent && source venv/bin/activate
python -m tools.web_tools          # expect: Web backend: firecrawl (http://localhost:3002)
# functional test through Hermes:
python -c "import asyncio; from tools.web_tools import web_extract_tool; \
print(asyncio.run(web_extract_tool(urls=['https://example.com'], char_limit=2000)))"
```
Restart the gateway (`~/.hermes/scripts/kill-gateway.py`, scheduled via `at` if
run from inside a gateway session) for live sessions to pick up the backend.

## Pitfalls (all learned the hard way)
- NO official images on Docker Hub (devflowinc/firecrawl-simple, mendableai
  — all gone). ghcr.io/firecrawl/* is the only official source.
- Compose file has the image lines COMMENTED OUT and `build:` active — flip
  them before `up` if you ever re-clone: uncomment `image:` + comment `build:`
  for api, playwright-service, nuq-postgres.
- `docker compose build` does NOT pass host env vars into Dockerfiles —
  PLAYWRIGHT_DOWNLOAD_HOST recipes never worked because of this.
- azureedge.net for playwright browsers redirects BACK to blocked
  prss.microsoft.com. npmmirror has old revisions only (1181 ok, 1208 missing).
- Auth: local quickstart uses USE_DB_AUTHENTICATION=false — fine on trusted
  LAN only; enable auth before exposing port 3002.
- @firecrawl/mcp-server (stdio) is a CLIENT, not the engine — it still needs
  a running Firecrawl instance; pointless for self-host.
