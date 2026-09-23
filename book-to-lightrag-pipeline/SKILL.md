---
name: book-to-lightrag-pipeline
description: "Use when building, querying or operating kg_* LightRAG graphs: batch book→skill→graph pipelines, local embeddings, the lightrag-mcp server and its kg-query/kg-ask/kg-add-book CLI, and with/without-book eval reports."
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [books, skills, lightrag, embeddings, batch, ocr]
    related_skills: [book-to-skill, hermes-libgen-book-download-skill]
---

# Book-to-LightRAG Pipeline (batch conversion + knowledge-graph layer)

Companion to the **book-to-skill** converter (single manual runs). This skill covers the
*automation layer*: turning dozens of books per week into installed skills with plain
scripts — no agent loop — plus execution discipline, validation gates, the retrieval
bake-off, and the knowledge-graph (LightRAG) layer. Consolidated 2026-09-12 from the
former `book-to-skill-pipeline` + `book-to-skill-ops` skills.

## When to Use

- User asks for batch/weekly book→skill conversion ("چند ده کتاب در هفته")
- A single-book conversion must run unattended (cron/watcher) or be parallelized
- Debugging why generated skill files are empty, unscanned, or low quality
- Building or querying LightRAG graphs over generated skills
- Producing "answer with and without the book" eval reports (incl. Persian PDFs)

## Architecture (validated end-to-end on a 700-page book)

1. **Acquire** — libgen download (see libgen skill). Ensure the target download
   directory exists first; the downloader fails with bare `FileNotFoundError`
   otherwise (not a clear "no such dir" message).
2. **Extract** — converter's `extract.py --mode text|technical` (local, free).
   Only scanned PDFs need OCR. This box has tesseract langs eng/fas/osd (there is no chi):
   use `fas` for Persian scans, and keep vision-model OCR only for pages where fas fails.
3. **Cut chapters** — heading-anchored slices of `full_text.txt`. Keep the LAST
   regex match per chapter heading: ToC lines match first and would empty every slice.
4. **Generate chapters** — per-chapter LLM calls from a script (concurrency 4):
   prompt extracts *structure* (named frameworks, decision rules, anti-patterns),
   never summaries; output language = book language (EN book → EN skill).
5. **Master files** — SKILL.md + glossary + patterns + cheatsheet from the chapters.
6. **Gates** — file-size check, security scan, then install into `~/.hermes/skills/`.

Real run numbers (Choose Your WoW, 28 chapters, glm-5.3-flash): ~14 min total;
218K in / 204K out tokens for chapters; masters + ~20K more (partly on a
non-reasoning fallback model). ExO + Playing to Win run: deepseek chapter gen
27/27, 260K tokens, 64s. Expect roughly half to one dollar of API tokens
per 500–700-page book at flash-model rates.

## Execution discipline (ops lessons from real runs)

- **Confirm extraction, don't re-extract.** Read the run's `metadata.json`
  (`pages`, `words`, `estimated_tokens`, `workdir`). If `estimated_tokens > 50_000`,
  treat `full_text.txt` as a queryable corpus — never a whole-file read.
- **Probe with grep/sed/wc** before any generation: `wc -w full_text.txt`;
  `grep -n -E "^CHAPTER [0-9]+"`; `head -c 8000` for title/author/ToC. Chapter
  ranges = `[heading_line, next_heading_line - 1]`; verify body headings by sed-ing
  a few lines after each heading — ToC titles and body headings can differ.
- **Analysis packs keep context proportional to output:** per chapter write a scratch
  pack (heading + first ~85 lines + glossary block), read packs in groups of 2–3,
  generate that group's chapter files immediately.
- **WRITE VERIFICATION — critical pitfall.** Bulk `write_file` is not trustworthy
  until confirmed on disk: in a real run, 24 calls reported `verified: true` but
  landed in a filesystem overlay later discarded — files silently gone. Preferred:
  `execute_code` with `pathlib.write_text` + read-back `assert read_text() == content`
  per file, print the on-disk count after every batch; batches of ~5. If you use
  write_file, verify per batch with `search_files (target='files')` — never at the end.
- **Token estimation without a tokenizer:** `words × 1.33` (conservative upper bound;
  trim until under budget by this measure) and `chars / 4` (prose estimate). Code-heavy
  text runs ~3.5–3.8 chars/token. Run `scripts/estimate_tokens.py <skill-dir>` for a
  per-file table.
