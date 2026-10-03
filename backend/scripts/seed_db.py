#!/usr/bin/env python3
"""Seed the database (users, sample reports, prompts, batches).

Usage (from backend/):
  python scripts/seed_db.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal, init_db
from app.seed import seed_all


async def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        await seed_all(db)
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
