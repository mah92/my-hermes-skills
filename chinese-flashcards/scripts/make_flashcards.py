#!/usr/bin/env python3
"""vocab_gloss.json -> printable DUPLEX flashcards PDFs (front: Hanzi+pinyin,
back: Persian). Two variants: flashcards.pdf (flip on SHORT edge) and
flashcards-longedge.pdf (flip on LONG edge). 6 cards/page, dashed cut guides,
card index in the corner to verify alignment. Run with the hermes venv python
(weasyprint installed there). Usage: python make_flashcards.py <ws> <outdir>"""
import json, os, sys

WS, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
items = [x for x in json.load(open(f"{WS}/vocab_gloss.json", encoding="utf-8")) if x.get("fa")]
N = len(items)
CARDS = 6
pages = [items[i:i+CARDS] for i in range(0, N, CARDS)]

def esc(s):
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

CSS_TEXT = """
@page { size: A4; margin: 10mm; }
body { font-family: 'Noto Sans CJK SC','Nazli',sans-serif; }
.page { width: 190mm; height: 277mm; page-break-after: always; display: grid;
  grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(2, 1fr);
  gap: 2mm; }
.note { grid-column: 1 / -1; grid-row: 1 / -1; text-align: center; font-size: 16pt;
  direction: rtl; display: flex; align-items: center; justify-content: center; }
.card { position: relative; border: 0.4pt dashed #999; border-radius: 2mm; display: flex;
  flex-direction: column; align-items: center; justify-content: center;
  padding: 2mm; text-align: center; }
.zh { font-size: 40pt; font-weight: bold; line-height: 1.15; }
.py { font-size: 13pt; color: #444; margin-top: 3mm; }
.fa { font-size: 17pt; direction: rtl; font-family: 'Nazli'; }
.idx { position: absolute; top: 1mm; left: 2mm; font-size: 8pt; color: #888; }
"""

def build(back_order_fn, note):
    html = [f'<div class="page front"><div class="note">{note}</div></div>']
    deck = 0
    for p in pages:
        fr = ['<div class="page front">']
        for v in p:
            deck += 1
            fr.append(f'<div class="card"><span class="idx">{deck}</span>'
                      f'<div class="zh">{esc(v["w"])}</div><div class="py">{esc(v["py"])}</div></div>')
        fr.append("</div>")
        html.append("".join(fr))
        page_idxs = list(range(deck - len(p) + 1, deck + 1))
        bk = ['<div class="page back">']
        for v in back_order_fn(p):
            n = page_idxs[p.index(v)]
            bk.append(f'<div class="card"><span class="idx">{n}</span>'
                      f'<div class="fa">{esc(v["fa"])}</div></div>')
        bk.append("</div>")
        html.append("".join(bk))
    return "".join(html)

def short_edge(p):   # duplex driver rotates page2 180deg -> back grid = whole 180deg
    return list(reversed(p)) if len(p) > 1 else p

def long_edge(p):    # duplex driver mirrors page2 -> back grid = columns reversed
    out = []
    for r in range(0, len(p), 3):
        out += list(reversed(p[r:r+3]))
    return out

NOTE = ("چاپ دو‌رو: گزینه «برگرداندن از لبه کوتاه» (flip on short edge). سپس از خط‌چین‌ها ببرید. "
        "شماره کنار کارت برای چک تراز: پشت هر کارت باید شماره همان کارت باشد · اول یک برگه تست بزنید.")
NOTE_LONG = ("چاپ دو‌رو: گزینه «برگرداندن از لبه بلند» (flip on long edge). سپس از خط‌چین‌ها ببرید. "
             "شماره کنار کارت برای چک تراز: پشت هر کارت باید شماره همان کارت باشد · اول یک برگه تست بزنید.")

from weasyprint import HTML, CSS
STYLES = [CSS(string=CSS_TEXT)]
HTML(string="<html><head><meta charset='utf-8'></head><body>" + build(short_edge, NOTE) +
     "</body></html>").write_pdf(f"{OUT}/flashcards.pdf", stylesheets=STYLES)
HTML(string="<html><head><meta charset='utf-8'></head><body>" + build(long_edge, NOTE_LONG) +
     "</body></html>").write_pdf(f"{OUT}/flashcards-longedge.pdf", stylesheets=STYLES)
print(f"{N} cards -> {OUT}/flashcards.pdf + flashcards-longedge.pdf")
