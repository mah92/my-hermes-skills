#!/usr/bin/env python3
"""Generate pinyin + Persian glosses for a Chinese vocab list (vocab.json).
Writes vocab_gloss.json: [{w, f, py, fa}]. GLOSS via avalai (deepseek-v4-flash),
pinyin via pypinyin (Style.TONE). Resume-safe on glosses.
Usage: python gloss_vocab.py <ws>"""
import json, os, sys, time, urllib.request
from pypinyin import lazy_pinyin, Style

WS = sys.argv[1]
vocab = json.load(open(f"{WS}/vocab.json", encoding="utf-8"))
KEY = os.environ["HERMES_CUSTOM_API_AVALAI_IR_API_KEY"]
URL = "https://api.avalai.ir/v1/chat/completions"
MODEL = "deepseek-v4-flash"

# pinyin for every word (tone style)
for v in vocab:
    v["py"] = " ".join(lazy_pinyin(v["w"], style=Style.TONE))

G = f"{WS}/vocab_gloss.json"
out = json.load(open(G, encoding="utf-8")) if os.path.exists(G) else []

def call(messages, retries=4):
    body = json.dumps({"model": MODEL, "messages": messages,
                       "temperature": 0.2, "max_tokens": 16384}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={
                "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                c = json.loads(r.read())["choices"][0]["message"]["content"]
                if c and c.strip():
                    return c
        except Exception as e:
            print(f"  retry {a+1}: {e}", file=sys.stderr)
        time.sleep(6)
    return None

done = {o["w"] for o in out if o.get("fa")}
todo = [v for v in vocab if v["w"] not in done]
print(f"glossing {len(todo)} words (done {len(done)})", flush=True)

SYS = ("You gloss Chinese words for Persian learners of Chinese. For each "
       "ID<TAB>word line output ID<TAB>short Persian gloss. Use natural Persian, "
       "1-4 words; for function words/particles give the grammatical function "
       "briefly (e.g. 的 -> «یِ اضافه/ملکیت»); disambiguate with context if "
       "needed. NO pinyin, NO extra text, ONLY the ID<TAB>gloss lines.")

CH = 100
for i in range(0, len(todo), CH):
    chunk = todo[i:i+CH]
    block = "\n".join(f"{v['w']}\t{v['w']}" for v in chunk)  # w unique -> id=word itself
    print(f"  chunk {i}..{i+len(chunk)-1}", flush=True)
    out_text = call([{"role": "system", "content": SYS},
                     {"role": "user", "content": block}])
    if out_text is None:
        print("FAILED chunk, keeping progress"); break
    fa = {}
    resp_lines = [l for l in (out_text or "").splitlines() if l.strip()]
    for i, line in enumerate(resp_lines):
        if "\t" in line:
            head, gl = line.split("\t", 1)
            # prefer word-ID match; else use line ORDER (LLM often numbers 1..N)
            if head in {v['w'] for v in chunk}:
                fa[head] = gl.strip()
            elif i < len(chunk):
                fa.setdefault(chunk[i]['w'], gl.strip())
        elif i < len(chunk) and not fa.get(chunk[i]['w']):
            fa[chunk[i]['w']] = line.strip()
    for v in chunk:
        out.append({"w": v["w"], "f": v["f"], "py": v["py"], "fa": fa.get(v["w"], "")})
    json.dump(out, open(G, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(1)

missing = sum(1 for v in out if not v["fa"])
merged = {o["w"]: o for o in out}
final = [merged[v["w"]] for v in vocab]           # dedupe + keep frequency order
json.dump(final, open(G, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"done: {len(final)}/{len(vocab)} glossed, missing {missing} -> {G}")
