"""Defines task state passed through proxy queue workers."""
# proxy/queue/task.py
from __future__ import annotations

"""Defines the proxy task object passed between handlers and queue workers."""

import time
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class ProxyTask:
    """Defines the proxy task object passed between handlers and queue workers."""
    request_id: Optional[int]
    req_obj: Any                            # Maintains the existing proxy/scheduler experiment flow.
    instance_body: Dict[str, Any]           # Maintains the existing proxy/scheduler experiment flow.

    instance_id: str                        # Maintains the existing proxy/scheduler experiment flow.
    instance_host: str
    instance_port: int

    url_path: str                           # Maintains the existing proxy/scheduler experiment flow.

    kdn_addr: str | None = None

    # Maintains the existing proxy/scheduler experiment flow.
    response_queue: "asyncio.Queue[Optional[bytes]]" = field(
        default_factory=lambda: asyncio.Queue(maxsize=128)
    )

    # Timing data used by experiment analysis.
    created_at: float = field(default_factory=lambda: time.time())

    # Maintains the existing proxy/scheduler experiment flow.
    error: Optional[str] = None

    kv_ready_kids: List[str] = field(default_factory=list)
    text_only_kids: List[str] = field(default_factory=list)
    miss_kids: List[str] = field(default_factory=list)
    kv_ready_meta: list = field(default_factory=list)

    kv_ack: Dict[str, Any] = field(default_factory=dict)
    trace: Dict[str, int] = field(default_factory=dict)

    # reservation state for ready/prefill timeline
    # prediction stage: "prefill" (default) or "decode" (reserved for future modeling)
    predict_stage: str = "prefill"
    pred_slot_idx: int = -1
    pred_slot_ready_ts_ms: int = 0
    pred_forward_start_ts_ms: int = 0
    pred_prefill_start_ts_ms: int = 0
    pred_first_token_ts_ms: int = 0
    pred_decode_ms: int = 0
    pred_forward_end_ts_ms: int = 0
    pred_worker_free_ts_ms: int = 0
    pred_service_ms: int = 0
    has_started_forward: bool = False
    has_seen_first_token: bool = False
    reservation_seq: int = -1
    recompute_generation: int = 0

    def mark(self, key: str, ts_ms: int) -> None:
        self.trace[key] = int(ts_ms)