- **Load the `book-to-skill` skill and read its `tools/scan_generated_skill.py` rules BEFORE writing content** (approximate):
  real files not symlinks; valid UTF-8; no invisible Unicode codepoints; no
  "you are now" / "ignore previous instructions" / "disregard the system" /
  `<system>` tags / chat-template delimiters (`<|im_start|>`, `[INST]`); exfiltration
  shape = one line containing both a network verb (`curl|wget|send|post|upload`) and a
  secret word (`.env|base64|secret|credential|api key`) — don't pair those in prose;
  frontmatter: no `allowed-tools`, no `disable-model-invocation: false`. Composing
  with these in mind beats fixing 25 files after. Run the scan LAST; non-zero exit →
  STOP and report, do not silently rewrite. Publish (git/GitHub) only on explicit
  request; copyrighted-book derivatives stay private.
- **The scanner silently PASSES empty files** — it checks patterns, not emptiness.
  ALWAYS `wc -c` master files before trusting a scan; also `wc -c` caught a mid-run
  crash leaving a valid SKILL.md beside three empty support files. Do not regenerate
  non-empty files (skip semantics), only the empty ones.
- **Cleanup via metadata, never a guessed path:** delete the `workdir` recorded in
  the run's `metadata.json` (per-run, PID-suffixed) — another extraction may be
  running beside yours.

## Retrieval layer on top of a book skill (FINAL after round 2, 2026-09-11)

Chapter files alone don't let an agent find cross-chapter answers. Two bake-off
rounds (blind questions paraphrased away from the book's wording; round 2 = 8
questions, TWO independent judges averaged — single-judge rankings flip between
rounds); full data in `references/retrieval-bakeoff-2026-09-11.md`.

| Method | R1 quality | R2 quality (2 judges) | R2 coverage | Build cost |
|---|---|---|---|---|
| A · regex keyword match | 5.3 | 6.3 | 31% | $0 |
| C · keyword index + LLM router (owner's design) | 6.7 | 5.6 | 62% | ~$0.03 |
| D · knowledge graph (LightRAG) | 8.5 | **7.6** | **75%** | minutes + retries |

**Decision (owner-approved, round-2 verdict):** Method **D (knowledge graph) is the
answer engine** — the only paraphrase-proof method and the most stable across harness
hardening. C is an optional cheap pre-router for cost-sensitive/simple queries;
bigger indexes and more chapters did NOT fix its router-drift failure mode (picks
generic front-matter chapters on ~25% of questions). Regex-only (A) is dead as an
answer path.

- **Bake-off discipline (owner-demanded, before adopting ANY retrieval design):**
  blind paraphrased questions + fixed golden chapters + ≥2 independent judges +
  metrics = answer quality, context tokens, golden-chapter coverage. Present results
  as an IMAGE (table-as-image pattern), never a markdown table in the messaging platform. Get owner
  sign-off on numbers before wiring a layer in.

## Knowledge-graph enrichment layer (LightRAG)

Chapters = depth layer ("read"), graph = find layer ("locate across books").
Chosen direction: LightRAG — incremental insert (new books merge into the same
graph without rebuild), pluggable LLM, local-embedding capable. **User hard rule:
embeddings must come from a local model (e.g. HF), never GPT/OpenAI.**

LightRAG 1.5.7 installed from PyPI (`lightrag-hku`), unpatched; integration through the
official plugin interfaces only: extraction LLM `deepseek-chat` via `openai_complete_if_cache`;
embeddings local, wrapped with lightrag's own `EmbeddingFunc` and e5 `query:`/`passage:`
prefixes (`kg_common.py:build_rag`). The current default is `intfloat/multilingual-e5-small`
(384d, the fa+en benchmark winner, `server.py:_model_for`); a graph keeps whatever model its
`meta.json` pins, so older graphs still run on `intfloat/multilingual-e5-base` (768d) or
`heydariAI/persian-embeddings`. The historical bake-off used a hand-rolled async wrapper
(`wrap_embedding_func_with_attrs`) — that recipe lives in `references/kg-embedding-local.md`.

Graphs built: kg_ptw (698 ent / 879 rel), kg_exo (336/386), kg_merged (1703/2222);
query tests 6/6 passed (hybrid + mix). Build shape: per-chapter md files → `ainsert`
batch; expect per-doc timeouts → retry passes (purge non-processed doc_status, re-
ainsert; a `dup-*` doc-id class appears after retries — purge by id prefix only
after confirming the real `doc-*` entry is processed). The build/query scripts live in
`~/lightrag/ins-nav/` (`kg_build.py`, `kg_add_new.py`, `kg_purge.py`, and `kg_q.py`, which is now
only a compatibility shim forwarding to `kg-query`). The old scratch dir
`~/booktest/` (`kg_index.py`, `local_embed.py`, `compare3.py`, `kg_multihop_test.py`, …) NO LONGER
EXISTS, so the eval-run recipes are historical: re-derive them with the current `kg-query`/`kg-ask`
CLI instead of the old script names.

**Querying:** `kg-query "<question>" -g <graph> -m naive` — pure vector search,
works with a dummy LLM func (no LLM cost). `hybrid` needs a real LLM for two-level
keyword extraction (hl/ll keywords; local=entities, global=topics). Cap retrieved
context to ~12K chars before handing to an answering model.

## Eval runs ("answer X with and without the book")

Validated pattern (drone-company strategy questions, 2026-09-11):

1. Fetch context per question: `kg-query "<question>" -g <graph> -m naive`.
2. Answer with DIRECT deepseek-chat calls (~5K tokens per answer, <15s).
   Do NOT deliver long inline context through delegate_task/subagents — the
   hosted model's 90s non-streaming timeout kills every such run (failed 7x
   across providers); control runs with short prompts are fine as delegates.
