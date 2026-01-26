# kdn_server/text_db.py
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _normalize_text(s: str) -> str:
    # 稳定、可复现：仅统一换行 + 去首尾空白，不做大小写/空格折叠以避免误合并
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.strip()


def compute_kid(content: str) -> str:
    norm = _normalize_text(content)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KBItem:
    id: str
    rel_path: str
    content: str
    length: int
    embedding: Optional[List[float]] = None
    embed_dim: Optional[int] = None
    kv_ready: int = 0
    kv_rel_dir: Optional[str] = None
    kv_dumped_keys: Optional[int] = None
    kv_updated_at: Optional[int] = None


class TextDatabase:
    def __init__(self, base_dir: str, embedder=None):
        self._embedder = embedder
        self.base_dir = Path(base_dir).resolve()
        self.blocks_dir = self.base_dir / "blocks"
        self.db_path = self.base_dir / "index.sqlite3"
        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._ensure_kv_columns()
        self._ensure_embedding_columns()

    def _connect(self) -> sqlite3.Connection:
        # 每次操作独立连接：适配多并发 & 多线程（uvicorn 默认 async + 线程池）
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL：提升并发读写体验（写仍然串行，但读不会被写长时间阻塞）
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_blocks (
                    kid TEXT PRIMARY KEY,
                    rel_path TEXT NOT NULL,
                    length INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    meta_json TEXT,
                    embedding BLOB,
                    embed_dim INTEGER
                );
                """
            )

    def _ensure_kv_columns(self) -> None:
        with self._connect() as conn:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(knowledge_blocks);").fetchall()]
            if "kv_ready" not in cols:
                conn.execute("ALTER TABLE knowledge_blocks ADD COLUMN kv_ready INTEGER DEFAULT 0;")
            if "kv_rel_dir" not in cols:
                conn.execute("ALTER TABLE knowledge_blocks ADD COLUMN kv_rel_dir TEXT;")
            if "kv_dumped_keys" not in cols:
                conn.execute("ALTER TABLE knowledge_blocks ADD COLUMN kv_dumped_keys INTEGER;")
            if "kv_updated_at" not in cols:
                conn.execute("ALTER TABLE knowledge_blocks ADD COLUMN kv_updated_at INTEGER;")

    def _ensure_embedding_columns(self) -> None:
        with self._connect() as conn:
            cols = [r["name"] for r in conn.execute(
                "PRAGMA table_info(knowledge_blocks);"
            ).fetchall()]

            if "embedding" not in cols:
                conn.execute("ALTER TABLE knowledge_blocks ADD COLUMN embedding BLOB;")
            if "embed_dim" not in cols:
                conn.execute("ALTER TABLE knowledge_blocks ADD COLUMN embed_dim INTEGER;")

    def register_text(self, content: str, meta: Optional[Dict[str, Any]] = None) -> Tuple[str, str, int]:
        """
        返回: (kid, status, length)
          status: "created" | "exists"
        """
        if not isinstance(content, str):
            raise TypeError("content must be str")

        norm = _normalize_text(content)
        if not norm:
            raise ValueError("content is empty after normalization")

        kid = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        rel_path = f"blocks/{kid}.txt"
        final_path = self.base_dir / rel_path
        length = len(norm)
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        embedding_blob = None
        embed_dim = None
        if self._embedder is not None:
            vec = self._embedder.encode_vector(norm)[0]
            vec = np.asarray(vec, dtype=np.float32)
            embedding_blob = vec.tobytes()
            embed_dim = int(vec.shape[0])

        # 先尝试查索引，命中则直接返回（幂等）
        with self._connect() as conn:
            row = conn.execute("SELECT kid FROM knowledge_blocks WHERE kid = ?", (kid,)).fetchone()
            if row:
                return kid, "exists", length

        # 原子写文件：tmp -> replace
        tmp_dir = self.base_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"{kid}.{os.getpid()}.tmp"
        tmp_path.write_text(norm, encoding="utf-8")
        os.replace(tmp_path, final_path)

        # 写索引：用事务，确保索引与文件一致（若并发注册同一 kid，INSERT OR IGNORE 保幂等）
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_blocks
                (kid, rel_path, length, created_at, meta_json, embedding, embed_dim)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (kid, rel_path, int(length), now, meta_json, embedding_blob, embed_dim),
            )
            conn.execute("COMMIT;")

        return kid, "created", length

    def mark_kv_ready(self, kid: str, kv_rel_dir: str, dumped_keys: int, updated_at: Optional[int] = None) -> None:
        kid = (kid or "").strip().lower()
        if not kid:
            raise ValueError("empty kid")

        ts = int(time.time()) if updated_at is None else int(updated_at)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            # kid 必须已经存在（先注册文本），否则你要决定是否允许“只KV无文本”
            row = conn.execute("SELECT kid FROM knowledge_blocks WHERE kid=?", (kid,)).fetchone()
            if not row:
                conn.execute("ROLLBACK;")
                raise KeyError(f"kid not found in text index: {kid}")

            conn.execute(
                """
                UPDATE knowledge_blocks
                SET kv_ready=1, kv_rel_dir=?, kv_dumped_keys=?, kv_updated_at=?
                WHERE kid=?
                """,
                (kv_rel_dir, int(dumped_keys), ts, kid),
            )
            conn.execute("COMMIT;")

    def get_many(self, kids: Iterable[str]) -> Tuple[List[KBItem], List[str]]:
        items: List[KBItem] = []
        miss: List[str] = []

        kids_list = list(kids)
        if not kids_list:
            return items, miss

        # 批量查索引：新增 embedding / embed_dim
        q_marks = ",".join(["?"] * len(kids_list))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT kid, rel_path, length, embedding, embed_dim, kv_ready, kv_rel_dir, kv_dumped_keys, kv_updated_at
                FROM knowledge_blocks
                WHERE kid IN ({q_marks})
                """,
                tuple(kids_list),
            ).fetchall()

        # kid -> (rel_path, length, embedding_list_or_None, embed_dim_or_None)
        by_kid: Dict[str, Tuple[str, int, Optional[List[float]], Optional[int], int, Optional[str], Optional[int], Optional[int]]] = {}

        for r in rows:
            rel_path = r["rel_path"]
            length = int(r["length"])

            emb_list: Optional[List[float]] = None
            emb_dim: Optional[int] = None

            # embedding 反序列化：BLOB(float32 bytes) -> List[float]
            blob = r["embedding"]
            if blob is not None:
                emb_dim = int(r["embed_dim"]) if r["embed_dim"] is not None else None
                # 注意：这里假设你注册时写入的是 float32
                arr = np.frombuffer(blob, dtype=np.float32)
                emb_list = arr.tolist()
                # 可选一致性校验：embed_dim 存在则检查维度匹配
                if emb_dim is not None and emb_dim != len(emb_list):
                    # 维度不一致时，你可以选择：报错 / 忽略 embedding / 标记 miss
                    # 我这里选择忽略 embedding，避免因为单条脏数据拖垮整个查询
                    emb_list = None

            kv_ready = int(r["kv_ready"]) if r["kv_ready"] is not None else 0
            kv_rel_dir = r["kv_rel_dir"]
            kv_dumped_keys = int(r["kv_dumped_keys"]) if r["kv_dumped_keys"] is not None else None
            kv_updated_at = int(r["kv_updated_at"]) if r["kv_updated_at"] is not None else None

            by_kid[r["kid"]] = (rel_path, length, emb_list, emb_dim, kv_ready, kv_rel_dir, kv_dumped_keys, kv_updated_at)

        # 按输入顺序返回，不去重
        for kid in kids_list:
            rec = by_kid.get(kid)
            if not rec:
                miss.append(kid)
                continue

            rel_path, length, emb_list, emb_dim, kv_ready, kv_rel_dir, kv_dumped_keys, kv_updated_at = rec
            p = (self.base_dir / rel_path).resolve()
            if not p.exists():
                miss.append(kid)
                continue

            content = p.read_text(encoding="utf-8")
            items.append(
                KBItem(
                    id=kid,
                    rel_path=rel_path,
                    content=content,
                    length=length,
                    embedding=emb_list,
                    embed_dim=emb_dim,
                    kv_ready=kv_ready,
                    kv_rel_dir=kv_rel_dir,
                    kv_dumped_keys=kv_dumped_keys,
                    kv_updated_at=kv_updated_at,
                )
            )

        return items, miss

    def snapshot(self, limit: int = 1000000, offset: int = 0, include_embedding: bool = True) -> List[dict]:
        """
        返回知识索引快照（不读正文 txt，专用于 scheduler 初始化建库）。
        - include_embedding=True 时，会把 embedding(BLOB) 反序列化成 list[float]
        """
        limit = max(1, int(limit))
        offset = max(0, int(offset))

        cols = [
            "kid", "rel_path", "length",
            "embed_dim", "kv_ready", "kv_rel_dir",
            "kv_dumped_keys", "kv_updated_at",
        ]
        if include_embedding:
            cols.insert(3, "embedding")

        sql = f"""
        SELECT {",".join(cols)}
        FROM knowledge_blocks
        ORDER BY created_at ASC
        LIMIT ? OFFSET ?
        """

        with self._connect() as conn:
            rows = conn.execute(sql, (limit, offset)).fetchall()

        out: List[dict] = []
        for r in rows:
            it = dict(r)

            # embedding: BLOB -> list[float]（float32）
            if include_embedding:
                blob = it.get("embedding")
                if blob is not None:
                    arr = np.frombuffer(blob, dtype=np.float32)
                    it["embedding"] = arr.tolist()
                else:
                    it["embedding"] = None

            # 规整类型
            it["length"] = int(it.get("length") or 0)
            it["embed_dim"] = int(it.get("embed_dim") or 0) if it.get("embed_dim") is not None else None
            it["kv_ready"] = int(it.get("kv_ready") or 0)
            it["kv_dumped_keys"] = int(it.get("kv_dumped_keys") or 0) if it.get("kv_dumped_keys") is not None else None
            it["kv_updated_at"] = int(it.get("kv_updated_at") or 0) if it.get("kv_updated_at") is not None else None

            out.append(it)

        return out


    def delete_one(self, kid: str) -> Tuple[bool, str]:
        """
        删除一个知识块（索引 + 文件）。
        返回 (deleted, reason)
          deleted=True: 本次确实删除了索引记录（以及尽力删除文件）
          deleted=False: 不存在 or 参数非法
        """
        kid = (kid or "").strip().lower()
        if not kid:
            return False, "empty kid"

        # 先查出路径（若索引不存在，直接返回 not_found）
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rel_path FROM knowledge_blocks WHERE kid = ?",
                (kid,),
            ).fetchone()
            if not row:
                return False, "not_found"

            rel_path = row["rel_path"]
            file_path = (self.base_dir / rel_path).resolve()

            # 先删索引（事务内），再删文件（避免删错文件时索引无法回滚的问题）
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("DELETE FROM knowledge_blocks WHERE kid = ?", (kid,))
            conn.execute("COMMIT;")

        # 文件删除尽力而为：不存在也算成功（因为索引已删）
        try:
            if file_path.exists():
                os.remove(file_path)
        except Exception as e:
            # 这里不回滚索引；把异常作为 reason 返回，便于你排查权限/占用
            return True, f"index_deleted_file_delete_failed: {e}"

        return True, "deleted"

    def delete_many(self, kids: Iterable[str]) -> dict:
        """
        批量删除，返回统计信息。
        """
        deleted: List[str] = []
        not_found: List[str] = []
        errors: List[dict] = []

        for kid in kids:
            ok, reason = self.delete_one(kid)
            if ok:
                if reason == "deleted":
                    deleted.append(str(kid))
                else:
                    # 例如 index_deleted_file_delete_failed
                    deleted.append(str(kid))
                    errors.append({"kid": str(kid), "error": reason})
            else:
                not_found.append(str(kid))

        return {"deleted": deleted, "not_found": not_found, "errors": errors}
