"""Process-local append-only trace collection with monotonic durations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import uuid4

from .clock import SystemTraceClock, TraceClock
from .enums import TraceStageName, TraceStageOutcome, TraceStageState
from .models import RequestTrace, TraceContext, TraceMeasurement, TraceProvenance, TraceStage


@dataclass
class _OpenStage:
    stage_id: str
    sequence: int
    name: TraceStageName
    provenance: TraceProvenance
    started_at: datetime
    started_monotonic_ns: int
    parent_stage_id: str | None
    operation_id: str | None
    artifact_id: str | None
    measurements: list[TraceMeasurement] = field(default_factory=list)


class TraceCollector:
    """Collect local stages; exported contracts never contain monotonic readings."""

    def __init__(
        self,
        context: TraceContext,
        *,
        clock: TraceClock | None = None,
        enabled: bool = True,
        id_factory: Callable[[], str] | None = None,
    ):
        self.context = context
        self.clock = clock or SystemTraceClock()
        self.enabled = bool(enabled)
        self._id_factory = id_factory or (lambda: f"stage_{uuid4().hex}")
        self._next_sequence = 0
        self._open: dict[str, _OpenStage] = {}
        self._timeline: list[str] = []
        self._completed: dict[str, TraceStage] = {}

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        correlation_id: str,
        legacy_request_id: int | None = None,
        sampled: bool = True,
        clock: TraceClock | None = None,
        enabled: bool = True,
        id_factory: Callable[[], str] | None = None,
    ) -> "TraceCollector":
        """Create a context at the injected clock and return its collector."""
        selected_clock = clock or SystemTraceClock()
        context = TraceContext(
            trace_id=f"trace_{uuid4().hex}",
            request_id=request_id,
            correlation_id=correlation_id,
            legacy_request_id=legacy_request_id,
            sampled=sampled,
            created_at=selected_clock.utc_now(),
        )
        return cls(context, clock=selected_clock, enabled=enabled, id_factory=id_factory)

    @property
    def collecting(self) -> bool:
        return self.enabled and self.context.sampled

    def start_stage(
        self,
        name: TraceStageName,
        provenance: TraceProvenance,
        *,
        parent_stage_id: str | None = None,
        operation_id: str | None = None,
        artifact_id: str | None = None,
    ) -> str | None:
        if not self.collecting:
            return None
        stage_id = self._id_factory()
        if stage_id in self._open or stage_id in self._completed:
            raise ValueError("stage_id must be unique within a collector")
        stage = _OpenStage(
            stage_id=stage_id,
            sequence=self._next_sequence,
            name=TraceStageName(name),
            provenance=provenance,
            started_at=self.clock.utc_now(),
            started_monotonic_ns=self.clock.monotonic_ns(),
            parent_stage_id=parent_stage_id,
            operation_id=operation_id,
            artifact_id=artifact_id,
        )
        self._next_sequence += 1
        self._open[stage_id] = stage
        self._timeline.append(stage_id)
        return stage_id

    def append_measurement(self, stage_id: str | None, measurement: TraceMeasurement) -> bool:
        if not self.collecting or stage_id is None:
            return False
        stage = self._open.get(stage_id)
        if stage is None:
            if stage_id in self._completed:
                raise ValueError("cannot append to a completed stage")
            raise KeyError("unknown stage_id")
        stage.measurements.append(measurement)
        return True

    def finish_stage(
        self,
        stage_id: str | None,
        outcome: TraceStageOutcome,
        *,
        outcome_code: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool = False,
        fallback_eligible: bool = False,
        fallback_stage_id: str | None = None,
        partial_reason: str | None = None,
    ) -> TraceStage | None:
        if not self.collecting or stage_id is None:
            return None
        if stage_id in self._completed:
            raise ValueError("stage is already completed")
        stage = self._open.get(stage_id)
        if stage is None:
            raise KeyError("unknown stage_id")
        ended_at = self.clock.utc_now()
        elapsed = self.clock.monotonic_ns() - stage.started_monotonic_ns
        if elapsed < 0:
            raise ValueError("monotonic clock moved backwards")
        completed = TraceStage(
            stage_id=stage.stage_id,
            sequence=stage.sequence,
            name=stage.name,
            state=TraceStageState.COMPLETED,
            outcome=outcome,
            provenance=stage.provenance,
            measurements=tuple(stage.measurements),
            started_at=stage.started_at,
            ended_at=ended_at,
            duration_ns=elapsed,
            parent_stage_id=stage.parent_stage_id,
            operation_id=stage.operation_id,
            artifact_id=stage.artifact_id,
            outcome_code=outcome_code,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            fallback_eligible=fallback_eligible,
            fallback_stage_id=fallback_stage_id,
            partial_reason=partial_reason,
        )
        del self._open[stage_id]
        self._completed[stage_id] = completed
        return completed

    def export(self, *, complete: bool = False, error_code: str | None = None) -> RequestTrace:
        stages: list[TraceStage] = []
        for stage_id in self._timeline:
            completed = self._completed.get(stage_id)
            if completed is not None:
                stages.append(completed)
                continue
            opened = self._open[stage_id]
            stages.append(TraceStage(
                stage_id=opened.stage_id,
                sequence=opened.sequence,
                name=opened.name,
                state=TraceStageState.RUNNING,
                provenance=opened.provenance,
                measurements=tuple(opened.measurements),
                started_at=opened.started_at,
                parent_stage_id=opened.parent_stage_id,
                operation_id=opened.operation_id,
                artifact_id=opened.artifact_id,
            ))
        components = tuple(dict.fromkeys(stage.provenance.source_component for stage in stages))
        return RequestTrace(
            context=self.context,
            stages=tuple(stages),
            exported_at=self.clock.utc_now(),
            complete=complete,
            source_components=components,
            error_code=error_code,
        )

    def safely(self, operation: Callable[[], object], default=None):
        """Run optional instrumentation without allowing failures into caller behavior."""
        try:
            return operation()
        except Exception:
            return default


__all__ = ["TraceCollector"]
