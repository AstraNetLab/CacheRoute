# proxy/queue/knowledge.py
"""
proxy维护的知识注入方法，由准备队列调用
"""
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
    """
    向 KDN 请求知识（非流式）。
    返回：(items, miss)
    """
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
    """
    将 retrieved_context 注入 instance_body（OpenAI 风格），返回新 dict。
    - text: 保持现有 instruction 包装
    - kvcache: 使用纯文本 system 前缀，尽量贴近 KV 预构建格式
    """
    if not retrieved_context:
        return instance_body

    new_body = dict(instance_body)

    # chat/completions
    if endpoint_type == "chat/completions":
        msgs = list(new_body.get("messages") or [])

        if injection_type == "kvcache":
            # KVCache 模式：system 直接放纯知识文本，不加额外包装
            msgs.insert(0, {"role": "system", "content": retrieved_context})
        else:
            # text 模式：保持现有模板
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
        # completions 下没有 role 结构，只能尽量贴近：
        # 把纯知识文本直接放在 prompt 最前面
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
    """
    按 KDN 返回结果对知识块分类：
      - kv_ready_items: 已有 KV，可用于后续 KV 注入
      - text_only_items: 只有文本，没有现成 KV
      - miss_ids: KDN 未命中的 kid
    并保持输入顺序稳定。
    """
    miss_set = {str(x) for x in (miss or [])}

    # KDN 返回 items 不保证我们想要的顺序，这里先建索引
    item_map: Dict[str, Dict[str, Any]] = {}
    for it in items or []:
        kid = str(it.get("knowledge_id") or it.get("kid") or it.get("id") or "")
        rel_path = it.get("rel_path")
        if not kid and rel_path:
            # 兜底：从 rel_path 推断 kid（如 knowledge/a.txt -> a）
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
            # KDN 没明确放进 miss，但也没返回 item，当 miss 处理
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
    """
    构造注入文本：
    先放 kv_ready 的文本，再放 text_only 的文本。
    """
    ordered = list(kv_ready_items) + list(text_only_items)
    return format_retrieved_context(ordered)