# KG evaluation reports — format rules + Persian RTL PDF recipe

User-corrected format requirements (2026-09-11, three corrections in one session — treat as binding for any "compare answers with/without the graph" deliverable):

1. **Fair comparison = identical model.** All arms of an A/B (with-graph vs without-graph) must run on the SAME LLM with the same temperature. A deepseek-vs-glm comparison was rejected ("برای fair شدن مقایسه") and re-run entirely on deepseek-chat.
2. **Questions verbatim.** Never summarize the user's question in the report — reproduce it word-for-word in a quote box, and reference "سؤال ۱ (کامل بالا)" from tables.
3. **Answers verbatim and complete.** Never summarize the model answers in the report — include the full text of each answer. A "summary of answers" section was rejected ("جواب ها رو هم خلاصه کردی. کاملشونو بگذار").
4. **Per-answer cost banner.** Immediately before EACH answer's full text, a banner with: model, latency (s), prompt tokens, completion tokens, total tokens — measured at run time from the API response usage field. This is answer-cost, explicitly NOT graph-build cost.
5. **Answers are never edited.** The verbatim answers go into the report with their own markdown converted to HTML (headings/lists/quotes preserved) — no tightening, no re-summarizing, no "key points" reduction. Two rejections in one session: first a summary section ("جواب ها رو هم خلاصه کردی. کاملشونو بگذار"), and the report grew from 42KB to ~95KB once the full answers went in. Plan the PDF around full-answer size from the start.
6. **Merged-graph arms.** When the user then asks "same questions with the merged graph too": run the same harness against kg_merged, add a dedicated report section (e.g. "۵. پاسخ‌های گراف ترکیبی") between single-book answers and conclusion, renumber subsequent sections, grow the §1/§2 tables to include the new arms, and add a conclusion paragraph noting the merged-graph cost/coverage finding (merged arms came out cheaper: ~4.2-4.4K vs ~5K tokens).

## Tutorial deliverables (new sub-pattern, 2026-09-11 evening)

When asked for a short tutorial PDF on a technical topic (delivered: LightRAG tutorial, `booktest/lightrag_tutorial.html/pdf`), the user returned FOUR distinct corrections in one round — treat all as binding for any tutorial/explainer deliverable:

1. **Mechanism section is mandatory.** "How it works" step-by-step (indexing: chunking → LLM extraction → embedding → storage; querying: keyword/vector → dual retrieval → context → answer), each step in plain language with a concrete example from the actual project.
2. **Example diagrams expected.** Graphviz figures rendered via `dot` (`sudo apt-get install graphviz`; python graphviz module alone is NOT enough — needs the binary). Persian node labels shape correctly with `node [fontname="Vazir"]`; use `rankdir=LR` (the `neato` engine scatters Persian edge labels unreadably). Re-render and vision-check before embedding. Include the DOT source as an appendix ("در حد مثال").
3. **Write for a reader who has never used the tool.** "بعضی جملات از دید ناظری که X کار نکرده گنگ هست" — rewrite jargon sentences in plain language, add a quick glossary box (چانک، embedding، موجودیت، graphml), and lead with the problem the tool solves (why plain RAG fails) before the tool.
4. **Reuse the same weasyprint RTL pipeline** as comparison reports: Vazir fonts, `dir="rtl"`, but ADD `pre, code { direction: ltr; text-align: left; }` so code blocks don't garble inside RTL body; images via `HTML(path, base_url=img_dir)`; page-break between major parts; vision-QC pages before delivery.

## Fair-run pattern (validated)

Write one runner script that executes all arms in one process and writes a JSON ledger:

```python
RUNS = {"exo_no_ref": {...prompt without context...},
        "exo_graph": {...prompt with ctx inlined...}, ...}
for run, cfg in RUNS.items():
    t0 = time.time(); r = requests.post(deepseek_url, ...); dt = time.time()-t0
    ledger[run] = {"latency_s": round(dt,1), "prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
    open(f"fair_{run}.md","w").write(content)
json.dump(ledger, open("fair_ledger.json","w"))
```

Real numbers (deepseek-chat, temp 0.3, 12K-char context): no-ref answers ~110 prompt / ~800-1000 completion tokens, 5-7s; with-graph answers ~2.8K prompt / ~2.2K completion tokens, 11-13s. With-graph answers were ~2x output volume.

Context fetch: `kg-query "<question>" -g <graph> -m naive`  [was `kg-query "<question>" -g <graph> -m naive`] (naive mode needs only a dummy LLM func; hybrid needs a real LLM for keyword extraction). Trim context to ~12K chars. Run the with-graph arms DIRECTLY against deepseek with the context inlined — do not route through subagents (host-model 90s non-streaming timeout kills them).

## Persian RTL PDF recipe (weasyprint, validated)

reportlab cannot shape Persian glyphs. Working path:

1. `pip install weasyprint` into the agent venv (worked on this box; pango system deps present).
2. Vazir fonts already at `<HOME>/.fonts/vazir/Vazir-{Regular,Bold}.ttf`.
3. Build HTML: `<html lang="fa" dir="rtl">`, `@font-face` pointing at the TTFs via `file:///`, `body { font-family:'Vazir'; direction:rtl; }`. Navy/red heading theme, `.box` callouts, `.lat` (yellow) cost banners, `.pagebreak { page-break-before: always; }` between major parts.
4. Convert the verbatim markdown answers to HTML with a small converter: `#`/`##`/`###` headings, `- `/`N.` list items to `<li>`, `---` to `<hr>`, `>` to styled `<blockquote>`, `**bold**` and backtick-code inline. Escape first, then apply inline regexes.
5. `python -c "from weasyprint import HTML; HTML('report.html').write_pdf('report.pdf')"`.
6. Verify: render pages with the pdf skill's `pdf_page_image.py --pages 1,3,5` and inspect with vision_analyze (glyph shaping, RTL alignment, tofu check). Then deliver via the messaging platform `sendDocument`.

Reference outputs from the validated run: `booktest/report4.html`, `booktest/report4.pdf` (~8 pages, 76KB), `booktest/fair_*.md`, `booktest/fair_ledger.json`.
