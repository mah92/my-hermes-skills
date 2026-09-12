#!/usr/bin/env python3
"""Rough token-budget table for generated skill files when no tokenizer is installed.

Proxies used (both printed):
  - words * 1.33  : conservative upper bound for BPE token counts on English text.
  - chars / 4     : prose estimate (code-heavy text runs ~3.5-3.8 chars/token).
Real token counts land between the two; glossary/cheatsheet-style structured text
compresses below both.

Usage: python3 estimate_tokens.py [path-to-skill-dir]   (default: current dir)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
md_files = sorted(p for p in root.rglob("*.md") if p.is_file())

if not md_files:
    print(f"no .md files found under {root}")
    sys.exit(1)

print(f"{'file':48s} {'bytes':>7s} {'words':>7s} {'w*1.33':>8s} {'chars/4':>8s}")
tot_words = 0
for p in md_files:
    text = p.read_text(encoding="utf-8")
    words = len(text.split())
    tot_words += words
    print(f"{str(p.relative_to(root)):48s} {p.stat().st_size:7d} {words:7d} {words*1.33:8.0f} {len(text)/4:8.0f}")
print(f"\ntotal words: {tot_words} | total w*1.33 proxy: {tot_words*1.33:.0f}")
