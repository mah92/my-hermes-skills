---
name: wanbo-dlna-cast
description: "Use when casting media to the Wanbo projector over DLNA."
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [wanbo, dlna, upnp, projector, android-tv, cast, smart-home]
    related_skills: [lg-webos-tv-control]
---

# Wanbo DLNA Cast (UPnP AV Renderer)

Cast video files to the Wanbo projector (Android, EShare renderer) on the home
LAN without ADB. Works even with no developer options and ADB off.

## When to Use
- User wants to play a video/movie on the Wanbo projector from the Linux box
- Control (play/pause/stop/volume) of the Wanbo renderer
- Identify which device on the LAN is the Wanbo

## Device facts (verified 2026-08-26)
- Wanbo T4, Android 9.0 (per device.report / manuals.plus), IP 192.168.1.103
- DLNA stack: EShare/1.0.4.2, friendlyName "EShare-6313", model "AV Renderer
  Device", manufacturer "EShare Technology Corporation" (China Dragon WiFi OUI)
- **The HTTP port for the UPnP description is DYNAMIC** — seen on 2002 and
  1726 at different times. NEVER hardcode it: rediscover via SSDP each time.
- SSDP responds on UDP 239.255.255.250:1900 (multicast). mDNS returned nothing
  (multicast may be filtered; don't rely on it).
- Network ADB port 5555 is CLOSED (debugging off). Dev options on the T4:
  Settings → About → tap "Software version" 7-10x (the T4 has no "Build
  number" row). ADB only matters if the user wants shell control.

## Steps: cast a file to the projector

1. Ensure the projector is ON (SSDP answers only when it is). Test:
   `ping -c2 192.168.1.103`
2. Discover the current control endpoint:
   `python3 scripts/discover.py`
   → prints LOCATION + AVTransport controlURL (dynamic port).
3. Serve the media from this box with the Range-capable server:
   `python3 scripts/range_server.py [DIR]`   # default /tmp/dlna_cast_serve
   Copy the video into that dir. NOTE: python3 -m http.server is NOT enough
   — it has no Range support and the EShare renderer aborts the stream.
4. Cast:
   `python3 scripts/cast.py http://192.168.1.108:8000/movie.mp4 "Movie Title"`
   (or `python3 scripts/cast.py /path/movie.mp4 "Title"` — copies into serve
   dir and builds the URL itself; own IP is auto-detected)
5. The script polls GetTransportInfo; expect state=PLAYING with advancing
   RelTime. When the clip ends the state returns to STOPPED.
6. Control afterwards: `python3 scripts/control.py volume`, `volume 30`,
   `mute`, `status`, `stop`, `pause`, `play`.

## Casting to the LG webOS TV (192.168.1.104, DLNADOC/1.50)
The LG needs a DIFFERENT SOAP payload than the Wanbo. Use scripts/cast_lg.py:
`python3 scripts/cast_lg.py <file|url> ["Title"] [tv_ip]`
- LG replies ONLY to unicast SSDP → discovery inside cast_lg.py sends the
  M-SEARCH straight to the TV IP (multicast is ignored by this TV).
- Rejects plain `s:Envelope` SOAP with UPnP error **714 "Illegal MIME-type"**
  (despite any protocolInfo string). The payload that works (learned via a
  Wireshark-verified nano-dlna fork on Stack Overflow Q 51728337):
  - `SOAP-ENV:` prefix, `xmlns:dt="urn:schemas-microsoft-com:datatypes"` with
    `dt:dt="ui4"` on InstanceID and `dt:dt="string"` on URI/meta args
  - `<res>` WITHOUT protocolInfo, `restricted="0"`, XML-escaped DIDL-Lite
    with `xmlns:dlna` and `<upnp:class>object.item.videoItem</upnp:class>`
- The LG validates the URL with HEAD before SetAVTransportURI — 501 on HEAD ⇒
  error 716 "Resource not found" (fixed by the HEAD support in range_server.py).
- GetTransportInfo/GetPositionInfo give full playback feedback (state/position).
- RenderingControl GetVolume/GetMute did NOT answer on this LF6300 — don't
  rely on volume queries for LG; AVTransport state is the feedback channel.
- Old LG sink list is limited: MP4 named profile only AVC_MP4_BL_CIF15_AAC_520
  plus wildcards; a 640x360 H.264 Constrained Baseline + AAC + faststart file
  played fine. If 704 "format not supported" appears at Play time, re-encode
  smaller/baseline first.

## Media requirements (learned the hard way)
- Container: MP4, H.264 High + AAC stereo up to 720p worked (tested 640x360
  and re-encoded 1280x720). Very likely 1080p fine too.
- **faststart strongly recommended**: re-encode with
  `-movflags +faststart` if the play aborts. The 7.6MB Blender Sintel trailer
  as-downloaded FAILED (went black, connection reset at ~2s, position stuck
  at 00:00:00) until re-encoded to the same specs with faststart.
- If a play aborts instantly: check `GetPositionInfo` (stuck at 0) and the
  serve-dir log — look for "Connection reset by peer" during streaming.

## Pitfalls
- Dynamic UPnP port: rediscover every session (scripts/discover.py).
- **Multicast SSDP can be ignored: some renderers (e.g. the LG webOS TV at
  .104, model LF6300, DLNADOC/1.50) reply ONLY to a UNICAST M-SEARCH sent
  directly to their IP:1900.** scripts/discover.py falls back to unicast when
  a target IP is given: `python3 scripts/discover.py 192.168.1.104`.
- Do not use stock `http.server`; Range support is mandatory (renderer sends
  `Range:` and expects 206; it reset the connection when we returned 200-only).
- **Serve HEAD too: some renderers (LG webOS) first validate the URL with a
  `HEAD` request — a 501 there makes them reject the cast with UPnP error 716
  "Resource not found".** scripts/range_server.py handles HEAD/OPTIONS.
- LG webOS specifics: replies only to unicast SSDP; RenderingControl
  GetVolume/GetMute did NOT answer on LF6300 (AVTransport state works fine;
  only volume queries failed — treat volume reporting as unsupported there).
- EShare occasionally resets one range request AFTER getting what it needs —
  harmless as long as the state keeps PLAYING and position advances.
- Users see a short black flash when the renderer switches input — normal.
- First test: use a small clip (e.g. 10s ffmpeg testsrc) to validate the
  pipeline before downloading a real movie.
- Download source that worked direct (Iran-friendly): download.blender.org
  (Big Buck Bunny, Sintel trailer — open movies). YouTube works only via
  proxy/VPN on this network.

## Scripts in this skill
- scripts/discover.py — SSDP M-SEARCH MediaRenderer:1 → LOCATION + controlURL
- scripts/range_server.py — tiny HTTP server WITH Range (206) support
- scripts/cast.py — SetAVTransportURI + Play + status polling (self-contained
  discovery; takes file path or URL + title)
- scripts/cast_lg.py — LG webOS variant: unicast discovery + dt:dt SOAP
  payload + HEAD-tolerant server requirement
- scripts/control.py — GetVolume/SetVolume/Mute/Stop/Pause/Play/Status
