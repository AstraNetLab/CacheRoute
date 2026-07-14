"""Collects local proxy metrics that can be attached to Scheduler heartbeat payloads."""
class ProxyMetrics:
    def inc_inflight(self): ...
    def dec_inflight(self): ...
    def snapshot(self) -> dict:
        return {
            "inflight": ...,
            "qps_1m": ...,
            # Maintains the existing proxy/scheduler experiment flow.
        }

