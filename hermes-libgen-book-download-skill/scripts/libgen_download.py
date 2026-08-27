#!/usr/bin/env python3
"""Libgen downloader — working flow for libgen.la (Gen+).

search -> json metadata -> ads.php -> get.php signed URL -> PDF in ~/Downloads
Optional --send uploads the file to Bale (bot token from ~/.hermes/.env).

Usage:
  python3 libgen_download.py --query "best of asimov" --dry-run
  python3 libgen_download.py --query "asimov" --format pdf --index 0 --send
"""
import argparse, html, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

BASE = "https://libgen.la"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"

def fetch(url, referer=None, timeout=60):
    hdr = {"User-Agent": UA}
    if referer:
        hdr["Referer"] = referer
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def search_meta(query):
    """Scrape search page, extract file ids, return metadata dict."""
    q = urllib.parse.quote(query)
    page = fetch(f"{BASE}/index.php?req={q}&columns%5B%5D=t")
    m = re.search(r"json\.php\?object=f&ids=([0-9,]+)", page)
    if not m:
        raise RuntimeError("no JSON ids link found on search page")
    ids = m.group(1).split(",")[:100]
    meta = json.loads(fetch(f"{BASE}/json.php?object=f&ids={','.join(ids)}"))
    return meta

def pick(meta, fmt, qterms):
    cands = []
    for fid, f in meta.items():
        loc = (f.get("locator") or "").replace("\\", " - ")
        if fmt and f.get("extension") != fmt:
            continue
        if not any(re.search(t, loc, re.I) for t in qterms):
            continue
        cands.append((loc, f.get("filesize"), f.get("md5"), f.get("extension")))
    return cands

def signed_get_url(md5):
    page = fetch(f"{BASE}/ads.php?md5={md5}", referer=f"{BASE}/")
    m = re.search(r'get\.php\?md5=[^"\'&]+&key=[^"\'&]+', page)
    if not m:
        raise RuntimeError("no signed get.php URL in ads page")
    return f"{BASE}/{m.group(0)}"

def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": f"{BASE}/"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as out:
        out.write(r.read())
    return os.path.getsize(dest)

def send_bale(path):
    token = None
    chat = os.environ.get("BALE_CHAT_ID", "")
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("BALE_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("BALE_CHAT_ID=") and not chat:
                chat = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not token:
        print("no BALE_BOT_TOKEN in ~/.hermes/.env — skipping send")
        return False
    if not chat:
        print("no BALE_CHAT_ID in env or ~/.hermes/.env — skipping send")
        return False
    ok = subprocess.run(
        ["curl", "-s", "--max-time", "300",
         "-F", f"chat_id={chat}",
         "-F", f"document=@{path}",
         f"https://tapi.bale.ai/bot{token}/sendDocument"],
        capture_output=True, text=True).stdout
    try:
        return json.loads(ok).get("ok") is True
    except Exception:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--format", default="pdf")
    ap.add_argument("--index", type=int, default=0, help="which candidate to take (0 = first)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--send", action="store_true", help="send file to Bale after download")
    args = ap.parse_args()

    qterms = [t for t in re.split(r"\s+", args.query) if len(t) > 2]
    meta = search_meta(args.query)
    cands = pick(meta, args.format, qterms)
    print(f"candidates ({len(meta)} files scanned): {len(cands)}")
    for i, c in enumerate(cands[:10]):
        print(f"  [{i}] {c[0][:80]} | {c[1]} B | .{c[3]} | md5 {c[2]}")
    if args.dry_run or not cands:
        return
    loc, size, md5, ext = cands[min(args.index, len(cands) - 1)]
    name = re.sub(r'[^\w.\- ]+', "", loc).strip()
    if not name.lower().endswith(f".{ext}"):
        name += f".{ext}"
    dest = os.path.join(os.path.expanduser("~/Downloads"), name)
    print(f"\nselected: {loc}\ndownloading {md5} -> {dest}")
    url = None
    for attempt in range(1, 4):
        try:
            if not url:
                url = signed_get_url(md5)
                print("signed URL:", url)
            got = download(url, dest)
            break
        except Exception as e:
            print(f"attempt {attempt} failed: {e}")
            url = None
            if attempt == 3:
                print("download failed after 3 attempts")
                sys.exit(1)
            time.sleep(4)
    ftype = subprocess.run(["file", dest], capture_output=True, text=True).stdout.strip()
    print(f"saved {got} bytes")
    print(ftype)
    ok = (got == int(size)) and "PDF" in ftype
    print("byte-exact match with libgen record:", ok)
    if args.send:
        print("sending via Bale:", send_bale(dest))

if __name__ == "__main__":
    main()
