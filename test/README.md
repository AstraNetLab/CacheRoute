# Test and Demo Scripts

`test/` contains local entrypoints, smoke scripts, and historical utility tests for CacheRoute development. Most `demo_*.py` files are intended to be launched manually from the repository root or from the `test` directory.

The default single-machine demo ports are:

| Component | Service plane | Control plane / auxiliary |
|---|---:|---:|
| Scheduler | `7001` | `7002` |
| Proxy | `8001` | `8002` |
| Instance | `9001` | `9002` |
| KDN Server | `9101` | - |
| Resource Agent | `9201` | - |

## Main demo files

| File | Purpose | Typical usage |
|---|---|---|
| `demo_scheduler.py` | Starts Scheduler service plane and control plane. Use it when validating full Client -> Scheduler -> Proxy routing. | `python3 demo_scheduler.py --cacheroute` |
| `demo_proxy.py` | Starts Proxy service plane and Proxy control plane. It registers to Scheduler if available, and accepts Instance registration/resource reports on `8002`. | `python3 demo_proxy.py --strategy round_robin --injection-strategy iws` |
| `demo_instance.py` | Starts an Instance service. By default it registers to Proxy, starts or reuses the Rust Resource Agent, reports resource snapshots after registration, and cleans up demo-owned agent processes on shutdown. | `python3 demo_instance.py --host 127.0.0.1 --port 9001 --proxy-cp-url http://127.0.0.1:8002` |
| `demo_kdn.py` | Starts the KDN Server for text/KVCache metadata query and registration. | `python3 demo_kdn.py` |
| `demo_client.py` | Sends demo requests through CacheRoute. Can be used with or without UI depending on flags. | `python3 demo_client.py --with-ui` |
| `demo_run.py` | Historical helper for running a demo flow. Check the script body before relying on it for new experiments. | `python3 demo_run.py` |
| `demo_embedding.py` | Local embedding / retrieval validation helper. | `python3 demo_embedding.py` |
| `demo_request_handle.py` | Request parsing and request-handle validation helper. | `python3 demo_request_handle.py` |
| `demo_resource_monitor_e2e.py` | Starts demo Proxy and demo Instance, waits for resource reports, terminates Instance, and checks that the demo-owned Rust Resource Agent is cleaned up. | `python3 demo_resource_monitor_e2e.py` |

## Utility and regression scripts

| File | Purpose |
|---|---|
| `request_handle.py` | Helper module for request parsing/handling experiments. |
| `test.py` | Legacy scratch/test entrypoint. Inspect before use. |
| `test_kb_kid.py` | Knowledge-base / knowledge-id validation. |
| `test_injector_reuse.py` | Injector reuse validation. |
| `test_kv_injector_reuse.py` | KVCache injector reuse validation. |
| `Injection_method_comparison.py` | Compares injection methods for local experiments. |
| `Prefill_calculation.py` | Prefill-time calculation helper. |
| `quick_start_docker.sh` | Convenience script for container-oriented startup. |

## Minimal Proxy + Instance resource-monitor demo

Terminal 1:

```bash
cd test
python3 demo_proxy.py \
  --host 127.0.0.1 \
  --port 8001 \
  --strategy round_robin \
  --injection-strategy iws
```

Terminal 2:

```bash
cd test
python3 demo_instance.py \
  --host 127.0.0.1 \
  --port 9001 \
  --proxy-cp-url http://127.0.0.1:8002
```

`demo_instance.py` enables resource monitoring by default. It will:

1. register the Instance to Proxy;
2. start or reuse the Rust Resource Agent;
3. wait for `http://127.0.0.1:9201/healthz`;
4. periodically report snapshots to `http://127.0.0.1:8002/v1/instance/resource_snapshot`;
5. kill only the Resource Agent process group it started when Instance exits.

Inspect resource status:

```bash
curl -sS "http://127.0.0.1:8002/debug/instance_resources" | python3 -m json.tool
curl -sS "http://127.0.0.1:8002/v1/instance/list?include_dead=true" | python3 -m json.tool
```

Disable resource monitoring:

```bash
python3 demo_instance.py --no-resource-monitor
```

Use a non-default Resource Agent port:

```bash
python3 demo_instance.py \
  --resource-agent-listen 127.0.0.1:19201 \
  --resource-agent-url http://127.0.0.1:19201
```

## Resource-monitor e2e smoke script

Run from the repository root:

```bash
python3 test/demo_resource_monitor_e2e.py \
  --agent-listen 127.0.0.1:19201 \
  --agent-url http://127.0.0.1:19201
```

The non-default `19201` port avoids false failures if a separate Resource Agent is already running on `9201`.

The script is intentionally a practical smoke validation rather than a pytest test. It may skip or fail on machines without `cargo`, `uvicorn`, or available ports.

## Full local path

A typical local end-to-end flow uses separate terminals:

```bash
# Terminal 1: KDN
cd test
python3 demo_kdn.py

# Terminal 2: Scheduler
cd test
python3 demo_scheduler.py --cacheroute

# Terminal 3: Proxy
cd test
python3 demo_proxy.py --strategy round_robin --injection-strategy iws

# Terminal 4: Instance
cd test
python3 demo_instance.py --host 127.0.0.1 --port 9001 --proxy-cp-url http://127.0.0.1:8002

# Terminal 5: Client
cd test
python3 demo_client.py --with-ui
```

For focused Proxy/Instance development, Scheduler and KDN are optional unless the specific feature under test requires them.

## Cleanup tips

Check ports:

```bash
ss -ltnp | grep -E "7001|7002|8001|8002|9001|9002|9101|9201" || true
```

Find stale demo processes:

```bash
ps -ef | grep -E "demo_scheduler|demo_proxy|demo_instance|demo_kdn|resource_agent|cargo" | grep -v grep
```

If old external processes are heartbeating to Proxy with unknown IDs, inspect their environment:

```bash
for p in /proc/[0-9]*; do
  pid=${p##*/}
  env=$(tr '\0' '\n' < "$p/environ" 2>/dev/null | grep -E "INSTANCE_ID|PROXY_CP_URL" || true)
  if [ -n "$env" ]; then
    echo "PID=$pid CMD=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)"
    echo "$env"
    echo
  fi
done
```