3. FAIRNESS RULE (user requirement): control (no-reference) and treatment
   (with-graph) runs MUST use the identical model, temperature, and prompt
   skeleton. Never compare answers produced by different models — the user
   rejected such a comparison and ordered a full re-run.
4. Log a per-answer ledger (latency_s, prompt/completion/total tokens) and put it
   IN the deliverable report next to each answer — user expects time/token cost
   per question, not aggregate.
5. Observed contrast (deepseek-chat, same settings): no-ref answers borrow
   the famous book's framework from pretraining but drift (renamed MTP as
   "modularization principle"), stay generic, and cite nothing; with-graph
   answers follow the book's exact template, cite [ref N] per claim, surface
   advanced concepts (ExO Lite + edge-ExO, Haier ZZJYTs, Institutional Yes,
   EQ dashboard, six telltale signs/traps filters), and flag own inferences
   «استنتاج من». Cost: ~4K extra input tokens, ~6s extra per answer.

Deliverable recipes (scripts + templates in references):

- Eval-run recipe: `references/kg-eval-runs.md`
- Report FORMAT rules (verbatim questions, verbatim answers, per-answer cost
  banners — user corrected all three): `references/eval-report-format.md`
- Persian PDFs: reportlab cannot shape RTL glyphs. Working stack = hand-written
  RTL HTML (Vazir font via file://$HOME/.fonts/vazir/, dir=rtl) rendered with
  weasyprint (pip-installed into the hermes venv). Verify rendering by rasterizing
  pages and inspecting with vision. `references/persian-pdf-report.md`
- Tutorial/explainer PDFs (e.g. "short LightRAG tutorial") are a separate
  deliverable class: step-by-step mechanism section, graphviz diagrams (binary
  via apt required; rankdir=LR for Persian labels), novice-safe wording with a
  glossary — user corrected all three at once. `references/lightrag-tutorial-pieces.md`

## No-Agent Generation Mode (verified, full 28-chapter run)

At volume you do NOT run generation through a chat agent — a plain script calls the
LLM API directly (works under cron, no session context burned). Parallel per-chapter
generation (ThreadPoolExecutor, 3–4 workers): 28 chapters in ~9.5 min. Cost gate:
extraction is free; generation is the whole bill. Owner rule: an English book yields
an ENGLISH skill — no translation.

**Reasoning-model token trap (empty files + cost):** reasoning models burn the
`max_tokens` budget on `reasoning_content` before writing `content`. At
max_tokens=4000–6000 with long prompts, one provider repeatedly returned
`finish: length, content_len: 0, reasoning_len: ~17K` → **zero-byte master files**.
Defenses (all verified):
- Instrument every response: log `finish_reason`, `content_len`, `reasoning_len` —
  a 200 OK is not success (same trap applies to graph builds: verify graphml/vdb
  content, not doc_status counts).
- Chunk inputs so each call needs less output (a glossary succeeded in ~45-term
  parts after the whole-book prompt failed 3× in a row).
- Non-trivial content gate: reject + retry when `content < 200–400 chars`.
- Route compact high-density artifacts (cheatsheet) to a non-reasoning chat model.

**Infra notes:** generation scripts need `requests`+`PySocks` and the socks route
(no separate skill for it: the proxy is `ALL_PROXY=socks5h://127.0.0.1:<port>`); run with the venv python that has `requests`+`PySocks`. Target dir must exist
before download-to-disk (a missing `~/Downloads` failed every attempt as
"No such file or directory" after each fresh signed URL).

## Formula-bearing (technical) books

`pdftotext` mangles equations. Decision tree:
- formula-sparse book → text mode (fast, free);
- formula-dense → Docling technical mode (installed; enable
  `do_formula_enrichment` for LaTeX output — off by default in the converter),
  ~1.5 s/page budget; truly hard pages → vision-model OCR per page.
The generation prompt must include "do not rewrite LaTeX" so chapters keep formulas.

### Install shape (one venv, one package, then a skill)

`mah92/lightrag-mcp` -> `./install.sh` puts the MCP server AND the CLI in ONE venv
(`kg-mcp`, `kg-query`, `kg-ask`, `kg-add-book`). Never split them across two interpreters: that is
how `lightrag` went missing while `kg_create`/`kg_list` kept working — **whichever venv runs a
`kg-*` entry point needs `lightrag` + `mcp<2` + `torch` + `pymupdf`**.

Path story (one line, no confusion): `install.sh` creates `~/.hermes/lightrag-mcp-venv` by
default and `LIGHTRAG_MCP_VENV=<path>` overrides it; the pre-existing install on this box lives in
`~/.hermes/mcp-venv`, which is what `hermes mcp add` registered — so run checks as
`LIGHTRAG_MCP_VENV=~/.hermes/mcp-venv ./install.sh --check`. Registration either way:
`hermes mcp add lightrag-kg --command <venv>/bin/kg-mcp`, or the form this box uses,
`--command <venv>/bin/python --args <repo>/src/lightrag_kg_mcp/server.py`. The skill itself is the
operating manual and stays in the skills collection; persona/profile glue (persona name, persona
text, chat ids, graph choice — e.g. the profile-local persona shim) stays OUT of both repos, on
the profile side, as a thin shim over `kg-ask`.

- **Canonical names (one operation, one name):** MCP tools use underscores, the CLI the same name with
  hyphens. `kg_query`/`kg-query` = retrieve context only (no answer LLM — cheap, safe for grounding);
  `kg_ask`/`kg-ask` = retrieve + answer with `[ref N]` citations (add `--persona-file`/`--name` for a
  persona); `kg_add_book`/`kg-add-book` = PDF -> skill md -> graph (long: `background=True` + `kg_jobs`);
  `kg_create`, `kg_jobs`, `kg_add_markdown`, `kg_add_repo`, `kg_register`, `kg_delete`, `kg_list`,
  `kg_setup` are MCP-only (no CLI);
  `kg-mcp` is the server itself. Legacy names in older notes: `kg_q.py`/`kg_fetch_context.py` ->
  `kg-query`, `kg_answer.py`/`kg_book.py` -> `kg-ask`/`kg-add-book`.
- **Skill-first install on a fresh machine:** install ONLY the skill; it drives the repo (never vendor
  code into a skill). Verified end to end 2026-09-23 against the published `v0.2.1`:
  1. install/copy this skill (`hermes skills install mah92/my-hermes-skills/book-to-lightrag-pipeline`
     or copy the folder into `~/.hermes/skills/`);
  2. clone the pinned release — both repos are PUBLIC, so HTTPS needs no key:
     `git clone --depth 1 --branch v0.2.1 https://github.com/mah92/lightrag-mcp.git && cd lightrag-mcp && ./install.sh`
     (override the venv with `LIGHTRAG_MCP_VENV=...`; ~1.7 GB with the CPU torch wheel);
  3. ASK THE USER FIRST — `hermes mcp add lightrag-kg --command <venv>/bin/kg-mcp` edits config.yaml;
  4. verify: `./install.sh --check`, then `<venv>/bin/kg-query "test" -g <graph>`;
  5. build or register a graph: `<venv>/bin/kg-add-book <graph> <pdf>` / `kg_register`.

  Rehearsed twice on this box in throwaway venvs (since removed): v0.2.0 with a cold pip cache
  (~6.5 min, 1.7 GB with the CPU torch wheel) and v0.2.1 with the cache warm. Both runs: HTTPS clone
  of the tag -> `install.sh` -> `--check` OK (lightrag 1.5.7, mcp 1.30, pymupdf, four console
  scripts, tiktoken cache) -> `kg-query` returned ~26-30K chars of context -> `kg-mcp` served 11
  tools and `kg_list` saw kg_nav. Nothing needs a key or a running Hermes to pass those steps; only
  the MCP registration writes config.yaml.
- **`tiktoken` tries to download its BPE file from an Azure blob that this box cannot route to**
(`openaipublic.blob.core.windows.net` — a 15 s curl from here never answers, and Python raises
errno 101; LightRAG builds the tokenizer at load time, so the whole process dies). The fix is
`TIKTOKEN_CACHE_DIR=~/.cache/tiktoken_cache`, which `kg_common.py` sets **on import, but only when
that directory already exists** — so a fresh machine must populate the cache (a network that can
reach the blob does it with `TIKTOKEN_CACHE_DIR=~/.cache/tiktoken_cache python -c "import tiktoken;
tiktoken.get_encoding('o200k_base')"`; `install.sh` attempts exactly that and warns if it cannot).
- **Long book jobs: `kg_add_book(..., background=True)`** returns a job id at once (log +
`job.json` under `~/lightrag/jobs/<id>/`, poll with the `kg_jobs` tool, the state file survives an
MCP restart). The job body is `kg_add_book.py`, which is resumable — an existing extraction, an
already-generated skill and PROCESSED documents are all skipped, so a crash costs only the gaps.

## MCP server (lightrag-mcp / `lightrag-kg`) — what breaks and how to reload

Source of truth: `~/lightrag/kg_mcp/repo` (git, `mah92/lightrag-mcp`,
`src/lightrag_kg_mcp/server.py`); `~/lightrag/kg_mcp/server.py` is a plain copy — mirror it
after every edit.

All 11 tools (`hermes mcp test lightrag-kg` prints exactly this list). CLI = same name with hyphens,
present only where the operation is useful outside an agent:

| tool | what it does | use it when | CLI |
|---|---|---|---|
| `kg_query` | retrieve context only, no answer LLM | grounding, cheap probing, feeding another model | `kg-query` |
| `kg_ask` | retrieve + answer with `[ref N]` citations | an answer in the graph's own words | `kg-ask` |
| `kg_add_book` | PDF → skill markdown → graph (`background=True`) | ingesting a book/paper | `kg-add-book` |
| `kg_add_markdown` | insert markdown text/file/dir directly (`replace=`) | one note, or refreshing a doc | — |
| `kg_add_repo` | repo → arc42 doc + its reference PDFs → graph | code/document repos | — |
| `kg_register` | register an existing graph kept outside `~/lightrag/kg` (`root`) | adopting a graph built elsewhere | — |
| `kg_create` | create an empty graph (+ its embedding model) | starting a new topic domain | — |
| `kg_list` | graphs, embedding model, doc count | first call in a session | — |
| `kg_jobs` | background job state, doc counts, log path | after `kg_add_book(background=True)` | — |
| `kg_delete` | remove a graph (external data needs `delete_data=true`) | retiring a graph, never a live one | — |
| `kg_setup` | pre-download embedding models, verify the environment | fresh install, new model | — |

- **It runs on `~/.hermes/mcp-venv` (python3.11 + `mcp<2`), not the hermes venv.** That venv
drifted once and silently lost `lightrag` → every graph tool died with ModuleNotFoundError,
while kg_create/kg_list (no lightrag import) kept working and masked it. Required there:
`lightrag-hku==1.5.7` + `openai`. Diagnose with
`~/.hermes/mcp-venv/bin/python -c "import lightrag, tiktoken, openai"`.
- **Never `asyncio.run()` inside an MCP tool.** FastMCP calls sync tool functions on the event
loop thread → "asyncio.run() cannot be called from a running event loop" broke kg_ask,
kg_add_book, kg_add_repo for every caller. Tool functions that await LightRAG must be
`async def` and await directly.
- **Reload without a gateway restart.** After editing server.py, SIGKILL the lightrag MCP child
(`pgrep -f lightrag_kg_mcp`): the gateway respawns it on the next tool call with the new file +
venv. Verify with `hermes mcp test lightrag-kg` (prints the live tool list; in the gateway venv it is
`~/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main mcp test lightrag-kg`) and with
`kg_create` (its `embedding_model` reveals which revision is running).
- **Do not SIGKILL by cmdline substring from a shell/heredoc** whose own text contains that
substring (e.g. `lightrag_kg_mcp` in the heredoc) — the loop matches its own process and kills
it (exit -9). Match the server path and skip `os.getpid()`/ppid. The terminal tool also blocks
`systemctl restart hermes-gateway-*`, so gateway restarts are the user's call (`kill-gateway.py`
handles the default profile only).
- **A graph that lives elsewhere is registered, not symlinked.** The server's `BASE` is
`~/lightrag/kg`, so a graph built at e.g. `~/lightrag/ins-nav` is invisible to it. Use
`kg_register(name, root)`: `meta.json` under `~/lightrag/kg/<name>/` gets `"root": <abs path>` and
every tool resolves `<root>/graph` + `<root>/inputs`. Symlink wrappers still work but are the hack.
`kg_delete` on such a graph removes only the registry entry unless `delete_data=true` (never nuke a
graph that lives outside BASE by accident).
- **Pipeline helpers are resolved beside server.py, then `~/lightrag/kg_mcp`.** The repo copy of
`generate_skill.py` once drifted stale behind the live one and contained three real bugs: it crashed
with no `~/.hermes/.env`, its chapter prompt never included the extracted TEXT chunk, and it
rewrote files that already existed (regenerating a good chapter after a retry). Whenever a pipeline
fix is made, sync both locations AND commit it to the repo — the live copy alone is invisible to git.
- **Chapter boundaries come from the PDF, not a regex.** `make_sections.py <pdf> <extract_dir>`
writes `sections.json` from PDF bookmarks (levels 1/2, auto-titles for machine-named bookmarks,
then printed-ToC lines); `kg_add_book` now runs it before `generate_skill.py`, which prefers
`sections.json` and only falls back to the `"Chapter N"` regex. The regex alone yielded 2 of 10
chapters for a 681-page book.
- **`kg_add_book` blocks the MCP call for the whole run** (20-30 min was one observed book; the
code's limits are a 4 h timeout on generation and insert, 1 h on pdftotext/make_sections —
`server.py:272`, `kg_add_book.py:58,65,83`). Pass `background=True`, or run `<venv>/bin/kg-add-book`
directly, so the MCP server stays responsive; both are resumable (only basenames without a
PROCESSED doc_status row are inserted).
- **`kg_add_markdown(graph, markdown|md_path, doc_name, replace)` semantics:** inline text or a
`.md` file/dir; stored as `<name>.md` under `<graph>/inputs/`. LightRAG's doc_id is
`md5(canonical stored path)` plus same-basename dedup (`lightrag/pipeline.py`), so re-inserting the
same file is a no-op and changed content would otherwise keep the OLD copy alongside the new one:
`replace=True` first deletes the documents whose stored `file_path` basename matches (LightRAG keeps
basenames, not full paths) — that is the way to refresh a changed doc.

