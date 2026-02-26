"""Add token_count column to chunks table for accurate batching.

Tracks the accurate token count (via tiktoken) for each chunk.
Used by embedding worker to dynamically batch chunks while respecting
cumulative token limits per batch (prevents context overflow).

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # token_count is nullable to support chunks ingested before migration
    # Fallback: embedding_worker calculates on-the-fly if NULL
    op.add_column(
        "chunks",
        sa.Column("token_count", sa.Integer(), nullable=True),
    )
    # Index for efficient filtering/sorting by token count
    op.create_index(
        "chunks_token_count_idx",
        "chunks",
        ["token_count"],
        postgresql_where=sa.text("token_count IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("chunks_token_count_idx", table_name="chunks")
    op.drop_column("chunks", "token_count")
