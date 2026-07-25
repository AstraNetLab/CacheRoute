# instance/pclient/proxy_client.py
"""Async client for registering Instance nodes with the Proxy control plane."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from core.instance_capability import InstanceCapability


@dataclass
class RegisterResult:
    instance_id: str
    heartbeat_interval_s: int
    ttl_s: int
    capability_fingerprint: Optional[str] = None


class ProxyControlClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def close(self) -> None:
        await self._client.aclose()

    async def register(
        self,
        instance_id: str,
        host: str,
        port: int,
        endpoints: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        capabilities: Optional[InstanceCapability] = None,
        capability_fingerprint: Optional[str] = None,
    ) -> RegisterResult:
        payload = {
            "instance_id": instance_id,
            "host": host,
            "port": port,
            "endpoints": endpoints or ["chat/completions", "completions"],
            "meta": meta or {},
        }
        if capabilities is not None:
            payload["capabilities"] = capabilities.model_dump(mode="json")
        if capability_fingerprint is not None:
            payload["capability_fingerprint"] = capability_fingerprint
        r = await self._client.post(f"{self.base_url}/v1/instance/register", json=payload)
        r.raise_for_status()
        j = r.json()
        return RegisterResult(
            instance_id=j["instance_id"],
            heartbeat_interval_s=int(j.get("heartbeat_interval_s", 10)),
            ttl_s=int(j.get("ttl_s", 30)),
            capability_fingerprint=j.get("capability_fingerprint"),
        )

    async def heartbeat(
        self,
        instance_id: str,
        capability_fingerprint: Optional[str] = None,
        capabilities: Optional[InstanceCapability] = None,
    ) -> None:
        payload = {"instance_id": instance_id}
        if capability_fingerprint is not None:
            payload["capability_fingerprint"] = capability_fingerprint
        if capabilities is not None:
            payload["capabilities"] = capabilities.model_dump(mode="json")
        r = await self._client.post(f"{self.base_url}/v1/instance/heartbeat", json=payload)
        r.raise_for_status()

    async def unregister(self, instance_id: str) -> None:
        r = await self._client.post(f"{self.base_url}/v1/instance/unregister", json={"instance_id": instance_id})
        r.raise_for_status()

    async def report_kdn_topology(self, instance_id: str, links: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        payload = {"instance_id": instance_id, "links": links}
        r = await self._client.post(f"{self.base_url}/v1/topology/report", json=payload)
        r.raise_for_status()
        return r.json()
