#!/usr/bin/env python3
"""vocab_gloss.json -> 2-column study sheet PDF (RIGHT: Chinese hanzi,
LEFT: Persian gloss, middle: pinyin). A4, table layout, 21 pages for ~411 words.
Run with the hermes venv python (weasyprint installed there).
Usage: python make_sheet.py <ws> <outdir>"""
import json, os, sys

WS, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
items = [x for x in json.load(open(f"{WS}/vocab_gloss.json", encoding="utf-8")) if x.get("fa")]

def esc(s):
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

CSS_TEXT = """
@page { size: A4; margin: 12mm; }
body { font-family: 'Noto Sans CJK SC','Nazli',sans-serif; }
table { width: 100%; border-collapse: collapse; }
th { font-size: 12pt; border-bottom: 1pt solid #333; padding: 2mm; }
td { font-size: 13pt; border-bottom: 0.3pt solid #ccc; padding: 1.6mm; }
td.fa { direction: rtl; text-align: right; width: 45%; font-family: 'Nazli'; font-size: 14pt; }
td.zhs { text-align: center; font-size: 19pt; font-weight: bold; width: 30%; }
td.pys { text-align: center; color: #555; font-size: 11pt; width: 25%; }
tr { page-break-inside: avoid; }
"""

rows = []
for v in items:
    rows.append(f'<tr><td class="fa">{esc(v["fa"])}</td><td class="zhs">{esc(v["w"])}</td>'
                f'<td class="pys">{esc(v["py"])}</td></tr>')

html = ("<html><head><meta charset='utf-8'></head><body>"
        "<table><tr><th>فارسی</th><th>چینی</th><th>پینیین</th></tr>"
        + "".join(rows) + "</table></body></html>")
from weasyprint import HTML, CSS
HTML(string=html).write_pdf(f"{OUT}/vocab-sheet.pdf", stylesheets=[CSS(string=CSS_TEXT)])
print(f"{len(items)} rows -> {OUT}/vocab-sheet.pdf")
