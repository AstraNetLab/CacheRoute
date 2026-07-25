from fastapi.testclient import TestClient

from core.instance_capability import capability_fingerprint
from proxy.resource.instance_pool import InstancePool
from proxy.resource.p_control_plane import _control_plane, set_pool


def payload():
    return {
        "schema_version": "1", "model": {"identifier": "m"},
        "tokenizer": {"identifier": "m"}, "kv_cache": {"layout": "paged", "dtype": "fp16"},
        "parallelism": {"tensor_parallel_size": 1, "pipeline_parallel_size": 1, "data_parallel_size": 1},
    }


def client():
    set_pool(InstancePool(ttl_s=30))
    return TestClient(_control_plane)


def test_legacy_registration_and_heartbeat_remain_accepted():
    with client() as api:
        response = api.post("/v1/instance/register", json={"instance_id": "legacy", "host": "h", "port": 1,
                                                               "meta": {"old": True}})
        assert response.status_code == 200
        assert response.json()["capability_fingerprint"] is None
        assert api.post("/v1/instance/heartbeat", json={"instance_id": "legacy"}).json() == {"ok": True}


def test_registration_recomputes_fingerprint_and_list_exposes_contract():
    capabilities = payload()
    with client() as api:
        response = api.post("/v1/instance/register", json={
            "instance_id": "new", "host": "h", "port": 2, "capabilities": capabilities,
            "capability_fingerprint": "sha256:incorrect",
        })
        expected = capability_fingerprint(capabilities)
        assert response.status_code == 200
        assert response.json()["capability_fingerprint"] == expected
        item = api.get("/v1/instance/list").json()[0]
        assert item["capabilities"]["model"]["identifier"] == "m"
        assert item["capability_fingerprint"] == expected


def test_heartbeat_omission_preserves_and_changed_object_updates_capability():
    capabilities = payload()
    with client() as api:
        api.post("/v1/instance/register", json={"instance_id": "i", "host": "h", "port": 2,
                                                "capabilities": capabilities})
        old = api.get("/v1/instance/list").json()[0]["capability_fingerprint"]
        api.post("/v1/instance/heartbeat", json={"instance_id": "i"})
        assert api.get("/v1/instance/list").json()[0]["capability_fingerprint"] == old
        capabilities["kv_cache"]["dtype"] = "bf16"
        assert api.post("/v1/instance/heartbeat", json={"instance_id": "i", "capabilities": capabilities}).json()["ok"]
        assert api.get("/v1/instance/list").json()[0]["capability_fingerprint"] == capability_fingerprint(capabilities)


def test_malformed_capability_returns_structured_validation_error():
    with client() as api:
        response = api.post("/v1/instance/register", json={"host": "h", "port": 2,
                                                           "capabilities": {"kv_cache": {"block_size": -1}}})
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"][-1] == "block_size"
