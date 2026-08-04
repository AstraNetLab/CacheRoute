"""Append-only process-local trace collection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from cacheroute.contracts.v1.errors import ContractErrorDetail, OutcomeCode
from .clock import SystemTraceClock, TraceClock
from .v1 import (
    RequestTrace, TraceContext, TraceMeasurement, TraceProvenance, TraceStage,
    TraceStageName, TraceStageState,
)


@dataclass
class _OpenStage:
    stage_id: str
    sequence: int
    name: TraceStageName
    provenance: TraceProvenance
    started_at: object
    started_ns: int
    parent_stage_id: str | None = None
    fallback_stage_id: str | None = None
    logical_operation_id: str | None = None
    artifact_id: str | None = None
    measurements: list[TraceMeasurement] = field(default_factory=list)


class TraceCollector:
    """Collect one request trace without I/O or global state."""

    def __init__(self, context: TraceContext, *, clock: TraceClock | None = None,
                 id_factory: Callable[[], str] | None = None, enabled: bool = True):
        self.context = context
        self._clock = clock or SystemTraceClock()
        self._id_factory = id_factory or (lambda: f"stage_{uuid4().hex}")
        self._collecting = enabled and context.sampled
        self._stages: list[TraceStage] = []
        self._open: dict[str, _OpenStage] = {}
        self._all_ids: set[str] = set()

    @property
    def collecting(self) -> bool:
        return self._collecting

    def start_stage(self, name: TraceStageName, provenance: TraceProvenance, *, stage_id: str | None = None,
                    parent_stage_id: str | None = None, fallback_stage_id: str | None = None,
                    logical_operation_id: str | None = None, artifact_id: str | None = None) -> str | None:
        if not self._collecting: return None
        identifier = stage_id or self._id_factory()
        if identifier in self._all_ids: raise ValueError("duplicate stage ID")
        known = self._all_ids
        if parent_stage_id is not None and parent_stage_id not in known: raise ValueError("unknown parent stage")
        if fallback_stage_id is not None and fallback_stage_id not in known: raise ValueError("unknown fallback stage")
        started_at = self._clock.utc_now()
        started_ns = self._clock.monotonic_ns()
        # Validate caller-controlled identities and references before reserving
        # the ID or sequence number.
        TraceStage(
            stage_id=identifier, sequence=len(self._all_ids), name=name,
            state=TraceStageState.RUNNING, provenance=provenance,
            started_at=started_at, parent_stage_id=parent_stage_id,
            fallback_stage_id=fallback_stage_id,
            logical_operation_id=logical_operation_id, artifact_id=artifact_id,
        )
        self._all_ids.add(identifier)
        self._open[identifier] = _OpenStage(
            identifier, len(self._all_ids) - 1, TraceStageName(name), provenance,
            started_at, started_ns, parent_stage_id,
            fallback_stage_id, logical_operation_id, artifact_id,
        )
        return identifier

    def append_measurement(self, stage_id: str | None, measurement: TraceMeasurement) -> None:
        if not self._collecting or stage_id is None: return
        if stage_id not in self._open: raise ValueError("unknown or finished stage ID")
        self._open[stage_id].measurements.append(measurement)

    def finish_stage(self, stage_id: str | None, *, outcome: OutcomeCode,
                     error: ContractErrorDetail | None = None) -> None:
        if not self._collecting or stage_id is None: return
        if stage_id not in self._open: raise ValueError("unknown or already finished stage ID")
        item = self._open[stage_id]
        finished_ns = self._clock.monotonic_ns()
        elapsed = finished_ns - item.started_ns
        if elapsed < 0: raise ValueError("monotonic clock moved backwards")
        candidate = TraceStage(
            stage_id=item.stage_id, sequence=item.sequence, name=item.name,
            state=TraceStageState.COMPLETED, provenance=item.provenance,
            started_at=item.started_at, finished_at=self._clock.utc_now(), elapsed_ns=elapsed,
            outcome=outcome, error=error, parent_stage_id=item.parent_stage_id,
            fallback_stage_id=item.fallback_stage_id, logical_operation_id=item.logical_operation_id,
            artifact_id=item.artifact_id, measurements=tuple(item.measurements),
        )
        del self._open[stage_id]
        self._stages.append(candidate)

    def skip_stage(self, name: TraceStageName, provenance: TraceProvenance, *, reason: str,
                   stage_id: str | None = None, parent_stage_id: str | None = None) -> str | None:
        if not self._collecting: return None
        identifier = stage_id or self._id_factory()
        if identifier in self._all_ids: raise ValueError("duplicate stage ID")
        if parent_stage_id is not None and parent_stage_id not in self._all_ids: raise ValueError("unknown parent stage")
        candidate = TraceStage(
            stage_id=identifier, sequence=len(self._all_ids), name=name,
            state=TraceStageState.SKIPPED, provenance=provenance,
            skip_reason=reason, parent_stage_id=parent_stage_id,
        )
        self._all_ids.add(identifier)
        self._stages.append(candidate)
        return identifier

    def export(self, *, cache_operation_ids: tuple[str, ...] = (), outcome: OutcomeCode | None = None,
               error: ContractErrorDetail | None = None) -> RequestTrace:
        if self._open: raise ValueError("cannot export while stages are running")
        return RequestTrace(context=self.context, stages=tuple(sorted(self._stages, key=lambda x: x.sequence)),
                            cache_operation_ids=cache_operation_ids, outcome=outcome, error=error)


__all__ = ["TraceCollector"]
