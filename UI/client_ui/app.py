from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Optional
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 复用你现有 client.py 的底层能力
from client import client as client_core

BASE_DIR = Path(__file__).resolve().parent          # .../UI/client_ui
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

def create_client_ui_app(
    default_scheduler_url: str = "http://127.0.0.1:7001/v1/chat/completions",
    page_title: str = "CacheRoute Client UI",
) -> FastAPI:
    """
    Client UI：独立 FastAPI App，可单独启动，也可被 Scheduler/Proxy mount。
    """
    app = FastAPI(title=page_title)

    router = APIRouter()

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # 静态资源
    if not STATIC_DIR.exists():
        raise RuntimeError(f"Static directory not found: {STATIC_DIR}")
    if not TEMPLATES_DIR.exists():
        raise RuntimeError(f"Templates directory not found: {TEMPLATES_DIR}")

    app.mount("/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui_static")

    @router.get("/ui/client", response_class=HTMLResponse)
    async def ui_page(request: Request):
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "default_scheduler_url": default_scheduler_url,
                "page_title": page_title,
            },
        )

    @router.post("/ui/api/parse_curl")
    async def parse_curl(payload: Dict[str, Any]):
        """
        输入：{ "line": "<curl-like line>" }
        输出：{ url, headers, body } 或 error
        """
        line = (payload.get("line") or "").strip()
        if not line:
            return JSONResponse(status_code=400, content={"error": "line is empty"})
        try:
            parsed = client_core.parse_cli_line(line)
            return {"parsed": asdict(parsed)}
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    @router.post("/ui/api/validate")
    async def validate_req(payload: Dict[str, Any]):
        """
        输入：{ "url": "...", "headers": {...}, "body": {...} }
        输出：{ ok: bool, errors: [] }
        """
        try:
            parsed = client_core.ParsedRequest(
                url=str(payload.get("url") or ""),
                headers=dict(payload.get("headers") or {}),
                body=dict(payload.get("body") or {}),
            )
            errors = client_core.validate_openai_like_request(parsed)
            return {"ok": len(errors) == 0, "errors": errors}
        except Exception as e:
            return JSONResponse(status_code=400, content={"ok": False, "errors": [str(e)]})

    @router.post("/ui/api/send")
    async def send_req(payload: Dict[str, Any]):
        """
        输入：{ "url": "...", "headers": {...}, "body": {...}, "timeout": 60 }
        输出：{ status_code, headers, body_text, body_json? }
        """
        timeout = float(payload.get("timeout") or 60.0)
        url = str(payload.get("url") or "")
        headers = dict(payload.get("headers") or {})
        body = dict(payload.get("body") or {})

        # Content-Type 补齐（和 client.py 一致的行为）
        if not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = "application/json"

        parsed = client_core.ParsedRequest(url=url, headers=headers, body=body)

        # 发送前再校验一遍，避免 UI 绕开规则
        errors = client_core.validate_openai_like_request(parsed)
        if errors:
            return JSONResponse(status_code=400, content={"error": "validation_failed", "errors": errors})

        try:
            resp = client_core.send_request(parsed, timeout=timeout)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

        out: Dict[str, Any] = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body_text": resp.text,
        }
        # 尝试 JSON 解析
        try:
            out["body_json"] = resp.json()
        except Exception:
            out["body_json"] = None

        return out

    app.include_router(router)
    return app


def run_client_ui(
    host: str,
    port: int,
    default_scheduler_url: str,
) -> None:
    """
    独立启动入口：python -m UI.client_ui.app
    """
    import uvicorn

    app = create_client_ui_app(default_scheduler_url=default_scheduler_url)
    uvicorn.run(app, host=host, port=port, reload=False)