## Verification (run this before trusting the system)

1. `LIGHTRAG_MCP_VENV=<the venv that runs the server> ./install.sh --check` → must end
   `OK: install looks healthy` (lightrag+mcp+pymupdf imports, four console scripts, DEEPSEEK key).
2. `hermes mcp test lightrag-kg` → connects, lists the 11 tools above.
3. `kg-list` equivalent: `kg_query -g <graph> "..." ` must resolve `<graph>` (registry + root) —
   or call the `kg_list` tool; a missing graph is the usual symptom of a wrong `~/lightrag/kg` entry.
4. `kg-query "<question>" -g <graph> -m naive` → prints `graph_dir:` + `=== CONTEXT (N chars) ===`.
   If it raises a tiktoken connection error, the tokenizer cache is missing (see the tiktoken note).
5. For background work: `kg_jobs` shows state running/done plus `docs_inserted`; the log is
   `~/lightrag/jobs/<id>/job.log`.

## Pitfalls (each one actually bit this session)

1. **Reasoning models burn `max_tokens` on thinking.** Symptom: HTTP 200,
   `finish_reason: length`, `content` empty or tiny, `reasoning_content` huge.
   The file gets written as 0 bytes. Fixes: log content_len AND reasoning_len on
   every call and retry on empty content; chunk large jobs; fall back to a
   non-reasoning chat model for master files.
