# Worked Example — Think Python 2 Generation Log

Full run of the book-to-skill workflow on *Think Python 2e* (Allen B. Downey, O'Reilly
2015, 291 pages, ~102K tokens), generated 2026-08-29. Everything below is what
actually happened and what shipped; reuse it as a size/shape benchmark.

## Source & Extraction
- Source: `<WORKDIR>/booktest/think_python2.pdf` → pypdf, BOOK_TYPE=text.
- `metadata.json` deltas: 21 chapters detected (`chapters_method: numeric`), ToC present,
  images_dropped 0. Workdir was PID-suffixed: `/tmp/book_skill_work-<pid>/`.

## Probing Pattern That Worked
- `grep -n -E "^CHAPTER [0-9]+"` gave all 21 heading lines (641, 957, 1235, ... 8267).
- ToC titles extracted with `sed -n '58,200p' | grep -E "^[0-9]+\."` to map chapters 1–21.
- Body headings verified by sed-ing 3 lines after each CHAPTER line (awk exact-match failed
  on heading lines — use sed slices instead).
- Per chapter: pack = opening ~85 lines + Glossary block (from "Glossary" to "Exercises").
  Ch20 had no Glossary section — its opening (error taxonomy) was the content anyway.
  Packs ran ~4.4–7 KB each; read 3 at a time, wrote 3 chapter files, repeat 7×.

## Budgets Observed (words×1.33 proxy; real BPE counts lower)
- SKILL.md body: 1,311 words ≈ 1,744 proxy — comfortably under 4,000.
- Chapters: 597–735 words / 3.9–5.1 KB each ≈ 800–980 proxy; real ~1,000–1,300 tokens
  (code-heavy text ≈ 3.5–3.8 chars/token). 1,000–1,800 target.
- glossary.md: 97 entries, 1,129 words ≈ 1,502 proxy — at the 1,500 cap after two cuts
  (128 entries → 116 → 97). Trim by dropping least-looked-up terms, not by wordiness.
- patterns.md: 1,018 words ≈ 1,354 proxy (cap 2,000). cheatsheet.md: 667 ≈ 887 (cap 1,200).

## The Overlay-Loss Incident (why write verification is step 6)
1. `mkdir` via terminal created the skill dir; then 24 `write_file` calls (21 chapters +
   glossary + patterns + cheatsheet) all returned `verified: true` with resolved paths.
2. A later `ls` in terminal showed the skill dir either missing or containing only a probe
   file — the bulk writes had landed in a filesystem overlay that was discarded mid-run.
3. Probe: `write_file` a marker, then `search_files`/`find` — only the marker was on the
   real FS. Confirmed loss of 24 composed files.
4. Recovery: rewrote all content via **execute_code** (which shares terminal's real FS —
   proven by earlier scratch files persisting in /tmp) with `pathlib.write_text` +
   `assert read_text() == content` per file. Wrote in 4 chapter batches (~5 files each)
   + 1 supporting-files batch + SKILL.md, printing total on-disk file count after each
   batch. Final `ls`/`du -sh` confirmed 25 files, 180K.

Lesson: bulk-write tools may report success against a discarded overlay. Verify on the
real FS (or write via execute_code with read-back) after EVERY batch, not at the end.

## Scan & Cleanup
- `python3 .../book-to-skill/tools/scan_generated_skill.py <skill-dir>` → exit 0,
  "no known injection or authority patterns found" (ran twice, incl. final confirm).
- Cleanup: removed workdir via `metadata.json["workdir"]` (json + shutil.rmtree), NOT a
  hardcoded path; also removed scratch packs. Final report listed all files with sizes.

## Final Inventory (25 files, 180K total)
- SKILL.md 9,478 B | glossary.md 7,110 B | patterns.md 6,996 B | cheatsheet.md 4,048 B
- chapters/: ch01 4,502 B … ch21 4,575 B (21 files, 3,863–5,107 B)
