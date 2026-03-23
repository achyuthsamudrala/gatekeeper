"""GateResult ORM model."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gatekeeper.orm.base import Base


class GateResult(Base):
    __tablename__ = "gate_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("pipeline_runs.id"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String, nullable=False)
    gate_name: Mapped[str] = mapped_column(String, nullable=False)
    gate_type: Mapped[str] = mapped_column(String, nullable=False)
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparator: Mapped[str | None] = mapped_column(String, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pipeline_run = relationship("PipelineRun", back_populates="gate_results")
