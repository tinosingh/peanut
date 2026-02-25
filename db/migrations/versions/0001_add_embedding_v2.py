"""Add embedding_v2 column to chunks for model upgrade path.

Revision ID: 0001
Revises:
Create Date: 2026-02-24

Epic 2 Story 2.3 — embedding_v2 VECTOR(768) column allows zero-downtime
model swap: populate v2 while serving v1, then atomic pointer flip.
"""
from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # embedding_v2 is nullable — populated by background re-embed job
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_v2 vector(768)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS chunks_ann_v2_idx
        ON chunks USING HNSW (embedding_v2 vector_cosine_ops)
        WHERE embedding_v2 IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_ann_v2_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_v2")
