# Retrieval Bake-off — Choose Your WoW! (2026-09-11)

Full session data behind the "Retrieval Layer" section of SKILL.md.

## Setup
- Skill under test: `~/.hermes/skills/choose-your-wow/` (28 chapters, 700p book).
- Knowledge graph (method D): LightRAG 1.5.7, working dir `booktest/kg/`,
  final state 28/28 docs processed, 2,979 entities / 4,504 relations,
  vdb stores: entities 2974 / relations 4504 / chunks 236 (768-dim, e5-base local).
- LLM for extraction/routing/answers/judging: deepseek-chat. Embeddings: local
  `intfloat/multilingual-e5-base` (e5 prefixes query:/passage:), 768d.
  Also validated `heydariAI/persian-embeddings` (better separation on FA tests,
  worse cross-lingual); e5 chosen for FA+EN future books.
- 6 blind questions, deliberately paraphrased away from book vocabulary
  (e.g. "we keep fixing the same problems and nothing improves" → target
  chapter ch24 Evolve WoW / GCI — zero word overlap). Golden chapters fixed
  per question from book structure. Judge: separate deepseek call, SCORE n/10.

## Results (per-method averages over 6 questions)
- Full-book baseline context: 104,832 tokens/question.
- A regex keyword match (70-term index, no LLM): quality 5.3, ctx 9.0K,
  coverage 0%, 1.6s. Zero coverage = every paraphrase question missed.
- C keyword index + LLM router: quality 6.7, ctx 11.9K, coverage 83%, 2.8s.
  Index build = free (regex over bold terms/headings), router call trivial.
- D LightRAG hybrid: quality 8.5, ctx 14.6K, coverage 75%, 4.6s.
  Highest quality; two questions where C underperformed scored 8+ on D.

## Build-cost reality (method D)
- First pass: 3/28 processed, 25 failed with 402 Insufficient Balance.
- After key replacement: timeouts killed several docs per pass; needed TWO
  additional retry passes (concurrency 4, timeout 240s) to reach 28/28.
- Retry artifact: `dup-*` doc-ids appear alongside real `doc-*` ids in
  kv_store_doc_status.json after a reset+reinsert; a doc can show BOTH
  'processed' (real) and 'failed' (dup). Fix: keep only `doc-*` entries with
  status=processed, delete everything else, verify per-FILE status (one file →
  one processed entry) before trusting the count.
- Silent-failure trap: `pass done in 0.0s` + "No new unique documents were
  found" means ainsert skipped everything because failed statuses remained —
  purge first, then insert.

## Multi-hop evidence (why the graph wins quality)
Query "Our big program is drowning in dependencies between teams" returned
entities Dependency Risk + Cross-Team Dependencies (defined in ch07, used in
ch23) — cross-chapter synthesis no single chapter file provides. The keyword
router reached only ch23.

## Files (session working dir <WORKDIR>/booktest/)
- method_a_keywords.py — builds keyword_index.json (70 terms → chapters), matcher
- compare3.py — full harness: methods A/C/D + answering + judging + summary
  (requires QueryParam import at module level; CHAPTER_FILES needs both full
  slug and 'chNN' alias keys because the keyword index uses short codes)
- local_embed.py — custom async embedding func + wrap_embedding_func_with_attrs
- kg_index.py / kg_retry2.py / kg_retry3.py / kg_clean_status.py — indexing + retry passes
- kg_status.py / kg_check*.py — status/verification probes
- infographic/compare_table.png + render_table.py — results table image
  (sent via platform sendPhoto + sendDocument)

## Owner preferences encoded in this work
- No OpenAI/GPT embeddings — local model (e5/heydariAI class) is a hard rule.
- English book → English skill, no translation.
- Explain technical mechanisms in plain language first, numbers second
  ("ساده‌تر بگو" after a jargon-heavy explanation).
- Tables/charts for comparison results are sent as images, not markdown.

## Round 2 (2026-09-11, later same day): 210-term index, 8 questions, dual judges

Owner-directed hardening: bigger keyword index, let method C include MORE text,
repeat the whole comparison to rule out noise, then a full table image.

Changes vs round 1:
- Index: 70 → 214 terms (bold terms + headings + capitalized noun-phrases;
  per-chapter coverage min 5). Method C allowed 4 chapters instead of 3
  (~15.3K ctx vs 11.9K). 2 NEW harder questions (estimates wrong+angry
  stakeholders → ch04/ch11; department handoffs killing lead time → ch02/ch19).
- Judging: TWO independent judges — deepseek-chat AND glm-5.3-flash (avg).
  GLM judging needs `reasoning_effort="low"` (medium → HTTP 400 code 1210) and
  max_tokens≈1200 with content gate; at max_tokens=200 GLM returned
  finish:length + empty content 3× (reasoning ate the budget).

## Results (round 2, avg of 2 judges, 8 questions)

| Method | Quality | Ctx tokens | Golden coverage |
|---|---|---|---|
| A · regex (210 terms) | 6.3 | 9.6K | 31% |
| C · index + LLM router (4 ch) | 5.6 | 15.3K | 62% |
| D · knowledge graph | 7.6 | 15.8K | 75% |
| FULL BOOK baseline | — | 104.8K | 100% |

Key readings:
- Bigger index did NOT fix C. Its failure mode is **router drift**: on 2/8
  questions the router picked generic front-matter chapters (ch01-03) instead
  of the specific target. More index terms ≠ better routing; the drift is in
  the router prompt/decision, not keyword recall.
- C got WORSE round-over-round (6.7→5.6) while the harness got harder —
  its 6.7 in round 1 was partly luck (single judge, easier mix).
- D was the most STABLE method across rounds/harness hardening
  (8.5→7.6 with dual judges) and the only one scoring 9/9 on the hardest
  paraphrase question ("same problems over and over" → ch24 GCI).
- A alone improved with the bigger index (0%→31% coverage) but remains
  non-viable; regex match on 'nothing improves' still hit ch02/ch01, missed ch24.
- Judge disagreement itself is signal: e.g. C on Q1 scored 1 (DS) vs 3 (GLM);
  D on Q7 8 vs 4 — always run ≥2 judges for accept/reject decisions at 0.3-level
  differences.

## REVISED pipeline decision (supersedes round-1 "C default, D optional")
Round 2 reversed the round-1 ranking: **D (knowledge graph) is the answer
engine** — the only paraphrase-proof method, stable across rounds. C stays as
an OPTIONAL cheap pre-router for cost-sensitive/simple queries, not the
default. Regex A is internal tooling only. Round-1 section above is kept for
the data trail; where they conflict, this round-2 verdict wins.

Round-2 harness: `booktest/compare_round2.py` (index builder inline, dual
judges, chNN-alias keys), `booktest/glm_rejudge.py` (GLM judge w/ low effort),
`booktest/comparison_round2.json` (full per-question data),
`booktest/render_final_table.py` → `infographic/final_compare.png`
(4-row table incl. full-book baseline; send photo + full-res document).
