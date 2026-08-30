# Derived Hermes image with passwordless sudo + Persian pipeline + book-to-skill deps.
# Base is the OFFICIAL public image, pinned by digest so every rebuild is
# byte-identical (NO local/private image refs — this file is shareable/gittable).
FROM nousresearch/hermes-agent@sha256:44733d69163211c82c3c6f7ab0ba4bb82e6995870014fc0308b6863fb2246b50

COPY wheels /opt/hermes-wheels

# Phase A: bootstrap pip into the venv + install offline deps (incl CPU torch + STT soundfile).
RUN /opt/hermes/.venv/bin/python3 /opt/hermes-wheels/get-pip.py --no-index --find-links=/opt/hermes-wheels \
 && /opt/hermes/.venv/bin/python3 -m pip install --no-index --find-links=/opt/hermes-wheels \
        PySocks \
        sherpa_onnx numpy python_docx python_pptx openpyxl weasyprint arabic_reshaper python_bidi pymupdf requests \
        pypdf pdfminer.six ebooklib beautifulsoup4 soupsieve striprtf trafilatura \
        soundfile cffi \
        torch==2.13.0+cpu torchvision==0.28.0+cpu \
 && /opt/hermes/.venv/bin/python3 -c "import sherpa_onnx, pypdf, pdfminer, ebooklib, bs4, striprtf, trafilatura, docx, pptx, openpyxl, torch, torchvision; print('PHASE A OK: core deps + torch', torch.__version__)"

# Phase B: docling + full transitive graph — OFFLINE from the wheels dir, with
# versions pinned to exactly what is proven working on the host (no CUDA, no
# version-mismatch backtracking).
RUN /opt/hermes/.venv/bin/python3 -m pip install --no-index --find-links=/opt/hermes-wheels \
        docling docling-core docling-slim docling-ibm-models docling-parse pypdfium2 \
        onnxruntime transformers tokenizers safetensors accelerate \
 && rm -rf /opt/hermes-wheels \
 && /opt/hermes/.venv/bin/python3 -c "import docling, onnxruntime; print('PHASE B OK: docling', getattr(docling,'__version__','?'), '| onnxruntime', onnxruntime.__version__)"

# Final gate: everything visible from the hermes venv AND from plain `python3`
# (extract.py and other scripts call `python3`, not the venv path). We add a
# .pth so the SYSTEM interpreter also sees the venv's site-packages — same
# benefit as the old include-system-site-packages trick, but in the right
# direction (everything lives in the venv; system merely sees it).
RUN /opt/hermes/.venv/bin/python3 -c "import sherpa_onnx, numpy, docx, pptx, openpyxl, weasyprint, arabic_reshaper, bidi, fitz, requests, pypdf, pdfminer, ebooklib, bs4, striprtf, trafilatura, torch, torchvision, docling; print('DEPS READY in hermes venv:', sherpa_onnx.__version__, '| torch', torch.__version__, '| docling', getattr(docling,'__version__','?'))" \
 && echo '/opt/hermes/.venv/lib/python3.13/site-packages' > /usr/local/lib/python3.13/dist-packages/hermes-venv.pth \
 && /usr/bin/python3 -c "import pypdf, docx, pptx, docling; print('SYSTEM python3 sees venv deps: OK')"
