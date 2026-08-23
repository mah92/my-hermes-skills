---
name: hermes-translation-skill
description: "Use when translating a markdown/text file via LLM API."
version: 1.0.0
author: Ali Sani
license: MIT
metadata:
  hermes:
    tags: [translation, persian, deepseek, avalai, markdown, novel, glossary]
    related_skills: [hermes-libgen-book-download-skill, hermes-agent]
---

# Translation via LLM API (verified pipeline)

Batch-translate markdown/text files (English → Persian by default) through an
OpenAI-compatible chat API, chunked at paragraph boundaries, resumable, with
glossary support. Verified on Caves of Steel chapter 1 (14 chunks, ~18K chars).

## When to Use
- Translate a book chapter/novel/document to Persian (or another language)
- Any long text that exceeds one-shot API output limits

## Key facts (learned the hard way — READ these)
- The REAL working endpoint on this box is the Hermes model provider:
  base `https://api.avalai.ir/v1/chat/completions`, model `deepseek-v4-flash`,
  key from `HERMES_CUSTOM_API_AVALAI_IR_API_KEY` in ~/.hermes/.env.
- The raw DeepSeek key (`DEEPSEEK_API_KEY` + api.deepseek.com) returns
  HTTP 402 Payment Required — no balance. Do NOT use it.
- Rate limits are real: burst calls → HTTP 429. Pace: sleep 8s between chunks,
  backoff 15s*attempt on 429/5xx/timeouts.
- /tmp can be cleaned between sessions — ALWAYS write per-chunk output to a
  parts directory so a killed run resumes instead of losing everything.

## Usage
```bash
python3 ~/.hermes/skills/mlops/hermes-translation-skill/scripts/translate_markdown.py \
  --input "~/Downloads/book/ch1.md" --glossary glossary_fa.md --send
# resume a partial run (parts dir exists): just re-run the same command
# --dry-run: print chunk plan only. --max-chars 1500 (default) per chunk.
```

## Pipeline (inside the script)
1. Split text into chunks at PARAGRAPH boundaries (never mid-paragraph),
   ~1500 chars each.
2. For each chunk: chat completion with a strict system prompt:
   - preserve markdown/paragraph/blank-line structure EXACTLY
   - ONE dialogue line per paragraph (each speaker's utterance on its own
     paragraph) — the model tends to merge dialogue lines otherwise
   - glossary (character/term names) for consistency across chunks
   - literary, fluent target language, respectful register
3. Write each translated chunk to `<output>.parts/chunk_NN.md` IMMEDIATELY
   (resume-safe); skip existing parts on rerun.
4. Assemble parts in order → post-process: split same-line adjacent
   dialogue (`» «` → `»\n\n«`).
5. Verify: report source vs output paragraph counts and char counts.
6. Optional --send: upload via Bale sendDocument (chat YOUR_BALE_CHAT_ID).

## Pitfalls
- If the model merges paragraphs despite the prompt, post-process with:
  `re.sub(r'» {1,3}«', '»\n\n«', text)` — do NOT use `\s+` between the
  guillemets: it also eats real paragraph breaks across two lines.
- Chunks of 2800+ chars time out on this model — keep 1500.
- Always pass --glossary for fiction (names must stay consistent).
