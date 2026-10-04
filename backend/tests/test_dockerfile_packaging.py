"""Static checks that the Docker packaging shape stays correct for Render."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_dockerfile_copies_data_from_repo_root_context():
    df = (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "WORKDIR /srv/backend" in df
    assert "COPY backend/requirements.txt" in df
    assert "COPY backend/ /srv/backend/" in df
    assert "COPY data/ /srv/data/" in df
    assert "DATA_DIR=/srv/data" in df
    assert "OCR_MAX_CONCURRENT=1" in df
    assert "OCR_MAX_QUEUE=2" in df
    # Build-time integrity assertions stay in the image recipe.
    assert "sample_reports.json" in df
    assert "scan_cache" in df


def test_root_dockerignore_excludes_frontend_keeps_data():
    text = (REPO / ".dockerignore").read_text(encoding="utf-8")
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert "frontend/" in lines
    assert ".git/" in lines
    assert any("node_modules" in ln for ln in lines)
    assert any(".venv" in ln for ln in lines)
    assert any(ln.endswith("*.db") or ln == "*.db" for ln in lines)
    assert "data/" not in lines
    assert "data" not in lines
