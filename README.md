<div align="center">

# ﷽

---

**My Hermes Skills** — Collection of Hermes Agent skills maintained by Ali

</div>

## Overview

Composable, lightweight skills for the [Hermes Agent](https://hermes-agent.nousresearch.com/) running on Ali's local Ubuntu box. Each skill lives in its own folder, is self-contained, and covers one concern. Skills are kept minimal by design: no bundled dependencies, no cross-repo coupling.

## Skills

| Skill | Folder | What it does | Usage |
|---|---|---|---|
| Self-hosted Firecrawl | `hermes-selfhosted-firecrawl-skill/` | Self-host Firecrawl as the Hermes web backend (search + scrape + crawl) using the 3 official prebuilt ghcr images — no source builds | `docker pull ghcr.io/firecrawl/firecrawl:latest` + 2 more (see SKILL.md) |
| Libgen downloader | `hermes-libgen-skill/` | Download books from working libgen mirrors: search → metadata → signed get-link → PDF in ~/Downloads, optional Bale delivery | `python3 hermes-libgen-skill/scripts/libgen_download.py --query "best of asimov"` |

## Installation

Skills load from `~/.hermes/skills/` (category subfolder). To use one of these:

```bash
cp -r hermes-<skill> ~/.hermes/skills/<category>/hermes-<skill>
```

No other setup required — Hermes picks skills up from its skills directory. The Libgen script is also runnable standalone (Python 3 stdlib only).

## Network notes (Iran)

- ghcr.io requires VPN for `docker pull` (docker daemon traffic must be tunneled); Docker Hub is reachable directly.
- Working libgen mirrors from this network: `libgen.la`, `libgen.li`; file CDN: `cdnN.booksdl.lc`. Dead here: `libgen.is/.rs/.st/.gs`, `annas-archive.org`, `z-lib`, `booksdl.org`.

## Project Structure

```
my-hermes-skills/
├── README.md
├── hermes-selfhosted-firecrawl-skill/
│   └── SKILL.md
└── hermes-libgen-skill/
    ├── SKILL.md
    └── scripts/
        └── libgen_download.py
```

## References

- Hermes Agent docs: https://hermes-agent.nousresearch.com/docs/
- Firecrawl self-host guide: https://docs.firecrawl.dev/contributing/self-host
- Libgen mirror status: https://libgen.help/monitor
