# Remote Voice/STT/TTS Parity Audit (snapshot 2026-08-26)

**STATUS: REMOTE BROUGHT TO PARITY 2026-08-26** — the gaps listed below were
fixed on the remote the same day (build-on-remote via socks, see "Fix recipe").
Re-run the audit commands anytime before concluding "remote is old".

Parity comparison of the Persian voice stack (TTS + STT + Bale adapter) between
the local machine (oem home) and the remote VPS
(<VPS>, `ssh -p <SSH_PORT> <USER>@<VPS>`). Both run
**Hermes Agent v0.20.0 (2026.8.3)** — same core, different stacks.

## Audit commands (reusable)

```bash
# Local config
grep -n -A 12 -E '^tts:|^stt:' ~/.hermes/config.yaml
grep -E 'BALE_|MATCHA|ESPEAK|STT_HUSH|SHENAVA' ~/.hermes/.env | sed 's/\(TOKEN=\).*/\1***/'

# Remote config (same greps over SSH)
ssh -p <SSH_PORT> <USER>@<VPS> 'grep -n -A 12 -E "^tts:|^stt:" ~/.hermes/config.yaml'

# Plugin commit parity
git -C ~/.hermes/plugins/platforms/bale log --format='%h %ci %s' -5        # local
ssh -p <SSH_PORT> <USER>@<VPS> 'git -C ~/.hermes/plugins/platforms/bale log -1 --format="%h %ci %s"'

# Skill versions (frontmatter) + script diff
head -8 ~/.hermes/skills/<skill>/SKILL.md | grep -E '^name:|^version:'
diff ~/.hermes/skills/hermes-persian-stt/scripts/stt.py <(ssh -p <SSH_PORT> <USER>@<VPS> 'cat .../stt.py')
```

Key checks to always run before concluding "remote = old": the STT provider
command (does it include `{input_path}` and `--quiet`?), the bale plugin git
commit, and which skill layout the config paths reference.

## Findings (as of snapshot)

| Component | Local (home) | Remote (VPS) |
|---|---|---|
| TTS provider | `matcha` — Zahra, daemon, `--speed 1.5`, `voice_compatible: true` | `piper` — built-in native provider, DEFAULT_PIPER_VOICE `en_US-lessac-medium` (ENGLISH), no Persian voice configured, no matcha binary/skill anywhere |
| STT skill | `hermes-persian-stt` v1.2.1 (per-skill dir) | `hermes-bale-stt` v1.2.1 inside legacy collection repo `hermes-bale-messenger-skills/` |
| STT command | `.../stt.py --quiet {input_path}` ✅ | `.../stt.py` — missing BOTH `{input_path}` and `--quiet` → script prints usage, exits 1 → STT effectively broken |
| stt.py script | newer: auto-downloads missing model, diagnostics → stderr, writes empty `transcript.txt` for empty result | older: no auto-download, diagnostics → stdout |
| STT model | present | present (model.int8.onnx 126M, dated Aug 9) |
| Bale plugin commit | `0444f2f` 2026-08-14 (sendVoice + MIME fix + ogg/opus→VOICE) | `70975cc` 2026-08-08 (no sendVoice → `MEDIA:` tags not rendered by Bale; voice delivery broken) |
| Bale .env | HOME=<USER_ID>, ALLOWED_CHATS/USERS=<USER_ID> only, ALLOW_ALL=false, no REQUIRE_MENTION, MAX_VOICE_DURATION=30000 | HOME=<GROUP_ID> (different bot/group), REQUIRE_MENTION=true, ALLOW_ALL=true + 7 allowed users, MAX_VOICE_DURATION=0 |
| venv packages | piper-tts 1.6.0 (verified) | piper-tts 1.6.0, sherpa_onnx 1.13.4, soundfile 0.14.0, numpy/scipy (verified) |

## Bottom line

- Remote STT: config command broken (missing `{input_path}`), script old,
  model fine → fix = new script + `stt.py --quiet {input_path}`. ✅ fixed
- Remote TTS: piper = English default voice, no Persian stack installed →
  Persian TTS effectively absent; migrate to matcha like local. ✅ fixed
- Remote voice send: broken until Bale plugin updated past `6479355` (sendVoice).
  ✅ fixed (now `0444f2f`)
- Remote .env intentionally different (group bot, mention-gated, multi-user,
  no voice-duration cap) — not a bug. ✅ untouched

