#!/usr/bin/env python3
"""Extract Chinese vocabulary (character-words) from a text file with jieba.
Usage: python extract_vocab.py <text.txt> <out_dir>
Writes <out_dir>/vocab.json: [{w, f}] sorted by frequency desc.
RUN WITH THE HERMES VENV PYTHON (jieba + pypinyin installed there)."""
import json, os, re, sys
import jieba

SRC, OUT = sys.argv[1], sys.argv[2]
text = open(SRC, encoding="utf-8").read()
words = [w for w in jieba.cut(text) if re.match(r"^[\u4e00-\u9fff]+$", w)]
cnt = {}
for w in words:
    cnt[w] = cnt.get(w, 0) + 1
vocab = [{"w": w, "f": c} for w, c in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))]
os.makedirs(OUT, exist_ok=True)
json.dump(vocab, open(f"{OUT}/vocab.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"tokens: {len(words)}, unique words: {len(vocab)} -> {OUT}/vocab.json")
