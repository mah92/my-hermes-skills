# KG Enrichment: LightRAG + Local Embeddings (validated 2026-09-11)

Session-specific detail for the book-to-lightrag-pipeline skill. Everything here was
actually executed on this host unless marked otherwise.

## Why LightRAG over Microsoft GraphRAG
- GraphRAG: strongest global sense, but community-based; adding a book can force
  graph rebuild; community benchmarks ~$6-7 (GPT-4o) to index one 32k-word book.
- LightRAG (HKUDS, MIT): incremental insert (`ainsert` merges into the existing
  graph, no rebuild), dual-level retrieval (local entities / global themes / hybrid),
  pluggable LLM + embedding functions. Community cost comparison ~10-15x cheaper.
  This matches the multi-book-per-week merge requirement (books in the same domain
  share entities; conflicts stay co-cited with sources).
- Alternatives noted: LlamaIndex Property Graph / neo4j-graphrag (heavier, need
  a graph DB server); fine for org-scale, overkill here.

## Wiring a local embedding function (the part that failed twice)
`lightrag.hku` 1.5.7 (installed into agent venv). Its built-in `hf` binding uses
`AutoModelForCausalLM` (a GENERATION model) — wrong tool for embedders and it
double-loads a big model on a 9GB-RAM CPU box.

Working pattern — write your own async fn and wrap it with LightRAG's own
decorator so the wrapper object shape matches (`LightRAG.__post_init__` calls
`.func` on it; a bare function raises `AttributeError: 'function' object has
no attribute 'func'`):

```python
from lightrag.utils import wrap_embedding_func_with_attrs

@wrap_embedding_func_with_attrs(embedding_dim=DIM, max_token_size=512, model_name=NAME)
async def local_embed(texts, **kwargs):
    is_query = bool(kwargs.get("is_query"))
    prefix = "query: " if is_query else "passage: "   # e5-style prefixes
    return _encode(list(texts), prefix)               # mean-pool + L2 normalize
```

Other required init (1.5.x API): `await rag.initialize_storages()` after
constructing `LightRAG(...)` — otherwise `ainsert` raises
`PipelineNotInitializedError`. Also `logger.setLevel("WARNING")` (positional
string; the `logging_level=` kwarg is deprecated/removed).

Mean pooling must weight by attention_mask (padding shifts naive `.mean(dim=1)`);
normalize L2; run under `torch.no_grad()`.

## Embedding model comparison (real runs, CPU, 9GB RAM box)
Harness: 1 query + 3 docs (1 related, 2 unrelated) per scenario; correctness =
argmax similarity lands on the related doc.

| Model | EN-EN | FA-FA | FA-EN cross | Notes |
|---|---|---|---|---|
| intfloat/multilingual-e5-base (768d, 278M) | 0.830 vs 0.75/0.74 | 0.836 vs 0.77/0.75 | 0.790 vs 0.72/0.71 | needs query:/passage: prefixes; margin thinner on distractors |
| heydariAI/persian-embeddings (768d, 0.6B xlm-r finetune) | 0.644 vs 0.36/0.16 | 0.732 vs 0.26/0.11 | 0.534 vs 0.20/0.15 | no prefixes (mean pooling per card); much better distractor rejection; Persian-focused |

