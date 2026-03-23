"""PipelineRun ORM model."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gatekeeper.orm.base import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    candidate_version: Mapped[str] = mapped_column(String, nullable=False)
    champion_version: Mapped[str | None] = mapped_column(String, nullable=True)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    offline_status: Mapped[str] = mapped_column(String, nullable=False, default="skipped")
    online_status: Mapped[str] = mapped_column(String, nullable=False, default="skipped")
    triggered_by: Mapped[str] = mapped_column(String, nullable=False, default="api")
    model_type: Mapped[str] = mapped_column(String, nullable=False, default="llm")
    registry_type: Mapped[str] = mapped_column(String, nullable=False, default="none")
    serving_type: Mapped[str] = mapped_column(String, nullable=False, default="none")
    gatekeeper_yaml: Mapped[str] = mapped_column(String, nullable=False)
    github_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    gate_results = relationship("GateResult", back_populates="pipeline_run", lazy="selectin")
    canary_snapshots = relationship(
        "CanarySnapshot", back_populates="pipeline_run", lazy="selectin"
    )
    audit_logs = relationship("AuditLog", back_populates="pipeline_run", lazy="selectin")
