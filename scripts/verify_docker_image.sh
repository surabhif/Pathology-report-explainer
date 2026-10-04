#!/usr/bin/env bash
# Build the PathExplain API image from the repo root and assert data/ is inside it.
# Usage (from repo root):
#   bash scripts/verify_docker_image.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE_TAG="${IMAGE_TAG:-pathexplain-api:ci}"

echo "Building ${IMAGE_TAG} (context=., Dockerfile=backend/Dockerfile)…"
docker build -f backend/Dockerfile -t "$IMAGE_TAG" .

echo "Verifying sample_reports.json + scan_cache inside the image…"
docker run --rm -i --entrypoint python "$IMAGE_TAG" - <<'PY'
import json
import sys
from pathlib import Path

data = Path("/srv/data")
sample = data / "sample_reports.json"
assert sample.is_file(), f"missing {sample}"
reports = json.loads(sample.read_text(encoding="utf-8"))
assert len(reports) >= 30, f"expected ≥30 sample reports, got {len(reports)}"
cancers = {r.get("cancer_type") for r in reports}
assert {"BRCA", "COAD", "LUAD"} <= cancers, cancers

cache = data / "scan_cache"
assert cache.is_dir(), f"missing {cache}"
# Demo + stratified set barcodes must be present with manifests + pages.
required = [
    "TCGA-B6-A401",
    "TCGA-A6-3808",
    "TCGA-44-8119",
    "TCGA-BH-A0HA",
    "TCGA-D5-6923",
    "TCGA-44-6777",
]
missing = []
for barcode in required:
    case = cache / barcode
    manifest = case / "manifest.json"
    page = case / "page-01.jpg"
    if not (manifest.is_file() and page.is_file()):
        missing.append(barcode)
assert not missing, f"scan_cache incomplete for {missing}"

# App path helpers must resolve to /srv/data when DATA_DIR is set (image default).
from app.config import get_settings
from app.services.scan_assets import scan_cache_root
from app.services.ocr.cache import ocr_cache_root

settings = get_settings()
assert Path(settings.data_dir) == Path("/srv/data"), settings.data_dir
assert scan_cache_root() == Path("/srv/data/scan_cache"), scan_cache_root()
assert ocr_cache_root() == Path("/srv/data/ocr_cache"), ocr_cache_root()
print(
    f"OK: {len(reports)} sample reports, scan_cache present, "
    f"DATA_DIR={settings.data_dir}, OCR_MAX_CONCURRENT={settings.ocr_max_concurrent}"
)
PY

echo "Docker image data integrity check passed."
