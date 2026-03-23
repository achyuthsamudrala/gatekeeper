"""AuditLog ORM model."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gatekeeper.orm.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("pipeline_runs.id"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False, default="system")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pipeline_run = relationship("PipelineRun", back_populates="audit_logs")
