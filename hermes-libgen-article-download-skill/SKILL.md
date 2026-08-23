---
name: hermes-libgen-article-download-skill
description: "Use when downloading a scientific article from libgen."
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [libgen, article, paper, doi, download, sci, pdf]
    related_skills: [hermes-libgen-book-download-skill, hermes-agent]
---

# Libgen Article Download (scimag, verified)

Download SCIENTIFIC ARTICLES from libgen's scimag database via libgen.la.
Verified 2026-08: "Attention is all you need" (NeurIPS 2017, DOI
10.1609/aaai.v34i07.6693) downloaded end-to-end: search → row → ads.php →
signed get.php → 9-page PDF. For BOOKS use hermes-libgen-book-download-skill.

## When to Use
- User wants a research paper / scientific article (by title, author, or DOI)
- Need full-text PDF from libgen scimag

## Flow
1. Search with the ARTICLES checkbox (same as ticking "Scientific Articles"
   on the libgen main page). The URL is:
   `https://libgen.la/index.php?req=<query>&topics%5B%5D=a`
2. Result rows contain the download link DIRECTLY:
   `ads.php?md5=<md5>&downloadname=<DOI-or-slug>` — grab md5 + doi
3. Same get-flow as books: fetch ads.php (browser UA + Referer), extract
   `get.php?md5=...&key=...`, download the signed URL to ~/Downloads/articles/

Run the script (search → pick → download → verify → optional Bale send):
```bash
python3 ~/.hermes/skills/research/hermes-libgen-article-download-skill/scripts/libgen_article_download.py \
  --query "attention is all you need" --dry-run
python3 .../libgen_article_download.py --query "attention is all you need" \
  --doi 10.1609/aaai.v34i07.6693 --send
```

## Notes & pitfalls
- topics[]=a is the "Scientific Articles" checkbox on the MAIN search page —
  /scimag/ paths are 404 on libgen.la/li
- Articles' md5 lives in the ads.php href; downloadname is the DOI/slug
- Metadata json (object=f) works the same as books; locator has the file path
- Some scimag rows have NO fulltext (only a z-library.se/fulltext link) —
  those md5 links will fail; pick a row with an ads.php link
- Same rate-limit rules as books: pace requests, retry 503/524/429 with backoff
- get.php key is per-request → always fetch ads.php fresh before downloading
