---
name: table-as-image
description: >
  جدول/table request → render PNG image, never markdown.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [bale, table, image, rtl, persian, png]
    related_skills: [bale-direct-api, persian-documents]
---

# Table as Image — no markdown tables

## Hard rule
NEVER send a markdown table in a chat that renders plain text only (Bale,
Telegram-without-markdown, WhatsApp…). The user literally cannot see it.
Always render the table to a **PNG image** (PIL, raqm for RTL Persian) and
send it via the messenger Bot API (`sendPhoto` + full-res `sendDocument`,
because the platform downscales photos).

## When to use
- User asks for a «جدول / table / مقایسه» in a Bale/plain-text chat.
- User asks to compare items with several attributes (size, year, I/O, …).

## Steps
1. **Verify facts first** (anti-hallucination): every number/claim needs a
   source. Put the sources in a footer line INSIDE the image.
2. Write data + render PNG (script below). Persian → RTL mode; English → LTR.
3. Send via Bale Bot API (endpoint `tapi.bale.ai`, Telegram-compatible).
4. Verify `ok:true` + integer `message_id`.

## Render script (adapt HEADERS/ROWS/COLS)

```python
# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont

RTL = True  # False for English/LTR
BODY_SZ, HDR_SZ, TITLE_SZ, FOOT_SZ = 30, 32, 42, 22
PAD_X, PAD_Y, LINE, SCALE = 24, 20, 3, 2  # SCALE=2 → crisp

if RTL:
    FD = "/home/oem/.fonts/vazir/misc/Farsi-Digits/fonts/ttf/"
    F_REG, F_BOLD = FD + "Vazirmatn-FD-Regular.ttf", FD + "Vazirmatn-FD-Bold.ttf"
else:
    FD = "/usr/share/fonts/truetype/dejavu/"
    F_REG, F_BOLD = FD + "DejaVuSans.ttf", FD + "DejaVuSans-Bold.ttf"

f_body = ImageFont.truetype(F_REG, BODY_SZ)
f_head = ImageFont.truetype(F_BOLD, HDR_SZ)
f_title = ImageFont.truetype(F_BOLD, TITLE_SZ)
f_foot = ImageFont.truetype(F_REG, FOOT_SZ)

HEADERS = ["مدل", "حجم", "سال"]           # ← your columns
ROWS = [["XTTS-v2", "~467M", "2023"]]     # ← your rows
COLS = [340, 330, 120]                    # ← widths per column
TITLE = "عنوان جدول"
FOOTER = "منابع: ... | arxiv ..."         # sources INSIDE the image

def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        kw = dict(direction="rtl", language="fa") if RTL else {}
        if draw.textlength(trial, font=font, **kw) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    return lines + ([cur] if cur else [])

probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
rhs = []
for r in ROWS:
    h = 0
    for i, c in enumerate(r):
        lines = []
        for part in c.split("\n"):
            lines += wrap(probe, part, f_body, COLS[i] - PAD_X * 2)
        h = max(h, len(lines) * (BODY_SZ + 10) + PAD_Y * 2)
    rhs.append(h)

HDR_H = HDR_SZ + PAD_Y * 2
TITLE_H = TITLE_SZ + 40
FOOT_H = 150
W = sum(COLS) + LINE * (len(COLS) + 1)
H = TITLE_H + HDR_H + sum(rhs) + FOOT_H + LINE * (len(ROWS) + 2)
img = Image.new("RGB", (W, H), (255, 255, 255))
d = ImageDraw.Draw(img)

tkw = dict(direction="rtl", language="fa", anchor="ma") if RTL else dict(anchor="ma")
d.text((W // 2, 20), TITLE, font=f_title, fill=(16, 74, 63), **tkw)
y = TITLE_H
x = 0
d.rectangle([0, y, W, y + HDR_H], fill=(16, 74, 63))
for i, hname in enumerate(HEADERS):
    x0 = x + LINE
    d.rectangle([x0, y, x0 + COLS[i], y + HDR_H], fill=(16, 74, 63))
    a = dict(anchor="rm") if RTL else dict(anchor="lm")
    tx = (x0 + COLS[i] - PAD_X) if RTL else (x0 + PAD_X)
    d.text((tx, y + HDR_H // 2), hname, font=f_head, fill=(255, 255, 255),
           **dict(direction="rtl", language="fa", **a) if RTL else a)
    x = x0 + COLS[i]
y += HDR_H
for ri, row in enumerate(ROWS):
    fill = (255, 255, 255) if ri % 2 == 0 else (238, 246, 242)
    d.rectangle([0, y, W, y + rhs[ri]], fill=fill)
    x = 0
    for ci, cell in enumerate(row):
        x0 = x + LINE
        d.rectangle([x0, y, x0 + COLS[ci], y + rhs[ri]], fill=fill)
        lines = []
        for part in cell.split("\n"):
            lines += wrap(d, part, f_body, COLS[ci] - PAD_X * 2)
        ty = y + PAD_Y
        a = dict(anchor="ra") if RTL else dict(anchor="la")
        tx = (x0 + COLS[ci] - PAD_X) if RTL else (x0 + PAD_X)
        for ln in lines:
            d.text((tx, ty), ln, font=f_body, fill=(25, 30, 40),
                   **dict(direction="rtl", language="fa", **a) if RTL else a)
            ty += BODY_SZ + 10
        x = x0 + COLS[ci]
    y += rhs[ri]
# grid: vertical lines at column boundaries + horizontal at row boundaries
xs, acc = [], 0
for cw in COLS:
    xs.append(acc); acc += cw + LINE
for gx in xs[1:]:
    d.rectangle([gx, TITLE_H, gx + LINE, y], fill=(120, 150, 140))
row_y = TITLE_H + HDR_H
for rh_ in rhs:
    d.rectangle([0, row_y, W, row_y + LINE], fill=(120, 150, 140))
    row_y += rh_ + LINE
# footer with sources
d.rectangle([0, y, W, H], fill=(248, 249, 251))
ty = y + 18
for ln in wrap(d, FOOTER, f_foot, W - 70):
    d.text((W // 2, ty), ln, font=f_foot, fill=(110, 118, 130),
           **dict(direction="rtl", language="fa", anchor="ma") if RTL else dict(anchor="ma"))
    ty += FOOT_SZ + 8
img = img.resize((W * SCALE, H * SCALE), Image.LANCZOS)
img.save("/tmp/table.png", "PNG")
```