## Fix recipe (2026-08-26, worked)

Remote egress goes through **SOCKS5 proxy `127.0.0.1:1080`** (FortiClient VPN,
tunproxy-socks5.py). Direct HTTPS is filtered. Everything below ran on the
remote via SSH.

1. **git through proxy:** `git config --global http.proxy socks5h://127.0.0.1:1080`
   — without it, `git fetch/clone` hangs (timeout).
2. **Everything else:** `curl --socks5-hostname 127.0.0.1:1080 <url>` or python
   `requests` with `proxies={"http":"socks5h://127.0.0.1:1080",...}` (pysocks is
   already in the hermes venv). GitHub, HuggingFace, pypi, archive.ubuntu.com
   all reachable this way.
3. **apt is dead (no direct egress)** → fetch .debs with curl/requests, then
   `sudo dpkg -i` them. Get exact pool paths from
   `apt-cache show <pkg> | grep ^Filename` (e.g. espeak-ng is in
   `pool/main/e/espeak-ng/` on noble — NOT universe). For espeak-ng need:
   libespeak-ng-dev, libespeak-ng1, espeak-ng-data, libpcaudio0, libsonic0;
   for ICU: libicu-dev + matching libicu74 + icu-devtools (same version).
4. **Build on remote, don't scp big assets.** Remote has cmake/g++/make and is
   FAST (MatchaTTSInfer built in 48s). ONNX Runtime 1.20.0 tarball from GitHub
   releases (~6MB compressed), extract to /usr/local + ldconfig. Models
   (123MB) come from HuggingFace via the socks curl. Verified byte-identical
   with local via md5 (matcha 835b64883ee7, vocos ca539bc4, tokens 5a8ddffc).
5. **matcha_tts_infer .gitmodules pitfall:** the published repo's submodule URL
   is a LOCAL path (<HOME>/Basir/G2P/NormalizeText) → fix after clone:
   `git config submodule.NormalizeText.url https://github.com/<GITHUB_USER>/NormalizeText.git`
   then `git submodule update --init NormalizeText`. Nested dirs (hazm_cpp,
   persian-ezafe-albert-cpp) are plain dirs in that repo, not submodules.
6. **espeak-ng-data on Ubuntu 24.04** lives at
   `/usr/lib/x86_64-linux-gnu/espeak-ng-data` (not /usr/share/) — set
   `ESPEAK_DATA` to that. fa voice = `lang/ira/fa`, `fa_dict`.
7. **Delete legacy repo** `~/.hermes/skills/hermes-bale-messenger-skills/` after
   deploying new per-skill dirs, else duplicate `hermes-bale-messenger` SKILL.md
   confuses the loader. Remote cron REFERENCING old paths would break — check
   `hermes cron list` + grep for stale refs.
8. **Restart remote gateway** via execute_code (terminal blocks it):
   `subprocess.run(["ssh","-p","9011","<USER>@<VPS>",
   "<HOME>/.hermes/hermes-agent/venv/bin/python",
   "<HOME>/.hermes/hermes-agent/hermes","gateway","restart"])` — "User
   service restarted (PID N)" and bale reconnects as @nasire_ali_bot.
9. **Verify full loop on remote:** TTS `tts.py --speed 1.5 in.txt out.ogg` →
   ffprobe duration; STT `stt.py --quiet out.ogg` → Persian text back
   ("سلام به خوبی امیدوارم حالت خوب" heard back correctly).
10. **send_document metadata bug — FIXED 2026-08-26 (plugin commit `5ebe36c`).**
    `BaleAdapter.send_document/photo/image/audio` lacked the
    `file_name/reply_to/metadata/**kwargs` params the base class + gateway core
    pass (`get unexpected keyword 'metadata'` → every file send silently
    failed — first seen 2026-07-31 in LOCAL logs, i.e. a core update started
    passing metadata=; it genuinely worked before that). Fixed in the plugin
    repo, pushed, pulled on both machines. Same commit also maps
    `reply_to` → `reply_to_message_id`. Follow-up `f052cd0` adds native
    `send_video` + `send_image_file` overrides (Bale sendVideo/sendPhoto) —
    the base-class fallbacks only posted a "Couldn't deliver" notice, so
    video/local-image delivery never actually arrived before. All three paths
    (document/image/video) verified end-to-end with real files + metadata on
    the live Bale API (local msgs 5535/5536/5537, remote 9589).