2. **The security scanner silently PASSES empty files.** Always gate on
   `wc -c` BEFORE scanning and before installing.
3. **Duplicate `.env` keys with empty values.** A first `KEY=` line shadows the
   real one. When parsing `.env` in scripts: skip lines whose value `.strip()`
   is empty instead of taking the first match.
4. **GLM flash API quirks:** `reasoning_effort` accepts only low/high/max —
   `medium` returns HTTP 400 code 1210. Script calls should set it explicitly.
5. **Proxy:** outbound script traffic needs `ALL_PROXY=socks5h://127.0.0.1:<PROXY_PORT>`
   (and `HTTPS_PROXY` for HF downloads). Run scripts with the hermes venv python
   (requests + PySocks available there). Exception: deepseek-chat direct (no
   proxy) works — api.deepseek.com needs no PySocks.
6. **Validate slice sizes before spending tokens:** skip/generate-with-warning for
   chapter slices under ~300 words; log per-chapter word counts in the state JSON.
7. **Merged-graph filename collisions.** LightRAG 1.5.7 derives doc_id from
   the canonical BASENAME and dedups by filename within one ainsert batch.
   Two books both containing `ch04.md` collide -> the whole merged insert
   becomes "no new unique documents" and silently writes nothing. Fix: give
   each source unique basenames per book (e.g. `ptw__ch04.md`, `exo__ch04.md`).
