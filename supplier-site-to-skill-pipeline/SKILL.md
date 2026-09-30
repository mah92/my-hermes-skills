---
name: supplier-site-to-skill-pipeline
description: Use when vendor websites must become per-site skills.
---

# Supplier sites -> per-site skills -> knowledge graph

Turns a list of company domains into one English knowledge skill per company, plus
an index skill, and loads them into a LightRAG graph. Built for the PCB/component/
EDA supplier list but the shape is general (any vendor list).

## Pipeline (fixed order)

1. **Probe reachability** for every domain: direct, then through the proxy pool.
   Record code + size + title per domain in a state JSON (resumable).
2. **Crawl the company's own pages** (10-16 per site): home, about, capabilities,
   services, FAQ, quote/order, blog, quality, plus anything matching
   `guide|how-to|tutorial|blog|help|faq|capability` in the links.
3. **Third-party reviews**: `https://www.sitejabber.com/reviews/<domain>` is the
   review site that actually answers to a plain curl here. Trustpilot, BBB,
   Reddit (search.json) and hn.algolia all return 403/empty — do not build on them.
4. **User videos** (the only source that says what customers really think):
   search YouTube for `<brand> review`, `<brand> vs`, `<brand> experience`,
   download the audio, run ASR, keep the transcript. See
   `youtube-bulk-asr-collection` for the download/ASR machinery.
5. **Write the skill** with an LLM: a fixed section skeleton (offers,
   capabilities/limits, ordering, lead time, what users say, practical notes,
   sources) and a hard rule: only facts present in the captured text; write
   "not covered by the captured sources" otherwise. Never let it invent numbers.
6. **Index skill**: group the per-site skills by what the buyer is buying and
   point to each; keep the raw evidence (pages, reviews, transcripts) in each
   skill's `references/`.
7. **Graph**: one markdown input per skill, then insert; then query it to verify.

## Pitfalls (all hit for real)

- **Vendor promo videos have no narration.** If the picker takes official
  channel clips ("Factory tour", "Inside <brand>"), ASR returns music-noise
  (empty or "<gbg> mmm"). Prefer titles containing review/vs/experience and
  reject factory/promo titles; keep trying more candidates when a transcript is
  empty — and require the downloaded id to be exactly 11 chars (truncated ids
  come out of search and yt-dlp rejects them as "Incomplete YouTube ID").
- **curl is not enough for JS-only sites** (1688, zbj, easyeda, oshwhub):
  the response is a shell page with no text. Use the sitemap, the docs/wiki
  subdomain, or the site's earlier first-pass crawl; if nothing exists, write an
  honest "no content captured" card plus a due-diligence checklist instead of
  pretending.
- **Check the domain from a second network before declaring it dead:** a site
  that answers `000` locally may answer on a foreign server (and vice versa).
- **A repo-building script that wipes its output directory** destroys `.git` and
  every directory not derived from its own sources. Move them aside, rebuild,
  move them back — otherwise the pushed history is gone.
- **Never re-run a naive re-insert after a partial graph load**: the batch
  answers "File name already exists" for everything already in the graph. Delete
  just the stuck document by file name and re-insert that one file.
- **Serialise ASR machine-wide** (one process at a time, ~2.7 GB each) and give
  the crawler a per-site budget; 12 extra paths x N dead proxies x 25 s turns
  one site into a 20-minute wait for nothing.
- **Counts must match reality**: report the number of skills actually written and
  the number of graph documents actually processed, not what was attempted.
