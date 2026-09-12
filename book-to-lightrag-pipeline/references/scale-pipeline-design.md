# Scale Pipeline Design — Book→Skill at Volume

Context: 2026-09-11 scale-planning session with the owner. Target volume: dozens of
books per week, continuous. Environment specifics (current model/provider for vision
OCR, mirrors, paths) live in host memory — this file stays parametric by design.

## Decision framework (MCP yes/no)

| Situation | Right shape |
|---|---|
| 1 book now | book-to-skill-ops recipe, direct execution |
| One-shot batch (dozens, once) | CLI + flat state file (book → stage), parallel workers. NO MCP — pure overhead for a one-time run |
| Continuous flow (dozens/week) | pipeline service + thin MCP server so any client can submit/query |

Owner volume = continuous → MCP justified. Agreed tool surface: `submit_book`,
`job_status`, `list_skills` (search optional later).

## Agreed pipeline (continuous flow)

1. **Intake (dual)**:
   - Inbox folder on the host — a new supported file = a new job (watcher or cron scan).
   - Book list (title/author) → auto-download via hermes-libgen-book-download-skill
     (its SKILL.md holds the verified mirror + proxy routing for this network).
2. **Extract**: converter's `scripts/extract.py`, local and free. Empty/short output
   vs page count → treat as scanned, route to OCR.
3. **OCR routing** (host-verified 2026-09-11):
   - Text-layer check FIRST (pdftotext/pymupdf): many "image" PDFs have hidden text.
   - English + Chinese: tesseract 5 (eng, chi_sim installed) — ready.
   - Persian: no tessdata `fas` on host → route via the configured vision-capable
     model, per page or page-group; alternative is installing tesseract-ocr-fas
     (lower quality). Per-page vision OCR cost is separate from generation cost.
   - Host inventory that day: tesseract+pdftotext+pdftoppm+calibre present,
     docling present, ocrmypdf NOT installed (installable on demand), marker-pdf absent.
4. **Generate**: chapter files via flash-class model. `DEPTH=reference` keeps per-book
   cost at the low end for volume runs; study depth multiplies it.
5. **Scan (mandatory in batch)**: `scan_generated_skill.py` on EVERY output — nothing
   is hand-reviewed at volume. Non-zero exit → quarantine, do not install.
6. **Install + state**: move skill into the Hermes skills root, update the state file
   (book → stage), log tokens actually spent per book.

## Weekly report (cron)

Successes / failures (+ reason) / real token spend — read from the state file,
never estimated.

## Rollout order (each layer tested before the next)

1. Single-book CLI end-to-end (a small English technical PDF on disk works as fixture)
2. Queue + inbox watcher
3. List → libgen ingestion
4. MCP layer on top
5. Weekly cron report

## Prototype gate

Before committing to batch economics: run 3–5 REAL owner books and measure pages,
tokens, wall time, and output quality (include at least one Persian book to exercise
the OCR route). Quote weekly cost only from these measurements.

## Prototype data point #1 — Choose Your WoW (2026-09-11, done)

700p English management book, 28 chapters, no OCR needed (text layer present).
Full no-agent run: ~14 min wall, 218K in / 204K out generation tokens (flash-class,
4 workers) + ~19K in / 1.3K out (non-reasoning chat model) for the cheatsheet.
Skill installed as `choose-your-wow`; scan clean AFTER the emptiness check.
See `references/choose-your-wow-noagent-log.md` for the three bugs hit and their
fixes (ToC-vs-heading cutting, reasoning-model token starvation → empty files,
scan-passes-over-empty-files). Formula routing decision (pdftotext vs docling
enrichment vs vision OCR) is now in SKILL.md Pitfalls — next prototype should be
a formula-dense technical book to exercise docling enrichment.

## Retrieval layer decision (2026-09-11, 2 bake-off rounds, owner-approved)

The prototype skill alone couldn't answer cross-chapter/paraphrased questions, so
a retrieval layer was raced over it (full data:
`references/retrieval-bakeoff-2026-09-11.md`). Round 2 (8 questions, two
independent judges, 214-term index) REVERSED round 1's ranking: **knowledge
graph (LightRAG) is the answer engine (quality 7.6, coverage 75%, most stable);
keyword-index+LLM-router demoted to optional cheap pre-router (5.6/62% — router
drifts to generic chapters); regex matching is dead as an answer path.**

Pipeline impact: the per-book build now optionally includes a KG build stage
after generation (entity/relation extraction with retries — budget for it), and
query tooling should route simple cost-sensitive queries through the cheap
pre-router and hard paraphrase questions to the graph. Embeddings are local
(e5-class) by owner rule — never OpenAI/GPT embedding APIs. Any future method
changes must pass the same bake-off gate before adoption: blind paraphrased
questions, golden chapters, ≥2 judges, quality + ctx-tokens + coverage metrics,
results delivered as an image table.
