# proxy/queue/knowledge.py
"""Provides KDN knowledge fetch, classification, and request-body injection helpers used by the proxy queue."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from core import forward_request

logger = logging.getLogger("proxy.queue.knowledge")


def format_retrieved_context(items: List[Dict[str, Any]]) -> str:
    lines = []
    for it in items:
        content = (it.get("content") or "").strip()
        if content:
            lines.append(content)
    return "\n".join(lines).strip()


async def fetch_knowledge_from_kdn(kdn_base_url: str, knowledge_ids: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Provides KDN knowledge fetch, classification, and request-body injection helpers used by the proxy queue."""
    if not knowledge_ids:
        return [], []

    url = f"{kdn_base_url.rstrip('/')}/knowledge/search/text"
    body = {
        "knowledge_ids": knowledge_ids,
        "need_fields": ["content", "length", "rel_path", "kv_ready", "kv_rel_dir", "kv_dumped_keys", "kv_updated_at"],
    }

    content_bytes = b""
    async for chunk in forward_request(url, data=body, use_chunked=False):
        if chunk:
            content_bytes += chunk

    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = content_bytes.decode("utf-8", errors="ignore")

    try:
        resp = json.loads(text) if text else {}
    except json.JSONDecodeError:
        raise RuntimeError(f"KDN response is not valid JSON: {text[:200]}")

    items = resp.get("items") or []
    miss = resp.get("miss") or []
    if not isinstance(items, list):
        items = []
    if not isinstance(miss, list):
        miss = []

    return items, miss


def inject_rag_into_instance_body(instance_body: Dict[str, Any], endpoint_type: str, retrieved_context: str, injection_type: str = "text") -> Dict[str, Any]:
    """Provides KDN knowledge fetch, classification, and request-body injection helpers used by the proxy queue."""
    if not retrieved_context:
        return instance_body

    new_body = dict(instance_body)

    # chat/completions
    if endpoint_type == "chat/completions":
        msgs = list(new_body.get("messages") or [])

        if injection_type == "kvcache":
            # Knowledge/KDN-related state used by scheduling and injection.
            msgs.insert(0, {"role": "system", "content": retrieved_context})
        else:
            # Maintains the existing proxy/scheduler experiment flow.
            system_prompt = (
                "You are a helpful assistant.\n"
                "Use the following retrieved context to answer the user. "
                "If the context is not relevant, ignore it.\n"
                f"### Retrieved Context\n{retrieved_context}\n"
            )
            msgs.insert(0, {"role": "system", "content": system_prompt})

        new_body["messages"] = msgs
        return new_body

    # completions
    prompt = str(new_body.get("prompt") or "")

    if injection_type == "kvcache":
        # Maintains the existing proxy/scheduler experiment flow.
        # Knowledge/KDN-related state used by scheduling and injection.
        new_body["prompt"] = retrieved_context + "\n" + prompt
    else:
        rag_prefix = (
            "You are a helpful assistant.\n"
            "Use the following retrieved context to answer the user. "
            "If the context is not relevant, ignore it.\n"
            f"### Retrieved Context\n{retrieved_context}\n"
            "### User Prompt\n"
        )
        new_body["prompt"] = rag_prefix + prompt

    return new_body


def classify_kdn_items(
    requested_ids: List[str],
    items: List[Dict[str, Any]],
    miss: List[str],
) -> Dict[str, Any]:
    """Provides KDN knowledge fetch, classification, and request-body injection helpers used by the proxy queue."""
    miss_set = {str(x) for x in (miss or [])}

    # Knowledge/KDN-related state used by scheduling and injection.
    item_map: Dict[str, Dict[str, Any]] = {}
    for it in items or []:
        kid = str(it.get("knowledge_id") or it.get("kid") or it.get("id") or "")
        rel_path = it.get("rel_path")
        if not kid and rel_path:
            # Maintains the existing proxy/scheduler experiment flow.
            try:
                kid = str(rel_path).split("/")[-1].split(".")[0]
            except Exception:
                kid = ""
        if kid:
            item_map[kid] = it

    kv_ready_items: List[Dict[str, Any]] = []
    text_only_items: List[Dict[str, Any]] = []
    miss_ids: List[str] = []

    for kid in [str(x) for x in requested_ids]:
        if kid in miss_set:
            miss_ids.append(kid)
            continue

        it = item_map.get(kid)
        if not it:
            # Knowledge/KDN-related state used by scheduling and injection.
            miss_ids.append(kid)
            continue

        if bool(it.get("kv_ready", False)):
            kv_ready_items.append(it)
        else:
            text_only_items.append(it)

    return {
        "kv_ready_items": kv_ready_items,
        "text_only_items": text_only_items,
        "miss_ids": miss_ids,
    }


def build_ordered_context(
    kv_ready_items: List[Dict[str, Any]],
    text_only_items: List[Dict[str, Any]],
) -> str:
    """Provides KDN knowledge fetch, classification, and request-body injection helpers used by the proxy queue."""
    ordered = list(kv_ready_items) + list(text_only_items)
    return format_retrieved_context(ordered)