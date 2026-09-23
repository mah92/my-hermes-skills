# KG evaluation-run scripts (book-to-lightrag-pipeline)

Session-specific scripts from the 2026-09-11 validation runs (PTW + ExO).
They live in <WORKDIR>/booktest/ and are referenced by the pipeline SKILL.md.

## `kg-query` — context-only retrieval (no LLM answer)  [was `kg_fetch_context.py`]

```
<HERMES_VENV>/bin/python kg-query "<question>" -g <graph_dir_name> -m <mode>
```

- `<graph_dir_name>`: kg_ptw | kg_exo | kg_merged (working_dir under <WORKDIR>/booktest/)
- mode: `naive` (pure vector; recommended — works with a dummy LLM func) or
  `hybrid` (needs a real LLM for keyword extraction; fails with dummy func).
- Prints LightRAG's context block (Document Chunks JSON with reference_ids,
  entity/relation sections depending on mode).
- Strip `INFO:`/`WARNING:`/`Loading weights` lines from stderr/stdout before
  embedding the text into a prompt.
- Cap to ~12K chars per question (~4K prompt tokens) — quality plateaus beyond
  that and keeps the answer run cheap.

## `kg-ask` — full query+answer smoke test per graph  [was `kg_query_test.py`]

```
<HERMES_VENV>/bin/python kg-ask "<question>" -g <graph_dir_name>
```

Runs the per-graph question set through hybrid and mix modes and prints
latency + answer head per mode. Question sets are defined inline in TESTS.

## fair_run.py — the fairness harness (identical model for all arms)

```
<HERMES_VENV>/bin/python fair_run.py
```

- Arms defined in RUNS dict: <topic>_no_ref (general-knowledge prompt) and
  <topic>_graph (same question + inline retrieved context + citation rules).
- One deepseek-chat call per arm (temperature 0.3, max_tokens 4000, no memory).
- Writes <WORKDIR>/booktest/fair_<arm>.md plus fair_ledger.json:
  {arm: {latency_s, prompt_tokens, completion_tokens, total_tokens}}.
- The ledger goes verbatim into the user-facing PDF report next to each
  answer (user requirement: per-question time/token, not aggregate).

## report4.html / report4.pdf — Persian RTL report template

- Hand-written HTML, `dir="rtl"`, Vazir font loaded via
  `file://<HOME>/.fonts/vazir/Vazir-Regular.ttf` (+Bold).
- Render: `<HERMES_VENV>/bin/python -c "from weasyprint import
  HTML; HTML('<WORKDIR>/booktest/report4.html').write_pdf('report4.pdf')"`
- weasyprint is pip-installed in the agent venv; reportlab alone cannot
  shape Persian glyphs (do not use it for Persian text).
- Verify by rasterizing (pdf skill: pdf_page_image.py --dpi 110) and
  inspecting the PNG with vision: check glyph shaping, RTL alignment, table
  columns, no tofu.
- Deliver via messaging-platform sendDocument to the owner chat (configure your platform details).

## Report content rules (user-corrected three times — binding)

The deliverable PDF for a with/without-graph comparison must contain:

1. The user's QUESTIONS VERBATIM, word-for-word, in quote boxes (a table
   may reference "سؤال ۱ (کامل بالا)" but never re-phrase the question).
2. A per-answer cost banner immediately before each answer: model name,
   latency in seconds, prompt/completion/total tokens (from the API usage
   field, measured at run time). This is answer cost — the user explicitly
   excluded graph-build cost from it.
3. The ANSWERS VERBATIM AND COMPLETE — no summaries, no abridged versions
   ("جواب ها رو هم خلاصه کردی. کاملشونو بگذار"). Convert each answer's
   markdown to HTML: `#`/`##`/`###` → h2/h3/h4, `- `/`N.` → `<li>`, `---`
   → `<hr>`, `>` → styled `<blockquote>`, `**bold**`/backticks inline.
   Escape HTML first, then apply inline regexes.
4. Structure that passed review: §1 experiment description + verbatim
   questions; §2 latency/token table; §3 head-to-head criteria table;
   §4 the four FULL answers under `.pagebreak`s; §5 conclusion; §6
   infrastructure stats (graph sizes, chapter-gen tokens) as appendix.

## Merged-graph arms (added later in the same session — validated)

User follow-up: "همین دو سوال رو با گراف ترکیبی هم بپرس" — the two questions
also ran against kg_merged (BOTH books in one graph, 1703 ent/2222 rel), and
the PDF gained a section "۵. پاسخ‌های گراف ترکیبی" between the single-book
answers and the conclusion. Renumber later sections (۶ conclusion, ۷ stats).

- Context fetch: same `kg-query` but `mode=naive` against kg_merged;
  hybrid fails there too with a dummy LLM (keyword extraction needs a real
  model). Cap 12K chars as usual.
- Answers via the same direct deepseek-chat call; prompts explicitly state
  the graph contains BOTH books and "if content from BOTH books is relevant,
  use it".
- Result: merged arms were CHEAPER than single-book graph arms (merged_exo
  8.3s/4360 tok, merged_ptw 8.7s/4205 vs ~5.1K/4.9K single) — naive retrieval
  over the larger graph returns tighter chunks — and surfaced cross-book
  concepts (Black Ops teams, Optimizer/Scaler/Evangelist roles) absent from
  single-book answers. Report this: it is evidence the merged graph adds
  retrieval efficiency, not just coverage.
- Report structure after addition: §1 verbatim questions (table grows to six
  runs: 4 original + 2 merged, each row naming its graph), §2 six-row
  latency/token table, §3 head-to-head, §4 four full answers, §5 TWO merged
  full answers under a header explaining the merged condition, §6 conclusion
  (+ paragraph noting the merged cost/coverage finding), §7 infra stats.

Rebuild script: `<WORKDIR>/booktest/build_report.py` (md→html conversion +
section splice; sandbox drops state between tool calls, so keep the
converter in a file on disk, not inline in the call). After adding sections,
re-check h2 markers before splicing — section numbering shifts (old
`<h2>۵. جمع‌بندی` becomes `<h2>۶. جمع‌بندی</h2>`), so match markers against
the CURRENT file, not the original template.