Both retrieved correctly in all scenarios. Default choice:
- mostly-EN corpus → e5-base (cross-lingual edge)
- FA-heavy corpus → heydariAI/persian-embeddings (user-suggested, validated)
Model card: https://huggingface.co/heydariAI/persian-embeddings
(e5: https://huggingface.co/intfloat/multilingual-e5-base)

HF download note: plain `ALL_PROXY` was not enough for transformers hub
downloads; `HTTPS_PROXY=socks5h://127.0.0.1:<PROXY_PORT>` worked. (hf-mirror.com
endpoint resolved via curl but failed inside transformers — don't bother.)

## Extraction LLM side
`openai_complete_if_cache("deepseek-chat", ..., api_key=..., base_url="https://api.deepseek.com")`
wrapped as `llm_model_func`. During the first real index run: entity extraction
worked (graph reached 358 nodes / 463 edges from 28 chapter files) but the
account hit `402 Insufficient Balance` mid-run → 25/28 docs marked `failed`.
LightRAG status store (`kv_store_doc_status.json`) tracks per-doc status, so
re-running `ainsert` retries only failed docs (LLM response cache in
`kv_store_llm_response_cache.json` avoids re-paying for completed chunks).
Also seen: occasional "found 3/5 fields on RELATION" format warnings from the
extraction LLM — tolerable, but a stricter model helps.

## Multi-graph ops (validated end-to-end 2026-09-11: kg_ptw, kg_exo, kg_merged)

Real numbers: 27 chapter-summaries (~168K extraction tokens deepseek-chat),
graphs kg_ptw 698 entities/879 rels, kg_exo 336/386, kg_merged 1703/2222/120
chunks; full merged build ~20 min at `llm_model_max_async=2` on the 9GB box.

**Memory (OOM exit 137).** LightRAG concurrency + e5 loading on a 9GB box:
default `llm_model_max_async=4` gets OOM-killed mid-insert. Always pass
`llm_model_max_async=2, embedding_func_max_async=2` on this class of host.
Inserts are incremental — re-running after a crash resumes pending docs only
(dup warnings for already-processed docs are harmless).

**Filename collisions silently drop documents (the big trap).** 1.5.7 derives
`doc_id = mdhash(canonical_basename)` and canonicalizes `file_paths` to the
BARENAME. Two books both have `ch04.md` → in a merged ainsert every colliding
basename after the first is recorded `duplicate_kind=filename` and SKIPPED: a
27-doc merged insert produced 0 new docs with "No new unique documents were
found" and no error. Cross-graph same-basename doc-ids also make
`kv_store_doc_status`/`full_docs` look contaminated (PTW rows inside kg_exo
bookkeeping) — the graphml/vdb QUERY layer stayed clean, but verify with graphml
probes (e.g. `s.count('Bounty')` vs `s.count('MTP')`), not by reading kv stores.
Fix: give every doc a globally-unique basename (`ptw__ch04.md`,
`exo__ch04.md`) before ainsert; for single-book graphs it only matters when
merging later, so do it from day one.

**Verify purity + completion, not vibes.** After each build: doc_status Counter
should be `{processed: N}`; grep graphml for per-book markers to confirm no
cross-contamination and that both books landed in a merged graph.

**Query validation (both modes).** `aquery(q, QueryParam(mode="hybrid"|"mix"))`
on 2 book-specific + 2 cross-book questions per graph; expect 4-16s/graph on
CPU. Cross-book merge works through shared entities and contrast questions
("what do both books say about X") return genuine both-book answers.

**Voice/document note (messaging platform).** Voice .ogg attachments may actually be other
binaries (an EPUB arrived as tmp*.ogg); `file` the path before assuming audio.

**naive vs hybrid retrieval for context-only fetches.** When pulling context
to hand to another LLM (no LightRAG answer step), use `QueryParam(mode="naive",
only_need_context=True)` with a dummy llm func — `hybrid` runs an LLM keyword-
extraction step that fails with a dummy ("Keyword extraction payload is not a
JSON object") and returns empty context. Strip `INFO:`/`WARNING:`/HF
"Loading weights" lines, then cap context at ~12K chars (~2.8K prompt tokens
through deepseek).


## Working dir layout (2026-09-11 state)
`<WORKDIR>/booktest/` — kg_build3.py (build kg_ptw/kg_exo/kg_merged),
kg_build_merged.py (merged-only build with unique basenames via kg_input/
staging dirs), kg_fetch_context.py (context-only query), kg_query_test.py
(6-question smoke test), fair_run.py + fair_merged_run.py + fair_ledger.json
(the 6-arm A/B harness), report4.html/report4.pdf (delivered Persian PDF
report), local_embed.py (embedding fn), embed_compare.py (model comparison).
