---
name: persian-slide-pdf
description: Build Persian RTL 16:9 slide decks as PDF with WeasyPrint.
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [persian, slides, pdf, rtl, weasyprint]
    related_skills: [persian-office, presenton-slides]
---

# Persian Slide-Deck PDF

Produce presentation-style PDFs (one slide = one page, 16:9) with correct
Persian RTL shaping and embedded fonts, via WeasyPrint. Use this INSTEAD of
python-pptx when the deck must render correctly on devices without Persian
fonts (PPTX render happens on the viewer's device; PDF render happens here).

## When to Use
- "PDF ارائه" / slide-deck request in Persian, delivery via Bale.
- Persian RTL text must display correctly on phones (no tofu, not LTR).
- Don't use for: editable PPTX deliverables (use presenton-slides direct
  python-pptx path), plain A4 documents (use persian-office).

## Procedure
1. Font check: `fc-list :lang=fa family`. Known-good on this box: Titr
   (titles), Vazirmatn RD FD (body), Nazli, Homa, Amiri. NEVER use B Titr /
   B Nazanin — they are not installed here and vanish on viewers' devices.
2. Author HTML with one `div.slide` per slide, inline `<style>` starting with
   `@page { size: 297mm 167mm; margin: 0; }` and `.slide { width: 297mm;
   height: 167mm; page-break-after: always; overflow: hidden; }`.
3. Render with the hermes venv python (system python lacks weasyprint):
   `~/.hermes/hermes-agent/venv/bin/python script.py` where the script calls
   `HTML(string=html).write_pdf(out, stylesheets=[CSS(string=css)])`.
   Body styles may live in the same passed-in CSS string.
4. VERIFY page count == slide count: `pdfinfo out.pdf | grep Pages`.
5. QC by vision: `pdftoppm -jpeg -r 40 out.pdf /tmp/qc` then vision_analyze
   on 2-3 representative pages. Check: one slide per page (not squeezed
   multi-slide), Persian letters connected and right-aligned, no overflow.
6. Send via Bale with exact chat_id verified first:
   `curl tapi.bale.ai/bot$BALE_BOT_TOKEN/getChat -d chat_id=<id>` — compare
   the returned title with the target chat name before sendDocument.

## Pitfalls
- WeasyPrint 69 silently ignores `@page` rules if the CSS string is never
  passed to write_pdf — pages fall back to A4 and slides pile up 3-per-page.
  Symptom: `pdfinfo` shows A4 portrait. Fix: pass stylesheets=[CSS(...)].
- `px` page sizes did not override A4 in one session; `mm` works.
- python-pptx decks show empty glyphs / wrong alignment on Android Bale:
  viewer lacks the font. Only PDF (fonts embedded) is device-safe.
- getChat title check matters: env default BALE_CHAT_ID may point to a
  different chat than the conversation the user wrote in.

## Verification
- pdfinfo Pages equals slide count; page size is 16:9 landscape.
- Vision QC on rendered pages: shaped RTL Persian, no cut-off content.
- Bale sendDocument response `ok:true` and chat id matches target.
