# LightRAG tutorial — reusable pieces (validated 2026-09-11)

Building blocks from the delivered LightRAG tutorial (`booktest/lightrag_tutorial.html/pdf`).
Reuse for any future "explain this tool" PDF in Persian.

## Graphviz diagrams (need `sudo apt-get install graphviz` for the `dot` binary)

Three diagrams that carried the explanation — sources live in
`<WORKDIR>/booktest/{diag_pipeline,diag_graph,diag_query}.dot`, rendered with:

```
dot -Tpng -Gdpi=140 diag_X.dot -o diag_X.png
```

1. **Pipeline (indexing)**: فصل کتاب → چانک‌بندی → LLM استخراج → موجودیت‌ها+روابط → گراف دانش؛ چانک‌ها → embedding محلی → بردارها؛ همه → working_dir (JSON+graphml).
2. **Mini knowledge graph (real example)**: the two books as box nodes, their named concepts as ellipse nodes, dashed cross-book edges («هر دو: انتخاب صریح» / «هر دو: لایه اطلاعاتی»). This one figure makes the "merged graph" concept tangible.
3. **Query flow**: سؤال → استخراج کلیدواژه (hybrid) یا embedding (naive) → جستجوی دولبه (گراف + بردار) → زمینه با [ref] → LLM → پاسخ با ارجاع.

Style that worked: `node [fontname="Vazir", shape=box, style="rounded,filled", fillcolor=...]`;
color-code node families (books orange, concepts blue/purple/green, shared/dashed pink);
`rankdir=LR` everywhere (neato scattered Persian edge labels).

## Plain-language explanations that landed (use these framings)

- **Why plain RAG fails**: "if the answer lives in the RELATIONSHIP between two things
  in different parts of the document, no single chunk has it — plain RAG can't answer".
- **Indexing steps in Persian novice terms**: چانک‌بندی (تکه‌های ~۱۲۰۰ توکنی) → استخراج با
  LLM (مثال: از جمله «آبشار انتخاب قلب روش لافلی است» دو موجودیت و یک رابطه ساخته می‌شود) →
  embedding چانک‌ها → ذخیره در working_dir. Same-name entities merge (this IS the merge mechanism).
- **Query steps**: dual retrieval = "هم تکه‌های متن مشابه را می‌آورد و هم مسیرهای گراف را" —
  the contrast with plain RAG is the point.
- **Glossary box** (one callout): چانک / embedding / موجودیت / یال / graphml.
- **naive vs hybrid for context-only fetches**: hybrid runs an LLM keyword-extraction step —
  fails with a dummy LLM func ("Keyword extraction payload is not a JSON object") → use
  `mode="naive", only_need_context=True`.

## Common trap for the novice reader

LightRAG 1.5.7's doc_id = mdhash(canonical basename); same-basename docs silently
dedup in one batch (27-doc merged insert → 0 docs, no error). Unique basenames per
book from day one (`ptw__ch04.md`).

## weasyprint additions for tutorial-style PDFs (vs plain reports)

- `pre, code { direction: ltr; text-align: left; font-family: 'DejaVu Sans Mono', monospace; }`
  — code blocks must be forced LTR inside the RTL body or they garble.
- Images: `HTML(html_path, base_url='/dir/with/images/').write_pdf(...)` so relative
  `<img src="diag_pipeline.png">` resolves.
- Persian in graphviz labels shapes correctly (tested with Vazir); no reshaping hacks needed.
- Structure that passed review: §1 what/why (lead with the problem), §2 mechanism
  step-by-step + 3 diagrams, §3 minimal working code, §4 query modes table, §5 embedding
  notes, §6 merge + big trap, §7 lessons-from-real-runs table, §8 full project scenario
  with real numbers, §9 one-page summary, appendix with DOT source.
