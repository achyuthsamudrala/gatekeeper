"""CanarySnapshot ORM model."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gatekeeper.orm.base import Base


class CanarySnapshot(Base):
    __tablename__ = "canary_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    pipeline_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("pipeline_runs.id"), nullable=False
    )
    timestamp: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    champion_latency_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    champion_latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    challenger_latency_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    challenger_latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    champion_error_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    challenger_error_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    champion_request_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    challenger_request_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    pipeline_run = relationship("PipelineRun", back_populates="canary_snapshots")
