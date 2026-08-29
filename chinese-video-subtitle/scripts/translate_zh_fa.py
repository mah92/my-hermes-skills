#!/usr/bin/env python3
"""Chinese->Persian chunked translation via avalai (deepseek-v4-flash).
Reads segments.json (zh text per cue) -> writes fa_cues.json {idx: fa}.
Chunk=40 lines + max_tokens=16384 (60-line chunks get empty responses on
deepseek-v4-flash — verified on the 2026-08-29 Chinese jobs and the 2026-08-28
English container E2E). Resume-safe.
Usage: python translate_zh_fa.py <ws>"""
import json, os, sys, time, urllib.request

WS = sys.argv[1]
segs = json.load(open(f"{WS}/segments.json", encoding="utf-8"))
KEY = os.environ["HERMES_CUSTOM_API_AVALAI_IR_API_KEY"]
URL = "https://api.avalai.ir/v1/chat/completions"
MODEL = "deepseek-v4-flash"
CHUNK = 40

out_path = f"{WS}/fa_cues.json"
fa = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}

def call(messages, retries=4):
    body = json.dumps({"model": MODEL, "messages": messages,
                       "temperature": 0.3, "max_tokens": 16384}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={
                "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.loads(r.read())["choices"][0]["message"]["content"]
                if out and out.strip():
                    return out
                print(f"  empty response, retry {a+1}", file=sys.stderr)
        except Exception as e:
            print(f"  retry {a+1}: {e}", file=sys.stderr)
        time.sleep(6)
    return None

SYS = ("You are a professional subtitle translator (Chinese->Persian) for an "
       "inspirational Chinese film with emotional spoken monologue. Translate to "
       "natural, FLUID spoken Persian — like real dubbing, NOT word-for-word. "
       "Handle interjections (哎, 啊, 嗯) naturally or drop them. Persist meaning "
       "and tone; use نیمفاصله everywhere; keep numbers and proper nouns.\n"
       "Output one line per input: ID<TAB>Persian text. ONLY those lines, no "
       "explanations, no thinking, no pinyin, no transliteration of Chinese.")

total = len(segs)
for start in range(0, total, CHUNK):
    idxs = list(range(start, min(start + CHUNK, total)))
    if all(str(i) in fa for i in idxs):
        print(f"chunk {start} done"); continue
    block = "\n".join(f"{i}\t{segs[i]['text']}" for i in idxs)
    print(f"translating {start}..{start+len(idxs)-1}", flush=True)
    out = call([{"role": "system", "content": SYS},
                {"role": "user", "content": block}])
    if out is None:
        print(f"FAILED chunk {start}; keeping progress"); break
    for line in out.splitlines():
        line = line.strip()
        if "\t" in line:
            i, txt = line.split("\t", 1)
            if i.isdigit() and int(i) in idxs:
                fa[i] = txt.strip()
    json.dump(fa, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(1)

print(f"done: {len(fa)}/{total} -> {out_path}")
