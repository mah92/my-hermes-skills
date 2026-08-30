# Image rebuild with baked venv deps + fleet migration (verified 2026-08-30)

Background: bot containers run `nousresearch/hermes-agent-sudo` (image python 3.13).
Historically deps were installed into the SYSTEM python with
`include-system-site-packages=true` in the venv cfg — owner rule changed this:
«همه چیز باید توی venv هرمس نصب بشه» (everything installs INTO `/opt/hermes/.venv`).

Key architectural fact: `/opt/hermes/.venv/bin/python3` is a SYMLINK to
`/usr/bin/python3.13` but the venv has its OWN `lib/python3.13/site-packages`.
Installing into the venv therefore does NOT make packages visible to plain
`python3`; both interpreters must be covered (extract.py calls `python3` by
default). Fix: at build end write the venv site-packages path into a `.pth`:

```bash
echo '/opt/hermes/.venv/lib/python3.13/site-packages' \
  > /usr/local/lib/python3.13/dist-packages/hermes-venv.pth
```

## Build recipe (final working Dockerfile shape)

Source dir: `/home/oem/profiles-containers/sudo-image/` (Dockerfile + `wheels/`
holding get-pip.py and ~157 offline wheels).

```
FROM nousresearch/hermes-agent-sudo:20260827
COPY wheels /opt/hermes-wheels
RUN /opt/hermes/.venv/bin/python3 /opt/hermes-wheels/get-pip.py --no-index --find-links=/opt/hermes-wheels \
 && /opt/hermes/.venv/bin/python3 -m pip install --no-index --find-links=/opt/hermes-wheels \
        PySocks \
        sherpa_onnx numpy python_docx python_pptx openpyxl weasyprint arabic_reshaper python_bidi pymupdf requests \
        pypdf pdfminer.six ebooklib beautifulsoup4 soupsieve striprtf trafilatura \
        torch==2.13.0+cpu torchvision==0.28.0+cpu \
 && /opt/hermes/.venv/bin/python3 -c "import sherpa_onnx, pypdf, ...; print('PHASE A OK')"
RUN /opt/hermes/.venv/bin/python3 -m pip install --no-index --find-links=/opt/hermes-wheels \
        docling docling-core docling-slim docling-ibm-models docling-parse pypdfium2 \
        onnxruntime transformers tokenizers safetensors accelerate \
 && rm -rf /opt/hermes-wheels \
 && /opt/hermes/.venv/bin/python3 -c "import docling, onnxruntime; print('PHASE B OK')"
RUN .../python3 -c "import ... torch, torchvision, docling; print('DEPS READY')" \
 && echo '/opt/hermes/.venv/lib/python3.13/site-packages' > /usr/local/lib/python3.13/dist-packages/hermes-venv.pth \
 && /usr/bin/python3 -c "import pypdf, docx, pptx, docling; print('SYSTEM python3 sees venv deps: OK')"
```