8. **A `kg-*` script must run on an interpreter that has lightrag+torch+pymupdf** — not
   any python. On this box that is `~/.hermes/mcp-venv` (the same one the MCP server runs on);
   `~/.hermes/hermes-agent/venv` is the legacy fallback in `kg_common.py` (`HERMES_PY`), and
   system `python3` has no torch at all. Picking an interpreter because of its path instead of
   probing the imports is what produced the two-venv drift above.
9. **OOM (on the old 9.7 GB VM; this box has 30 GB):** LightRAG's default concurrency (4)
   with e5 embeddings got the process SIGKILLed (exit 137). 2/2 is now the code default
   (`kg_common.py:build_rag`), so nothing needs setting by hand. Incremental insert resumes after crashes
   (docs keep processed status; failed docs retried on re-run).
10. **Cross-contamination of bookkeeping stores after crashes** — kv_store_*
    can contain foreign doc rows after OOM-killed runs, but graphml+vdb (the
    query layer) stayed clean. Verify purity via graphml marker greps before
    shipping; don't trust doc_status counts alone.

## References

- `references/retrieval-bakeoff-2026-09-11.md` — full retrieval-layer data: both bake-off rounds (A/C/D), dual-judge reversal, LightRAG build pains + retry/dup-status fix, multi-hop evidence, local-embedding setup
- `references/kg-embedding-local.md` — local embedding setup, model comparison, validated integration snippets
- `references/kg-eval-runs.md` — eval-run scripts and worked example
- `references/eval-report-format.md` — deliverable report format rules
- `references/persian-pdf-report.md` — RTL PDF recipe (fonts, weasyprint, the messaging platform delivery)
- `references/lightrag-tutorial-pieces.md` — reusable blocks for tutorial PDFs
- `references/choose-your-wow-noagent-log.md` — no-agent generation run log: ToC-vs-heading cutting bug, reasoning-model empty-output trap, silent-scan hole, real numbers
- `references/scale-pipeline-design.md` — volume architecture: MCP decision framework, dual intake, OCR routing, prototype gate (Choose Your WoW = first prototype data point)
- `references/think-python-2-generation-log.md` — worked example: full 21-chapter run (packs → batches → scan → cleanup), file inventory, overlay-loss incident + recovery
