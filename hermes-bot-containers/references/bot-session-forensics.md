# Bot session forensics & the book-to-skill python pitfall

Verified 2026-08-30 while diagnosing a heavy-user profile's "suspicious approval" request.

## Recipe — review a bot's recent session / find what an approval was

The per-bot session DB is the state.db inside the bound profile dir
(`~/.hermes/profiles/<name>/state.db`); gateway_state.json next to it tells you
the gateway is live. Open it READ-ONLY (gateway may be writing; WAL mode):

```bash
PY=/opt/hermes/.venv/bin/python3   # or host hermes venv
$PY - <<'EOF'
import sqlite3
con = sqlite3.connect('file:/home/oem/.hermes/profiles/<name>/state.db?mode=ro', uri=True)
cur = con.cursor()
# newest sessions first (bot DMs + cron)
for r in cur.execute("SELECT id, source, user_id, chat_id, display_name, "
                     "started_at, last_activity_at, message_count, title "
                     "FROM sessions ORDER BY last_activity_at DESC LIMIT 6"):
    print(r)
# tail a session: note the schema — columns are `id` (msg id), NOT session_id;
# messages carry role/tool_name/effect_disposition/tool_calls
sid = '<session id from above>'
for r in cur.execute("SELECT id, role, substr(content,1,400), effect_disposition, "
                     "tool_name, substr(tool_calls,1,200) FROM messages "
                     "WHERE session_id=? ORDER BY id DESC LIMIT 20", (sid,)):
    print(r)
EOF
```

- A message row with `effect_disposition in ('require_approval','suspended','blocked')`
  is a pending/intercepted action. Absent rows = nothing pending.
- Tool-output `"approval": "Command required approval … and was approved by the user"`
  vs `"auto-approved by smart approval"` distinguishes user-approved from auto-approved.
- `MAX(id)` per session tells you the session's true end; content after the last
  assistant msg may be mid-flight tool calls.

## Case study — "سشن مدغان یعنی چی؛ approve مشکوک داره"

Symptom: bot asks the user to approve `python3 -m pip install --break-system-packages pypdf`.

Root cause (verified): book-to-skill's `extract.py` ran under the container's SYSTEM
python3 (3.13) which has NO pypdf → log reads `Trying pdftotext... not available /
Trying pypdf... not available / Trying pdfminer.six... FAILED`, and because the system
python is PEP 668 (externally-managed), the naive fix the agent reaches for is
`--break-system-packages` — which is what triggered the approval prompt. NOT malicious,
but the wrong fix: it mutates the system interpreter and the approval looks suspicious.

Correct fix — no install at all: the container's hermes venv ALREADY has
pypdf/ebooklib/bs4/striprtf (installed fleet-wide 2026-08-29). Run the extract with the
venv interpreter:

```
BOOK_SKILL_WORKDIR=/tmp/out PYTHON_BIN=/opt/hermes/.venv/bin/python3 \
  /opt/hermes/.venv/bin/python3 <skills>/book-to-skill/scripts/extract.py \
  <book.pdf> --mode text --install-missing no
```

Verified end-to-end 2026-08-30: Playing_to_Win_Lafley_Martin.pdf → 306 pages /
86,921 words / ~115K tokens / 8 chapters, zero installs.

Rules for container agents:
1. NEVER approve/issue `pip install --break-system-packages` on a container — use the
   venv interpreter (`/opt/hermes/.venv/bin/python3`), which already carries the
   book-to-skill deps.
2. When extract.py reports "Trying … not available" for every parser, the FIRST thing
   to check is WHICH python it ran under (`which python3` / `PYTHON_BIN`), not whether
   packages are missing — `extract.py --check` distinguishes the two.
