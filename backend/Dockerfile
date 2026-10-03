# PathExplain API image — build from the **repo root** so `data/` is included.
#
#   docker build -f backend/Dockerfile -t pathexplain-api .
#
# Render: Root Directory = (empty), Dockerfile Path = ./backend/Dockerfile
FROM python:3.12.3-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/srv/data \
    # Cap concurrent Tesseract jobs (Render free tier ≈512 MB RAM).
    OCR_MAX_CONCURRENT=1 \
    OCR_MAX_QUEUE=2 \
    OCR_MAX_PAGES=1

# System OCR package (required for OCR_ENGINE=tesseract default).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/backend

COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install -r /srv/backend/requirements.txt

COPY backend/ /srv/backend/
# Authentic scan pages, sample_reports.json (30 cases), OCR disk cache.
COPY data/ /srv/data/

# Quick integrity check at build time (fails the image if data/ was omitted).
RUN test -f /srv/data/sample_reports.json \
    && python -c "import json; n=len(json.load(open('/srv/data/sample_reports.json'))); assert n>=30, n" \
    && test -d /srv/data/scan_cache/TCGA-B6-A401 \
    && test -f /srv/data/scan_cache/TCGA-B6-A401/manifest.json \
    && test -f /srv/data/scan_cache/TCGA-B6-A401/page-01.jpg

# Render sets $PORT; health check hits /api/health
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
