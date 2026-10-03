"""Add explanation retry + grounding_check columns.

Revision ID: 0003_explanation_grounding
Revises: 0002_generation_fallback
Create Date: 2026-10-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_explanation_grounding"
down_revision: Union[str, None] = "0002_generation_fallback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column("explanation_retried", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("generations", sa.Column("grounding_check_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "grounding_check_json")
    op.drop_column("generations", "explanation_retried")
