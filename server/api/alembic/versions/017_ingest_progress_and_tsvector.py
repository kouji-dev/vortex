"""ingest progress fields and tsvector on document_chunks

Revision ID: 017_ingest_progress_tsvector
Revises: 016_catalog_api_model_id
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "017_ingest_progress_tsvector"
down_revision = "016_catalog_api_model_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("chunks_total", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("chunks_done", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(sa.text(
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_search_vector "
        "ON document_chunks USING GIN (search_vector)"
    ))
    op.execute(sa.text(
        "UPDATE document_chunks SET search_vector = to_tsvector('english', content) "
        "WHERE content IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_document_chunks_search_vector"))
    op.execute(sa.text("ALTER TABLE document_chunks DROP COLUMN IF EXISTS search_vector"))
    op.drop_column("documents", "chunks_done")
    op.drop_column("documents", "chunks_total")
