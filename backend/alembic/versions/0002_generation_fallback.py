"""Add honest-fallback columns to generations.

Revision ID: 0002_generation_fallback
Revises: 0001_initial
Create Date: 2026-10-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_generation_fallback"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("generations", sa.Column("fallback_reason", sa.String(length=128), nullable=True))
    op.add_column("generations", sa.Column("requested_provider", sa.String(length=64), nullable=True))
    op.add_column("generations", sa.Column("requested_model", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "requested_model")
    op.drop_column("generations", "requested_provider")
    op.drop_column("generations", "fallback_reason")
    op.drop_column("generations", "is_fallback")
