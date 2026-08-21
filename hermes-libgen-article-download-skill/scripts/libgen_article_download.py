#!/usr/bin/env python3
"""Libgen scimag article downloader (libgen.la, Articles checkbox = topics[]=a).

Search -> rows carry ads.php?md5=...&downloadname=<DOI> -> signed get.php -> PDF.
Usage:
  libgen_article_download.py --query "attention is all you need" --dry-run
  libgen_article_download.py --query "attention is all you need" --doi 10.1609/aaai.v34i07.6693 --send
"""
import argparse, html, json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

BASE = "https://libgen.la"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"
OUT = os.path.expanduser("~/Downloads/articles")

def fetch(url, referer=None, timeout=300, tries=4):
    last = None
    for attempt in range(1, tries + 1):
        hdr = {"User-Agent": UA}
        if referer:
            hdr["Referer"] = referer
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (500, 503, 524, 429):
                time.sleep(5 * attempt)
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(5 * attempt)
    raise last

def find_articles(q):
    """Return [(md5, downloadname_slug), ...] from the articles-topic search."""
    url = f"{BASE}/index.php?req={urllib.parse.quote(q)}&topics%5B%5D=a"
    for attempt in range(1, 4):
        for mirror in (BASE, "https://libgen.li"):
            try:
                page = fetch(f"{mirror}/index.php?req={urllib.parse.quote(q)}&topics%5B%5D=a")
                links = re.findall(r"ads\.php\?md5=([0-9a-f]+)&downloadname=([^\"']+)", page)
                if links:
                    return links[:20]
            except Exception as e:
                print(f"  {mirror}: {e}")
        print(f"  attempt {attempt} throttled, waiting 8s")
        time.sleep(8)
    return []

def signed_get_url(md5, slug):
    page = fetch(f"{BASE}/ads.php?md5={md5}&downloadname={urllib.parse.quote(slug)}", referer=f"{BASE}/")
    m = re.search(r'get\.php\?md5=[^"\'&]+&key=[^"\'&]+', page)
    if not m:
        raise RuntimeError("no signed get.php URL (no fulltext for this row?)")
    return f"{BASE}/{m.group(0)}"

def download(url, dest):
    hdr = {"User-Agent": UA, "Referer": f"{BASE}/"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=300) as r, \
         open(dest, "wb") as f:
        f.write(r.read())
    return os.path.getsize(dest)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--doi", default="", help="exact DOI/slug to select")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()

    hits = find_articles(args.query)
    if not hits:
        print("no article rows found"); return
    print(f"{len(hits)} article rows:")
    for i, (md5, slug) in enumerate(hits[:15]):
        print(f"  [{i}] md5={md5}  doi/slug={urllib.parse.unquote(slug)[:70]}")
    if args.doi:
        picks = [h for h in hits if args.doi.lower() in h[1].lower()]
    else:
        picks = hits
    if not picks:
        print("no row matches --doi"); return
    md5, slug = picks[min(args.index, len(picks) - 1)]
    slug_u = urllib.parse.unquote(slug)
    if args.dry_run:
        print(f"would download md5={md5} slug={slug_u}")
        return
    os.makedirs(OUT, exist_ok=True)
    dest = os.path.join(OUT, re.sub(r'[^\w.\-]+', "_", slug_u)[:80] + ".pdf")
    print(f"\ndownloading {slug_u} -> {dest}")
    got = None
    for attempt in range(1, 3):
        try:
            url = signed_get_url(md5, slug)
            print("signed:", url)
            time.sleep(1.5)
            got = download(url, dest)
            break
        except Exception as e:
            print(f"  attempt {attempt}: {e}")
            time.sleep(8 * attempt)
    if got:
        print(f"saved {got} bytes")
        print(subprocess.run(["file", dest], capture_output=True, text=True).stdout.strip())
        if args.send:
            token = ""
            env_path = os.path.expanduser("~/.hermes/.env")
            if os.path.exists(env_path):
                for line in open(env_path):
                    if line.startswith("BALE_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
            if token:
                r = subprocess.run(["curl", "-s", "--max-time", "300",
                                    "-F", "chat_id=YOUR_BALE_CHAT_ID",
                                    "-F", f"document=@{dest}",
                                    f"https://tapi.bale.ai/bot{token}/sendDocument"],
                                   capture_output=True, text=True).stdout
                try:
                    print("Bale send ok:", json.loads(r).get("ok"))
                except Exception:
                    print("Bale send failed:", r[:150])
            else:
                print("no BALE_BOT_TOKEN — skipped send")

if __name__ == "__main__":
    main()
