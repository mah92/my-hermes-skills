#!/usr/bin/env python3
"""Measure OCR fidelity of a markdown file against a PDF's own text layer.

Usage:
    python ocr_quality.py SOURCE.pdf OCR_OUTPUT.md [-n 5]

Prints: word counts, how much of the PDF text the OCR output covers (recall),
how much of the OCR output is supported by the PDF text (precision), and the
share of repeated n-grams (a degeneration signal: >20% means the OCR is looping
or paraphrasing instead of transcribing).

Requires pymupdf (`pip install pymupdf`). No model, no network.
"""
import argparse
import collections
import re
import sys


def _import_fitz():
    try:
        import pymupdf as fitz  # newer name
    except Exception:
        import fitz  # older name
    return fitz


def norm(text):
    """Lowercase word tokens; drop detection tags and markdown/LaTeX punctuation."""
    text = re.sub(r"<\|det\|>[^<]*<\|/det\|>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[#*`>|_\[\]()<>{}\\]", " ", text)
    return re.findall(r"[A-Za-z0-9]+(?:[-'’][A-Za-z0-9]+)*", text.lower())


def grams(words, n):
    return set(tuple(words[i:i + n]) for i in range(len(words) - n + 1))


def duplication(words, n=6):
    c = collections.Counter(tuple(words[i:i + n]) for i in range(len(words) - n + 1))
    return sum(v - 1 for v in c.values() if v > 1) / max(1, len(words))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("ocr_md")
    ap.add_argument("-n", type=int, default=5, help="n-gram size (default 5)")
    a = ap.parse_args()

    fitz = _import_fitz()
    gt_text = "\n".join(str(p.get_text()) for p in fitz.open(a.pdf))
    gt = norm(gt_text)
    out = norm(open(a.ocr_md, encoding="utf-8", errors="ignore").read())
    if not gt or not out:
        print("empty input: pdf_words=%d ocr_words=%d" % (len(gt), len(out)))
        return 2
    A, B = grams(gt, a.n), grams(out, a.n)
    inter = len(A & B)
    print(f"pdf words:        {len(gt)}")
    print(f"ocr words:        {len(out)}")
    print(f"recall  ({a.n}-gram): {inter/len(A):6.1%}   share of the PDF text present in the OCR output")
    print(f"precision({a.n}-gram): {inter/len(B):6.1%}   share of the OCR output supported by the PDF")
    print(f"dup6:             {duplication(out):6.1%}   repeated 6-grams (>20% = degeneration)")
    verdict = "usable transcription" if inter / len(A) > 0.6 else "NOT a faithful transcription"
    print("verdict:", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
