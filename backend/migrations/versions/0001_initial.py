"""Initial tables.

Revision ID: 0001
Revises:
Create Date: 2025-01-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("candidate_version", sa.String(), nullable=False),
        sa.Column("champion_version", sa.String(), nullable=True),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("offline_status", sa.String(), nullable=False, server_default="skipped"),
        sa.Column("online_status", sa.String(), nullable=False, server_default="skipped"),
        sa.Column("triggered_by", sa.String(), nullable=False, server_default="api"),
        sa.Column("model_type", sa.String(), nullable=False, server_default="llm"),
        sa.Column("registry_type", sa.String(), nullable=False, server_default="none"),
        sa.Column("serving_type", sa.String(), nullable=False, server_default="none"),
        sa.Column("gatekeeper_yaml", sa.String(), nullable=False),
        sa.Column("github_context", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "gate_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("gate_name", sa.String(), nullable=False),
        sa.Column("gate_type", sa.String(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("comparator", sa.String(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "canary_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("champion_latency_p50_ms", sa.Float(), nullable=True),
        sa.Column("champion_latency_p95_ms", sa.Float(), nullable=True),
        sa.Column("challenger_latency_p50_ms", sa.Float(), nullable=True),
        sa.Column("challenger_latency_p95_ms", sa.Float(), nullable=True),
        sa.Column("champion_error_rate", sa.Float(), nullable=True),
        sa.Column("challenger_error_rate", sa.Float(), nullable=True),
        sa.Column("champion_request_count", sa.Integer(), nullable=True),
        sa.Column("challenger_request_count", sa.Integer(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False, server_default="system"),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_gate_results_pipeline_run_id", "gate_results", ["pipeline_run_id"])
    op.create_index("ix_canary_snapshots_pipeline_run_id", "canary_snapshots", ["pipeline_run_id"])
    op.create_index("ix_audit_logs_pipeline_run_id", "audit_logs", ["pipeline_run_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("canary_snapshots")
    op.drop_table("gate_results")
    op.drop_table("pipeline_runs")
