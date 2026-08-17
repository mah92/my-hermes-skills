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
- Docker Hub IS reachable (base images fine). `dl.google.com` also reachable.

## Bring the stack up
```bash
cd /home/oem/firecrawl && docker compose up -d
```

## Verify
```bash
docker images | grep firecrawl                                # 3 images present
curl --silent http://localhost:3002/v0/health/readiness       # {"status":"ok"}
docker compose ps                                             # services up
```
Hermes side: `FIRECRAWL_API_URL=http://localhost:3002` in ~/.hermes/.env,
`web.backend: firecrawl` in config.yaml.

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
