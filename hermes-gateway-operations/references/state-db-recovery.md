# State.db FTS5 Corruption Recovery

Complete recovery procedure for when `state.db` shows FTS5 corruption
(`fts5: corruption found reading blob`) and `PRAGMA integrity_check` fails.

## Step 1: Stop Gateway

```bash
sudo <HOME>/.hermes/hermes-agent/venv/bin/hermes gateway stop --system
```

## Step 2: Backup

```bash
cp ~/.hermes/state.db ~/.hermes/state.db.corrupt
```

## Step 3: Dump non-FTS data

Extract everything except FTS virtual tables:

```bash
cd ~/.hermes
sqlite3 state.db.corrupt ".dump" 2>/dev/null \
  | grep -v 'messages_fts' \
  | grep -v 'sqlite_' \
  | grep -v 'CREATE VIRTUAL' \
  > /tmp/clean_dump.sql
```

## Step 4: Rebuild in Python

The `.dump` import via `sqlite3 < file.sql` often fails because of duplicate
keys and the FTS triggers. Use Python to split CREATE and INSERT, import with
error tolerance:

```python
import sqlite3, os

corrupt = '<HOME>/.hermes/state.db.corrupt'
target = '<HOME>/.hermes/state.db'
dump = open('/tmp/clean_dump.sql').read()

# Parse CREATE and INSERT separately
creates = []
inserts = []
skip_fts = False
current_create = []
in_create = False

for line in dump.split('\n'):
    if 'messages_fts' in line or 'sqlite_sequence' in line:
        skip_fts = True
        if current_create:
            current_create = []
            in_create = False
        continue
    if skip_fts:
        if line.strip().endswith(';') and not line.startswith('INSERT'):
            skip_fts = False
        continue
    if line.startswith('PRAGMA') or line.startswith('BEGIN') or \
       line.startswith('COMMIT') or line.startswith('/*') or \
       'CREATE VIRTUAL TABLE' in line:
        continue
    if line.startswith('INSERT INTO'):
        inserts.append(line)
        in_create = False
        current_create = []
    elif line.startswith('CREATE TABLE') or line.startswith('CREATE INDEX') \
         or line.startswith('CREATE TRIGGER') or line.startswith('CREATE UNIQUE'):
        if current_create:
            creates.append('\n'.join(current_create))
        in_create = True
        current_create = [line]
    elif in_create:
        current_create.append(line)
        if line.strip().endswith(';'):
            creates.append('\n'.join(current_create))
            in_create = False
            current_create = []

if current_create:
    creates.append('\n'.join(current_create))

# Create new DB
if os.path.exists(target):
    os.remove(target)
conn = sqlite3.connect(target)

# Apply creates (skip duplicates)
for c in creates:
    try:
        conn.execute(c)
    except:
        pass  # table already exists from earlier batch
conn.commit()

# Apply inserts with error tolerance
errors = 0
for ins in inserts:
    try:
        conn.execute(ins)
    except:
        errors += 1
conn.commit()

# Set FTS rebuild markers
conn.execute(
    "INSERT OR REPLACE INTO state_meta (key, value) "
    "VALUES ('fts_rebuild_high_water', '-1')"
)
conn.execute(
    "DELETE FROM state_meta WHERE key = 'fts_rebuild_progress'"
)
conn.commit()

# Verify
for t in ['sessions','messages','gateway_routing','delivery_obligations']:
    c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {c}")
print(f"  INSERT errors: {errors}/{len(inserts)}")
conn.close()
```

## Step 5: Verify Integrity

```bash
sqlite3 ~/.hermes/state.db "PRAGMA integrity_check;"
# Must return "ok"
```

## Step 6: Start Gateway

```bash
sudo <HOME>/.hermes/hermes-agent/venv/bin/hermes gateway start --system
```

Hermes will rebuild the FTS indexes from scratch on the next message insert.

## Expected Data Loss

- ~1-2% of messages lost (corrupt btree pages are unrecoverable)
- ~2% of sessions may be lost
- gateway_routing, delivery_obligations, state_meta: usually fully recoverable

In the 2026-07-31 recovery: 44/45 sessions, 4955/5073 messages, all routing
and obligations recovered.
