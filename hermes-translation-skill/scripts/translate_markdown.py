#!/usr/bin/env python3
"""Translate a markdown/text file via an OpenAI-compatible chat API.

Resumable: per-chunk output is written to <output>.parts/ as chunks complete;
re-running the same command skips finished chunks and continues.

Usage:
  translate_markdown.py --input ch1.md [--output out.md] [--glossary g.md]
                        [--max-chars 1500] [--lang fa] [--send] [--dry-run]
Env/config: endpoint+model+key used = the Hermes model provider (AvalAI);
override with AVALAI_BASE/AVALAI_MODEL/AVALAI_KEY env vars if needed.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request

LANG = {"fa": "فارسی", "en": "English", "de": "German", "fr": "French"}
BASE = os.environ.get("AVALAI_BASE", "https://api.avalai.ir/v1/chat/completions")
MODEL = os.environ.get("AVALAI_MODEL", "deepseek-v4-flash")

def get_key():
    for line in open(os.path.expanduser("~/.hermes/.env")):
        if line.startswith("HERMES_CUSTOM_API_AVALAI_IR_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def build_system(lang_name, glossary="", dialogue_rule=True):
    rule = ("\n۶) قانون مهم دیالوگ: هر گفتارِ هر شخصیت باید در پاراگراف جدای خودش"
            " بیاید؛ دو گفتارِ دو شخصیت هرگز در یک پاراگراف قرار نگیرد.") if dialogue_rule else ""
    return f"""تو مترجم ادبی حرفه‌ای انگلیسی به {lang_name} هستی. متن را به {lang_name} روان،
ادبی و خوش‌خوان ترجمه می‌کنی.
قوانین:
۱) فقط متن ترجمه‌شده را برگردان؛ هیچ توضیح یا یادداشتی اضافه نکن.
۲) ساختار متن (پاراگراف‌ها، خط‌خالی‌ها، نقل‌قول‌ها، و مارک‌داون) را دقیقاً حفظ کن؛ بین هر دو پاراگراف باید یک خط خالی باشد.
۳) اسامی و اصطلاحات را طبق واژه‌نامه زیر، یکدست ترجمه کن:
{glossary}
۴) لحن و سبک متن اصلی حفظ شود؛ دیالوگ‌ها طبیعی اما مؤدبانه.
۵) به زبان معیار بنویس.{rule}"""

def call(prompt, system, temperature=1.05, timeout=300):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "temperature": temperature, "stream": False,
    }).encode()
    req = urllib.request.Request(BASE, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_key()}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"].strip()

def split_chunks(text, size):
    paras = text.split("\n")
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 > size and cur:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + "\n" + p).strip() if cur else p
    if cur:
        chunks.append(cur)
    return chunks

def postprocess(text):
    # split same-line adjacent dialogue: «...» «...» -> separate paragraphs
    return re.sub(r"» {1,3}«", "»\n\n«", text)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="")
    ap.add_argument("--glossary", default="")
    ap.add_argument("--max-chars", type=int, default=1500)
    ap.add_argument("--lang", default="fa")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = open(os.path.expanduser(args.input), encoding="utf-8").read()
    out_path = args.output or re.sub(r"\.\w+$", lambda m: ".fa" + m.group(0), os.path.expanduser(args.input))
    parts_dir = out_path + ".parts"
    os.makedirs(parts_dir, exist_ok=True)

    chunks = split_chunks(src, args.max_chars)
    print(f"chunks: {len(chunks)} | output: {out_path}")
    if args.dry_run:
        for i, c in enumerate(chunks, 1):
            print(f"  [{i}] {len(c)} chars, starts: {c.splitlines()[0][:50]}")
        return

    gloss = ""
    if args.glossary:
        gloss = open(os.path.expanduser(args.glossary), encoding="utf-8").read()
    system = build_system(LANG.get(args.lang, args.lang), gloss)

    for i, ch in enumerate(chunks, 1):
        part = os.path.join(parts_dir, f"chunk_{i:02d}.md")
        if os.path.exists(part):
            print(f"  chunk {i}/{len(chunks)} exists, skip")
            continue
        ok = False
        for attempt in range(1, 5):
            try:
                t = call(f"متن (بخش {i}/{len(chunks)}):\n\n{ch}", system)
                with open(part, "w", encoding="utf-8") as f:
                    f.write(t)
                print(f"  chunk {i}/{len(chunks)} ok ({len(t)} chars)")
                ok = True
                break
            except Exception as e:
                print(f"  chunk {i} attempt {attempt}: {e}")
                time.sleep(15 * attempt)
        if not ok:
            sys.exit(f"chunk {i} failed after retries — re-run to resume")
        time.sleep(8)  # rate-limit pacing

    parts = []
    for i in range(1, len(chunks) + 1):
        p = os.path.join(parts_dir, f"chunk_{i:02d}.md")
        parts.append(open(p, encoding="utf-8").read())
    result = postprocess("\n\n".join(parts))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)

    sp = [p for p in src.split("\n\n") if p.strip()]
    fp = [p for p in result.split("\n\n") if p.strip()]
    print(f"done: {len(result)} chars | source paragraphs {len(sp)} | output paragraphs {len(fp)}")

    if args.send:
        token = ""
        for line in open(os.path.expanduser("~/.hermes/.env")):
            if line.startswith("BALE_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
        if token:
            r = subprocess.run(["curl", "-s", "--max-time", "300",
                                "-F", "chat_id=685739898",
                                "-F", f"document=@{out_path}",
                                f"https://tapi.bale.ai/bot{token}/sendDocument"],
                               capture_output=True, text=True).stdout.strip()
            print("Bale send:", "ok" if '"ok":true' in r else r[:120])

if __name__ == "__main__":
    main()
