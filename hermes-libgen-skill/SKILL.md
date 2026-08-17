---
name: hermes-libgen-skill
description: "Use when downloading a book from libgen (search+get+PDF)."
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [libgen, books, download, pdf, scraping, asimov]
    related_skills: [hermes-selfhost-firecrawl-skill, hermes-agent]
---

# Libgen Download (working flow, verified)

Download books from Library Genesis mirrors that WORK from this network.
Mirror: **libgen.la** (and libgen.li — identical Gen+ app).
Verified end-to-end on 2026-08-17: search → metadata → get-link → PDF to disk
→ send via Bale.

## When to Use
- User asks for a book/PDF/story download (e.g. "download an Asimov book")
- Need search + metadata + actual file from libgen

## Flow (matches the site's real button path)
The site has NO /book/ page (404). Search rows link DIRECTLY to the get-flow:
search page → row's GET button → ads.php?md5=... → page embeds signed
get.php?md5=...&key=... → the signed URL downloads the file.

Run the script (full pipeline, filters by author/format, optional Bale send):
```bash
python3 ~/.hermes/skills/research/hermes-libgen-skill/scripts/libgen_download.py \
  --query "best of asimov" --dry-run      # list candidates only
python3 .../libgen_download.py --query "asimov complete stories" --format pdf --send
```
The script: scrapes the search page (browser UA) → pulls json.php metadata
(locator = "Author - Title.ext") → filters → GETs ads.php with Referer →
extracts get.php signed URL → downloads to ~/Downloads/ → verifies with
`file` + byte-size match → optional --send uploads via Bale sendDocument.

Manual curl equivalent (all one-liners):
```bash
MD5=<md5>  # from json.php metadata
curl -sL -A "Mozilla/5.0" -e "https://libgen.la/" "https://libgen.la/ads.php?md5=$MD5" | grep -o 'get\.php?md5=[^"&]*&key=[^"&]*'
curl -sL -A "Mozilla/5.0" -e "https://libgen.la/" "https://libgen.la/<that get.php URL>" -o book.pdf
```

## Current working mirrors (checklist)
- libgen.la, libgen.li — SERVE REAL APP to browser UAs (nginx default page to
  curl-default UAs — send a browser UA!)
- files served via cdnN.booksdl.lc — reachable from Iran
- DEAD from this network: libgen.is/.rs/.st/.gs, annas-archive.org, z-lib,
  cdn1.booksdl.org. sci-hub.se needs VPN.
- Status page: https://libgen.help/monitor (live mirror list)

## JSON metadata API
GET https://libgen.la/json.php?object=f&ids=<id1>,<id2>,...
- keys: md5, filesize, extension, locator ("path\Author - Title.ext"), time_added
- NO title/author fields — filter on locator string, not on title keys

## Pitfalls (learned the hard way)
- /book/index.php?md5=... → 404 on Gen+ mirrors; book rows link to ads.php
- ads.php + get.php MUST send browser User-Agent AND Referer: https://libgen.la/
- get.php key is per-request and time-limited — fetch ads.php fresh each time
- Some targets refuse scrapers (quotes.toscrape 403) — normal, pick another
- Ad-blocker recommended: Gen+ mirrors are ad-gated (bitcoin/donation links in HTML)
- Search with columns[]=t restricts to Title; default searches all fields
