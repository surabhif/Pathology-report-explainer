"""Initial schema for Pathology Report Explainer MVP.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("invite_token", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_invite_token", "users", ["invite_token"], unique=True)

    op.create_table(
        "session_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_session_tokens_token", "session_tokens", ["token"], unique=True)

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tcga_barcode", sa.String(64), nullable=False),
        sa.Column("cancer_type", sa.String(16), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("report_text", sa.Text(), nullable=False),
        sa.Column("gdc_metadata", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reports_tcga_barcode", "reports", ["tcga_barcode"], unique=True)
    op.create_index("ix_reports_cancer_type", "reports", ["cancer_type"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("name", "version", "kind", name="uq_prompt_name_ver_kind"),
    )

    op.create_table(
        "generations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("prompt_extract_version", sa.String(64), nullable=False),
        sa.Column("prompt_explain_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("facts_json", sa.JSON(), nullable=False),
        sa.Column("explanation_json", sa.JSON(), nullable=False),
        sa.Column("reading_level_original", sa.Float(), nullable=True),
        sa.Column("reading_level_explanation", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generations_report_id", "generations", ["report_id"])

    op.create_table(
        "evaluation_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("cancer_types", sa.JSON(), nullable=False),
        sa.Column("report_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "task_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("batch_type", sa.String(32), nullable=False),
        sa.Column("evaluation_set_id", sa.Integer(), sa.ForeignKey("evaluation_sets.id"), nullable=True),
        sa.Column("assigned_user_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "annotation_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("task_batches.id"), nullable=False),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("gold_labels", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_annotation_tasks_batch_id", "annotation_tasks", ["batch_id"])
    op.create_index("ix_annotation_tasks_assignee_id", "annotation_tasks", ["assignee_id"])

    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("task_batches.id"), nullable=False),
        sa.Column("generation_id", sa.Integer(), sa.ForeignKey("generations.id"), nullable=False),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=True),
        sa.Column("flagged_sentences", sa.JSON(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_review_tasks_batch_id", "review_tasks", ["batch_id"])
    op.create_index("ix_review_tasks_assignee_id", "review_tasks", ["assignee_id"])

    op.create_table(
        "auto_check_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("task_batches.id"), nullable=True),
        sa.Column("generation_ids", sa.JSON(), nullable=False),
        sa.Column("results_json", sa.JSON(), nullable=False),
        sa.Column("prompt_tags", sa.String(256), nullable=False),
        sa.Column("model_tags", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "rubrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("version"),
    )


def downgrade() -> None:
    op.drop_table("rubrics")
    op.drop_table("auto_check_runs")
    op.drop_table("review_tasks")
    op.drop_table("annotation_tasks")
    op.drop_table("task_batches")
    op.drop_table("evaluation_sets")
    op.drop_table("generations")
    op.drop_table("prompt_versions")
    op.drop_table("reports")
    op.drop_table("session_tokens")
    op.drop_table("users")
