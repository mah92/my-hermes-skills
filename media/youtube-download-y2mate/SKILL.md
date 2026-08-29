---
name: youtube-download-y2mate
description: "Use when y2mate download requested or yt-dlp fails."
version: 2.0.0
author: نصیر علی Agent
license: MIT
metadata:
  hermes:
    tags: [youtube, y2mate, download, captcha, turnstile, proxy, 403, socks]
---

# YouTube Download via y2mate (and the real fix when it fails)

## When to Use

- The user asks to download a YouTube video and explicitly says "با y2mate".
- Direct yt-dlp fails (HTTP 403, downloads skipped, no formats).
- The target site is unreachable through the SOCKS proxy while other sites
  still work (single-host filtering symptom).

## Portability rules (MUST)

This skill must work on ANY Linux server with a Hermes agent. Everything
environment-specific is parameterized — never hardcode paths, chat IDs, host
names, service names or ports:

- `PROXY_HOST` (default `127.0.0.1`), `PROXY_PORT` (default `1080`).
- `OUT_DIR` (default `$HOME/Downloads/yt`) — always `mkdir -p "$OUT_DIR"` first.
- Delivery target {token, chat_id} from the environment / current session —
  see the Delivery section; NEVER bake a chat ID or token into the skill.
- The SOCKS tunnel service name differs per machine (e.g. `vpn-proxy`,
  `tunproxy`, `openfortivpn@*`). Discover it with
  `systemctl list-units --type=service | grep -iE 'vpn|proxy|tun'`, never
  assume `vpn-proxy` exists.

## Step 0 — is the proxy alive?

```bash
systemctl is-active <tunnel-service>        # if a tunnel service exists at all
curl -s -x "socks5h://$PROXY_HOST:$PROXY_PORT" -o /dev/null -w '%{http_code}'
     -m 20 https://api.ipify.org/           # IP-echo = tunnel answers
```

If the proxy does not answer at all → the tunnel is down; fix the tunnel first
(this skill is not a VPN-repair guide; see the box's network/VPN skill for tunnel repair).

## Diagnosis — single-host filtering vs dead tunnel

```bash
# target check
curl -s -x "socks5h://$PROXY_HOST:$PROXY_PORT" -o /dev/null -w '%{http_code}' \
     -m 20 https://www.youtube.com/
# control hosts (choose 2-3 you know are reachable through the proxy in YOUR
# region — a search engine, an IP-echo, a CDN)
for h in https://www.google.com/ https://api.ipify.org/; do
  printf "%s -> " "$h"
  curl -s -x "socks5h://$PROXY_HOST:$PROXY_PORT" -o /dev/null -w '%{http_code}\n' -m 20 "$h"
done
```

Interpretation:

- TARGET = `000` AND control hosts = `200` → the proxy is alive but its egress
  NODE filters/geo-blocks the target. This is a per-node filter, not a dead
  tunnel.
- TARGET = `000` AND control hosts = `000` → the tunnel itself is dead — fix
  the tunnel, do not retry the target yet.
- TARGET = `200` → the proxy is fine; if yt-dlp still 403s, go straight to the
  Download section (android client).

The egress node can change between connections; a single `000` is often
temporary — never conclude "broken" from one probe.

## The fix — swap the egress node

If the tunnel is alive but the target is filtered, reconnect the tunnel to
get a different egress node (only if the agent has permission and a service
owns the tunnel):

```bash
sudo systemctl restart <tunnel-service>     # service name discovered in Step 0
sleep 45
# re-probe: target + control hosts — expect target back to 200
```

Retry loop (do not give up after one attempt): up to 3 restarts with 45s
waits, re-probing after each. If the target stays `000` after 3 tries, report
honestly («تولیدکننده/نود اگریس در دسترس نیست») and offer to retry later —
do not keep hammering.

## Prerequisites

- `yt-dlp` installed AND updated: `yt-dlp -U` (the android-client flags and
  the SABR-related warnings only exist in recent versions).
- `ffmpeg` available if re-encoding is needed.
- `sudo` working for the tunnel restart (if a restart is attempted).
- Write access to `$OUT_DIR` (create it).

## Download (yt-dlp, android client)

```bash
export PROXY_HOST=${PROXY_HOST:-127.0.0.1} PROXY_PORT=${PROXY_PORT:-1080}
export OUT_DIR=${OUT_DIR:-"$HOME/Downloads/yt"}
mkdir -p "$OUT_DIR" && cd "$OUT_DIR"

# probe first (title/duration make the choice transparent)
yt-dlp --proxy "socks5://$PROXY_HOST:$PROXY_PORT" \
  --extractor-args "youtube:player_client=android" \
  --skip-download --print "%(id)s | %(title)s | %(duration)s s" "URL"

# download, 360p mp4 by default (small, compatible)
yt-dlp --proxy "socks5://$PROXY_HOST:$PROXY_PORT" \
  --extractor-args "youtube:player_client=android" \
  -f "b[ext=mp4][height<=360]/b[height<=360]/b" \
  -o "vid_%(id)s.%(ext)s" "URL"
```

- yt-dlp proxy: `socks5://` (no `h` — yt-dlp resolves through the proxy's DNS
  with `socks5://` when the proxy supports it; use `socks5h://` if your local
  DNS is broken/poisoned — test once and keep the form that works locally).
- curl proxy: `socks5h://` (remote DNS; safer when local DNS is broken).
- WARNING «Some android client https formats have been skipped as they are
  missing a URL» = YouTube's SABR experiment on the current session — NOT
  fatal; the fallback formats in `-f` still download.
- If formats fail: add `--format-sort "res:360,ext:mp4"` or lower to
  `height<=144`; as a last resort re-encode to shrink for delivery
  (see Delivery cap).

## Verify

```bash
cd "$OUT_DIR"
ls -lh vid_*.mp4
file vid_*.mp4          # expect "ISO Media, MP4" (any v1/v2 marker)
# sanity: duration of the downloaded file vs the probe's printed duration
ffprobe -v error -show_entries format=duration -of csv=p=0 vid_*.mp4
```

## Delivery

- Load the platform messaging skill (e.g. `bale-direct-api` / `bale-operations`)
  for the exact endpoint + token source — do not guess.
- The bot token lives in the agent's environment / `.env` (`BALE_BOT_TOKEN` or
  platform equivalent) — never hardcode it.
