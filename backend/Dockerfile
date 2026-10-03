# PathExplain API — includes Tesseract for free-tier OCR on Render.
FROM python:3.12.3-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System OCR package (required for OCR_ENGINE=tesseract default).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Render sets $PORT; health check hits /api/health
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
