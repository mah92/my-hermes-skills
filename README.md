<div align="center">

# ﷽

---

**My Hermes Skills** — Collection of Hermes Agent skills maintained by Ali

</div>

## Overview

Composable, lightweight skills for the [Hermes Agent](https://hermes-agent.nousresearch.com/) running on Ali's local Ubuntu box. Each skill is a folder with a `SKILL.md` (and `scripts/` / `references/` when needed) and carries no personal data — values are parameters or placeholders.

## Skills

| Skill | Folder | What it does |
|---|---|---|
| Bot provisioning (Bale / Soroush Plus) | `hermes-bot-provisioning/` | Add or remove a bot on any Hermes host: one profile per bot, its own token/allowlists, gateway as a host systemd user service, optional Hermes-free docker sandbox. Scripts: `add-bot.sh`, `rm-bot.sh`, `verify-bot.sh`, `backup-bot-profile.sh`. |
| Libgen book downloader | `hermes-libgen-book-download-skill/` | Download books from working libgen mirrors: search → metadata → file. |
| Libgen article downloader | `hermes-libgen-article-download-skill/` | Download scientific papers from libgen scimag (Articles chapter). |
| LLM translation | `hermes-translation-skill/` | Translate markdown/text via an LLM API: paragraph-safe chunks, glossary, resumable. |
| Persian video subtitles | `persian-video-subtitle/` | Burned-in/SRT Persian subtitles + Farsi document handling. |
| Chinese video subtitles | `chinese-video-subtitle/` | Chinese film → dual subtitles (Chinese line + Persian). |
| Chinese vocab sheet | `chinese-vocab-sheet/` | Chinese vocab → 2-column study-sheet PDF. |
| Table as image | `table-as-image/` | Render table requests as PNG (RTL/Persian friendly) instead of markdown — for chat clients that mangle tables. |
| Local diffusion model setup | `local-diffusion-model-setup/` | Deploy image/video-gen models locally (FLUX klein) with ComfyUI + MCP. |
| Chinese/English STT | `sherpa-onnx-en-stt/` | Transcribe English audio with sherpa-onnx. |
| NASIR architecture | `nasir-architecture/` | Conventions for the NASIR C++ architecture. |
| Cast to projector | `wanbo-dlna-cast/` | Cast media to a Wanbo projector over DLNA. |
| Media helpers | `media/` | YouTube/media download helpers. |

Self-hosted Firecrawl now lives in its own repository:
`github.com/mah92/hermes-selfhost-firecrawl-skill`.

## Installation

Skills load from `~/.hermes/skills/` (category subfolder). To use one of these:

```bash
cp -r hermes-<skill> ~/.hermes/skills/<category>/hermes-<skill>
```

No other setup required — Hermes picks skills up from its skills directory. Standalone scripts (Libgen, provisioning) are also runnable directly with Python/Bash.

## Network notes (Iran)

- ghcr.io requires VPN for `docker pull` (docker daemon traffic must be tunneled); Docker Hub is reachable directly.
- Working libgen mirrors from this network: `libgen.la`, `libgen.li`; file CDN: `cdnN.booksdl.lc`. Dead here: `libgen.is/.rs/.st/…`

## Project Structure

```
my-hermes-skills/
├── README.md
├── hermes-bot-provisioning/
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── add-bot.sh
│   │   ├── rm-bot.sh
│   │   ├── verify-bot.sh
│   │   └── backup-bot-profile.sh
│   └── references/
│       ├── platforms.md
│       └── sandbox-image.Dockerfile
├── hermes-libgen-book-download-skill/
│   ├── SKILL.md
│   └── scripts/libgen_download.py
├── hermes-libgen-article-download-skill/
│   ├── SKILL.md
│   └── scripts/libgen_article_download.py
├── hermes-translation-skill/
├── persian-video-subtitle/
├── chinese-video-subtitle/
├── chinese-vocab-sheet/
├── table-as-image/
├── local-diffusion-model-setup/
├── sherpa-onnx-en-stt/
├── nasir-architecture/
├── wanbo-dlna-cast/
└── media/
```

## References

- Hermes Agent docs: https://hermes-agent.nousresearch.com/docs/
- Firecrawl self-host guide: https://docs.firecrawl.dev/contributing/self-host
- Libgen mirror status: https://libgen.help/monitor