Build with network (needed only for Phase B if online; final version is fully
offline so really it's not needed):
`docker build --network=host -t nousresearch/hermes-agent-sudo:20260830 .`

Test BEFORE migrating: run the image with `--entrypoint sh` mounting a test script;
assert imports from BOTH interpreters + a pptx/docx roundtrip + `extract.py --check`.

## Wheel supply chain pitfalls (each cost 5-40 min)

- **torch must be CPU wheels from `https://download.pytorch.org/whl/cpu`**:
  `torch-2.13.0+cpu-cp313-cp313-manylinux_2_28_x86_64.whl` (184M) +
  `torchvision-0.28.0+cpu-...` (1.8M). If pip resolves torch from PyPI in
  --no-index mode it backtracks toward a CUDA bundle far too big to download
  here (torch 821M + nvidia_cudnn 571M + nvidia_cublas 393M + cudart…).
  Use `pip download --no-deps -i https://download.pytorch.org/whl/cpu -d dir torch==2.13.0+cpu torchvision==0.28.0+cpu`.
- **Pin EVERY wheel to the host venv version** — one version per package in
  `wheels/`. Duplicates (two pydantic_core, sympy 1.13.1 + 1.14.0, typer
  0.26.8 + 0.27.2, semchunk 3.2.5 + 4.1.1) make pip descend into a
  "dependency graph is too complex for pip to solve efficiently" backtracking
  that runs 15-40+ min then fails.
- **docling graph specifics** (docling 2.123.1 / docling-core 2.92.0 /
  docling-slim 2.123.1):
  - omegaconf 2.3.1 REQUIRES `antlr4-python3-runtime==4.9.*`; that exact
    version has NO wheel — only an sdist `antlr4-python3-runtime-4.9.3.tar.gz`.
    pip builds it from source offline (needs setuptools wheel present).
  - semchunk must be `<4.0.0` → 3.2.5; semchunk dep mpire (2.10.2) + dill.
  - typer must be `<0.27.0` → 0.26.8 (0.27.2 exists but is rejected).
  - pydantic-core: docling-core wants `==2.46.5`, pydantic 2.13.4 wants
    `==2.46.4` — provide BOTH wheels and let pip pick per edge.
  - transformers must be older than 5.9 (`!=5.0-5.3, >=4.42, <5.9`) → 5.16.1 ok,
    but watch for the sys_platform=="darwin" variants in metadata.
  - hf-xet, huggingface-hub, pdfminer.six, tree-sitter family, opencv-python,
    shapely, pyclipper, rapidocr (OCR) all come along; opencv-python wheel is
    cp37-abi3 manylinux_2_28 (fine on cp313).
  - Deleted/absent variants that broke earlier builds: pluggy, huggingface-hub
    (needed), typer version, doclang, semchunk version, mpire, pydantic-core
    version — the failure loop teaches: whenever "Could not find a version that
    satisfies the requirement X", check X's wheel presence + version pin, add
    it, rebuild (each build ~4-6 min).
- **pypi.org direct is ~12-25s/hit from this network; sjtu mirror (~1.7s) is
  reachable DIRECT from the HOST but NOT from inside the build container**
  (times out even with --network=host). => do all `pip download` on the HOST,
  build offline with --no-index. Phase B online attempts (pypi directly) hung
  40+ min with zero progress (pip slept, 0 sockets, 0% CPU).

## Post-build STT requirement: soundfile + cffi (2026-08-30)
stt.py (`hermes-persian-stt/scripts/stt.py`) needs `numpy`, `soundfile`, `sherpa_onnx`.
First venv-only build had numpy+sherpa_onnx but NOT soundfile →
`ModuleNotFoundError: No module named 'soundfile'` on first STT round-trip.
Fix: `pip download --no-deps ... soundfile cffi` into wheels/, add both to the
Phase A pip line. Post-build gate: `docker run --rm ... '<venv-python> -c "import
soundfile, sherpa_onnx"'`.

## Removing the host-venv ro mount (2026-08-30, done after venv-bake)
With everything baked into the image, `docker-compose.yaml` no longer mounts
`/home/oem/.hermes/hermes-agent/venv` (was `:ro` on all 14 services). Do NOT
remove it blindly — the STT provider command pointed INTO that mount:
`/home/oem/.hermes/hermes-agent/venv/bin/python ...stt.py`. Migration order:
1. `sed -i 's|/home/oem/.hermes/hermes-agent/venv/bin/python|/opt/hermes/.venv/bin/python|g' ~/.hermes/profiles/*/config.yaml`
2. Verify: `grep -rl "hermes-agent/venv/bin/python" .../config.yaml` → 0,
   `grep -l "/opt/hermes/.venv/bin/python" ...` → 14.
3. `sed -i '\|/home/oem/.hermes/hermes-agent/venv:/home/oem/.hermes/hermes-agent/venv:ro|d' docker-compose.yaml`
   (back up first), `docker compose config --quiet`.
4. `docker compose up -d --force-recreate` (background=true), then verify
   `docker inspect hermes-<x> ... | grep -c venv` → 0 and real STT round-trip
   (generate a 2s wav in-container, run stt.py, expect exit 0).
Verified: all 14 bots running+connected, sessions preserved, extract.py works.

## Migration runbook (verified 2026-08-30, all 14 bots)

1. `docker images nousresearch/hermes-agent-sudo` + `grep -n "image:" docker-compose.yaml`.
   Compose may point at a deleted tag (it pointed at 20260828 which was gone).
   Backup compose, `sed -i 's|image: nousresearch/hermes-agent-sudo:20260828|image: nousresearch/hermes-agent-sudo:20260830|g'`,
   `docker compose config --quiet`.
2. WAL-safe backup via python `sqlite3 src.backup(dst)` per DB (state.db ~231M,
   memory_store.db, kanban.db, projects.db, verification_evidence.db) +
   config tgz + workspace tgz → `<backup_root>/pre-migration-<ts>/`.
   Verify `PRAGMA integrity_check` after (printed `ok` everywhere).
3. Canary: `docker compose up -d --force-recreate <low-stakes-bot>` (background=true —
   the guard treats compose up as long-lived). Verify: new image tag in
   `docker ps`, `pgrep -f "gateway run"`, `gateway_state.json`
   `gateway_state: running | bale: connected`, venv + system imports.
4. Batch the rest EXCEPT the priority user.
5. Priority user (heaviest-active profile) LAST: fresh backup right before, recreate, verify
   image/gateway/bale + open sessions preserved
   (`SELECT id, title, source FROM sessions WHERE ended_at IS NULL`) + the
   originally-broken op now works in-container.
6. Full sweep: every container shows 20260830 and `running connected`.
