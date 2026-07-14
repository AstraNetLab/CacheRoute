# CacheRoute Proxy UI

Lightweight browser dashboard for observing the Proxy control plane without changing scheduling, forwarding, KDN, or KVCache behavior.

## Run with demo proxy

```bash
cd test
python3 demo_proxy.py --host 127.0.0.1 --port 8001 --strategy round_robin --injection-strategy iws
```

The demo prints a URL such as:

```text
[demo_proxy] Proxy UI available at: http://127.0.0.1:8202
```

## Run standalone

```bash
PROXY_UI_PROXY_CP_URL=http://127.0.0.1:8002 \
PROXY_UI_SCHEDULER_CP_URL=http://127.0.0.1:7002 \
python3 -m uvicorn UI.proxy_ui.proxy_ui_server:app --host 127.0.0.1 --port 8202
```

## What the first version shows

- Proxy health and debug status.
- Instance pool records from `/v1/instance/list?include_dead=true`.
- Instance resource snapshots from `/debug/instance_resources`.
- KDN topology links from `/v1/topology/kdn_links`.
- Best-effort Scheduler registration state when `PROXY_UI_PROXY_ID` is configured.

The UI polls the Proxy control plane through the UI server, so the browser does not need direct CORS access to Proxy APIs.