- The chat id is the CURRENT session's chat, or the env-provided target
  (`BALE_CHAT_ID`) — never bake a fixed id into the skill.
- Keep the file size under the platform's upload cap (Bale: ~50MB observed).
  If it exceeds the cap: `ffmpeg -i in.mp4 -vf "scale=-2:360" -c:v libx264
  -crf 30 -preset veryfast -c:a copy out360.mp4` (or re-download at 144p).
- Keep a copy in `$OUT_DIR` — a temp dir may be wiped on reboot.

## y2mate anatomy — WHY it is usually captcha-walled (observed 2026-08-29)

Modern y2mate (e.g. en2.y2mate.is/x510/) loads Cloudflare **Turnstile**
(`challenges.cloudflare.com/turnstile/v0/api.js`) and:

1. POST `/getdata` JSON `{url, "cf-turnstile-response": token}` with an
   `X-CSRF-TOKEN` header (token in the page `<meta name="csrf-token">`).
   Without a token → `{"error":true,"message":"Something went wrong"}`.
2. Polls POST `/getconvert` JSON `{id, format}` until `progress==100` and a
   `download` URL is returned.
3. The old classic route POST `/mates/convertV2` was removed by the time of
   observation (`{"message":"The route mates/convertV2 could not be found."}`).

Mirror domains (y2mate.is/.nu/.gratis/.pm/.cm/.guru) sit behind the same
Turnstile wall. Without a headless browser able to solve Turnstile, minting
the token is not possible — do NOT burn cycles trying to bypass it; use
yt-dlp instead. NOTE: y2mate's structure changes often — if the endpoints
above stop matching, treat this section as dated history and re-inspect
`assets/js/convert.js` on the live site.

## Pitfalls

- Probe MULTIPLE hosts before concluding anything (one `000` proves nothing).
- Never `pkill -f` a long-running daemon by its path for teardown — use
  port-based teardown (`fuser -k <port>/tcp`) ONLY when you are sure the port
  belongs to the service, or the service's own stop command.
- Keep control-plane traffic (LLM providers, your messaging API hosts) DIRECT,
  outside the tunnel, if your network policy requires it — route only the
  blocked destinations through the proxy.
- Don't assume the tunnel egress is any particular country; egress IPs change
  per connection and per node.
- If the skill's own instructions no longer match reality (site changed,
  tunnel renamed), say so and adapt — do not fabricate.

## Related

- `youtube-video-download` — extra yt-dlp details (fresh-upload search,
  format selection).
- The box's VPN/proxy skill — tunnel repair and egress anatomy.
