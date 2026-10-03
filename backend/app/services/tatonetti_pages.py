"""Fetch original Textract input page images from the Tatonetti lab S3 zip.

Archive (~24GB): https://tatonettilab-resources.s3.us-west-1.amazonaws.com/tcga-path-reports/imgs_for_aws.zip
Supports HTTP range requests — we use remotezip to pull only members for selected
TCGA case barcodes (never download the whole archive).
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TATONETTI_IMGS_ZIP_URL = (
    "https://tatonettilab-resources.s3.us-west-1.amazonaws.com/tcga-path-reports/imgs_for_aws.zip"
)

_MEMBER_RE = re.compile(
    r"^imgs_for_aws/(TCGA-[A-Za-z0-9]+-[A-Za-z0-9]+)\.[^/]+_Page_(\d+)\.(jpe?g|png)$",
    re.IGNORECASE,
)


def parse_member(name: str) -> tuple[str, int] | None:
    """Return (case_submitter_id, page_number) or None."""
    m = _MEMBER_RE.match(name.replace("\\", "/"))
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2))


def list_zip_members_for_cases(
    case_ids: list[str],
    *,
    url: str = TATONETTI_IMGS_ZIP_URL,
) -> dict[str, list[tuple[int, str]]]:
    """Map case_id → [(page, zip_member_path), ...] using remote central directory only."""
    from remotezip import RemoteZip

    wanted = {c.upper() for c in case_ids}
    out: dict[str, list[tuple[int, str]]] = {c: [] for c in wanted}
    with RemoteZip(url) as zf:
        for name in zf.namelist():
            parsed = parse_member(name)
            if not parsed:
                continue
            case, page = parsed
            if case in wanted:
                out[case].append((page, name))
    for case in out:
        out[case].sort(key=lambda t: t[0])
    return out


def _shrink_jpeg(image_bytes: bytes, *, max_width: int = 1400, quality: int = 82) -> tuple[bytes, int, int]:
    """Downscale/recompress for a small local cache while keeping OCR-usable resolution."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        nh = int(h * (max_width / w))
        img = img.resize((max_width, nh), Image.Resampling.LANCZOS)
        w, h = img.size
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), w, h


def fetch_tatonetti_pages(
    barcode: str,
    out_dir: Path,
    *,
    max_pages: int = 2,
    url: str = TATONETTI_IMGS_ZIP_URL,
    force: bool = False,
) -> dict[str, Any] | None:
    """Range-fetch original Textract input pages for one case into out_dir.

    Returns a scan manifest fragment or None if the case is missing from the zip.
    """
    from remotezip import RemoteZip

    from app.services.scan_assets import case_submitter_id

    submitter = case_submitter_id(barcode)
    members_map = list_zip_members_for_cases([submitter], url=url)
    members = members_map.get(submitter.upper()) or []
    if not members:
        logger.info("tatonetti.pages.none case=%s", submitter)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    pages: list[dict[str, Any]] = []
    source_members: list[str] = []

    with RemoteZip(url) as zf:
        for page_num, member in members[:max_pages]:
            filename = f"page-{page_num:02d}.jpg"
            dest = out_dir / filename
            raw = zf.read(member)
            shrunk, w, h = _shrink_jpeg(raw)
            dest.write_bytes(shrunk)
            pages.append(
                {
                    "page": page_num,
                    "filename": filename,
                    "width": w,
                    "height": h,
                    "relpath": f"{submitter}/{filename}",
                    "source_member": member,
                    "source_bytes_raw": len(raw),
                    "source_bytes_cached": len(shrunk),
                }
            )
            source_members.append(member)
            logger.info(
                "tatonetti.page.cached case=%s page=%s raw=%d cached=%d",
                submitter,
                page_num,
                len(raw),
                len(shrunk),
            )

    return {
        "barcode": barcode,
        "case_submitter_id": submitter,
        "pages": pages,
        "source": "tatonetti_textract_input",
        "label": "Original pathology report page image (Tatonetti lab / Textract input)",
        "citation": (
            "Page images published by the Tatonetti lab as the AWS Textract inputs for "
            "TCGA-Reports (Kefeli et al., Patterns 2024): "
            "https://tatonettilab-resources.s3.us-west-1.amazonaws.com/tcga-path-reports/imgs_for_aws.zip "
            f"(members: {', '.join(source_members)})."
        ),
        "tatonetti_zip_url": url,
        "tatonetti_members": source_members,
        "is_real_scan": True,
        "scorable_for_ocr_benchmark": True,
    }