## Send via Bale Bot API

```python
import subprocess, json

def read_token():
    with open("/home/oem/.hermes/.env") as f:   # Hermes redacts in shell; open() is fine
        for line in f:
            if line.startswith("BALE_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]

token = read_token()
# chat_id: DM starts with 9 (e.g. 685739898), group starts with 6 (e.g. 6042445502).
# Find current session chat: grep "inbound message" ~/.hermes/logs/gateway.log | tail
chat_id = "685739898"
for method, field, cap in [("sendPhoto", "photo", "جدول"),
                           ("sendDocument", "document", "فایل کامل (وضوح اصلی)")]:
    cmd = ["curl", "-s", "-X", "POST", f"https://tapi.bale.ai/bot{token}/{method}",
           "-F", f"{field}=@/tmp/table.png", "-F", f"chat_id={chat_id}", "-F", f"caption={cap}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    resp = json.loads(r.stdout)
    assert resp.get("ok") and isinstance(resp.get("result", {}).get("message_id"), int), resp
```

## Pitfalls
- **RTL shaping**: Persian needs raqm → check `PIL.features.check('raqm')` is True.
  Without raqm letters render disconnected; fallback = `arabic_reshaper` + `python-bidi`.
- Use the **FD (Farsi-Digits) Vazirmatn** variant so Persian digits render natively.
- Never type Cyrillic/foreign letters inside Persian cells (typo happened: «генератор»).
- Bale downscales `sendPhoto` (~1500 px); always ALSO send `sendDocument` (full res).
- Put sources in the image footer AND cite them in the chat text — user demands a
  source for every number (فاکت rule).
- Verify `ok:true` + `message_id` after every send; check the target chat.
- Send to the chat of the CURRENT session — find it via gateway log, don't guess.
- Bold/italic/markdown don't work in Bale text messages either; plain text only.
