"""gateway: request_traces.request_json column.

Add ``request_json JSONB`` to ``request_traces`` to support
``POST /v1/gateway/traces/{id}/replay`` (H3). Replay needs the original
canonical request body to re-dispatch.

Revision ID: 054_gateway_trace_request_json
Revises: 053_gateway_guardrails
"""

from __future__ import annotations

from alembic import op

revision = "054_gateway_trace_request_json"
down_revision = "053_gateway_guardrails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE request_traces ADD COLUMN IF NOT EXISTS request_json JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE request_traces DROP COLUMN IF EXISTS request_json")
