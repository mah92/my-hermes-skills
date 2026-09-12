# Persian RTL PDF report recipe (validated 2026-09-11)

Full validated path for producing Persian (Farsi) RTL PDF reports on this box
and delivering them via the messaging platform. Use this whenever a deliverable report must be a
PDF in Persian.

## Why not reportlab
reportlab cannot shape Arabic-script glyphs — Persian text comes out
disconnected/reversed. The bundled pdf skill's reportlab path is Latin-only in
practice. Do NOT use it for Persian.

## Working stack: weasyprint (installed in agent venv)
```bash
<HERMES_VENV>/bin/pip install weasyprint   # pulled pango deps cleanly
<HERMES_VENV>/bin/python -c "import weasyprint"  # verify
```

Fonts already on box (verified): `<HOME>/.fonts/vazir/Vazir-Regular.ttf`
and `Vazir-Bold.ttf` (copies also in `~/hermes_files/fonts/`).

## Pattern
1. Write HTML: `<html lang="fa" dir="rtl">`, `@font-face` with
   `url('file://<HOME>/.fonts/vazir/Vazir-Regular.ttf')` (+ Bold),
   `body { font-family:'Vazir'; direction:rtl; }`.
2. Render: `from weasyprint import HTML; HTML('/abs/path/report.html').write_pdf('/abs/path/report.pdf')`
   — absolute paths required (weasyprint resolves relative badly).
3. Verify visually: `pdf_page_image.py report.pdf --pages 1-3 --dpi 110
   --out-dir imgs/` then `vision_analyze` each page — check glyph shaping
   (connected letters), RTL alignment, no tofu, tables intact.
4. Deliver via the messaging platform: `POST https://<PLATFORM_API>/bot$BOT_TOKEN/sendDocument`
   with `data={'chat_id': <OWNER_CHAT_ID>, 'caption': ...}` and
   `files={'document': (name, fh, 'application/pdf')}` — verified HTTP 200.
   Page ~ every long section with `<div class="pagebreak"></div>`.

## Markdown -> HTML converter (for verbatim answer embedding)
Small stdlib converter pattern: `html.escape` each line, then
`**bold**` -> `<b>`, backticks -> `<code>`; `# ` -> `<h2>`, `## ` -> `<h3>`,
`### ` -> `<h4>`; `- ` / `N. ` lines collect into `<ul><li>`; `---` -> thin
`<hr>`; `> ` -> styled `<blockquote>`; blank-line-separated paragraphs ->
`<p>`. Keep converter as a self-contained build script on disk (sandbox drops
interpreter state between execute_code calls — build scripts must be files).

## Report standard (user-mandated, 2026-09-11 — do not soften)
For any "same question, N experimental conditions" comparison:
- ALL runs use ONE identical model + settings (deepseek-chat, temp 0.3).
  Mixing models (glm control vs deepseek graph) was rejected: redo on one model.
- A banner immediately BEFORE each answer states that answer's own cost:
  model | latency seconds | prompt tokens | completion tokens | total tokens
  (answer-time cost only — never graph-build cost).
- Questions quoted VERBATIM in full (in a callout box), never paraphrased.
- Answers included VERBATIM in full — never summarized. Summaries were
  rejected twice; the report grew 42KB -> 95KB when fixed.
- Final deliverable: the PDF, sent via messaging-platform sendDocument to the owner.

## Fair-run harness pattern
- Fetch each condition's context FIRST via `kg_fetch_context.py <graph>
  <question> naive` (naive works with a dummy llm func; hybrid needs a real
  LLM for keyword extraction and fails with dummy).
- Answer via ONE direct deepseek-chat call per condition (~5K tokens each,
  5-13s). Long inline context through subagent delegation fails (glm 90s
  non-streaming timeout) — short-prompt control runs may still use delegate.
- Keep a ledger JSON {run: {latency_s, prompt_tokens, completion_tokens,
  total_tokens}} and feed the banners from it.
- Merged-graph (kg_merged) runs: naive retrieval over the bigger graph
  returns tighter chunks — answers came out CHEAPER (4.2-4.4K tokens vs ~5K)
  and pulled cross-book concepts (Black Ops, Optimizer/Scaler/Evangelist
  roles) unavailable in single-book graphs.

Validated ledger (deepseek-chat, temp 0.3, 2026-09-11):
exo_no_ref 7.4s/1158tok | exo_graph 13.0s/5158 | ptw_no_ref 5.5s/885 |
ptw_graph 11.5s/4929 | merged_exo 8.3s/4360 | merged_ptw 8.7s/4205.
