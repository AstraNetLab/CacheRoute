"""
现在 heartbeat loop 是：
    await client.heartbeat(proxy_id=PROXY_ID)
后续池级资源统计到这来后，只需扩展成：
    snap = metrics.snapshot()
    await client.heartbeat(
        proxy_id=PROXY_ID,
        inflight=snap["inflight"],
        qps_1m=snap["qps_1m"],
        gpu_util=snap.get("gpu_util"),
)
"""
class ProxyMetrics:
    def inc_inflight(self): ...
    def dec_inflight(self): ...
    def snapshot(self) -> dict:
        return {
            "inflight": ...,
            "qps_1m": ...,
            # gpu_util 以后加
        }

