import os
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple

from .services import embed_text

logger = logging.getLogger(__name__)


def _project_base_dir() -> str:
    return os.path.dirname(os.path.dirname(__file__))


def _get_index_base_dir() -> str:
    base = os.environ.get("RAG_INDEX_DIR")
    if base:
        return base
    return os.path.join(_project_base_dir(), ".rag_index")


def _sanitize_host(host: str) -> str:
    return "".join(c for c in (host or "unknown").lower() if c.isalnum() or c in ("-", ".", "_")) or "unknown"


def _host_dir(host: str) -> str:
    return os.path.join(_get_index_base_dir(), _sanitize_host(host))


def _index_path(host: str) -> str:
    return os.path.join(_host_dir(host), "index.jsonl")


def _ensure_host_dir(host: str) -> None:
    os.makedirs(_host_dir(host), exist_ok=True)


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def chunk_for_rag(text: str, *, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    text = text or ""
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def _load_index(host: str) -> List[Dict[str, Any]]:
    path = _index_path(host)
    items: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.debug("RAG load index failed: %s", e)
    return items


def _save_index(host: str, items: List[Dict[str, Any]]) -> None:
    path = _index_path(host)
    _ensure_host_dir(host)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def upsert_page(host: str, url: str, title: str, text: str, *, chunk_size: int, overlap: int, max_docs: int = 5000) -> int:
    """Chunk page text, embed and upsert into on-disk JSONL index for the host.
    Returns number of new chunks added.
    """
    if not host or not text:
        return 0
    chunks = chunk_for_rag(text, chunk_size=chunk_size, overlap=overlap)
    existing = _load_index(host)
    seen_ids = {it.get("id") for it in existing}
    added = 0
    for idx, ch in enumerate(chunks):
        cid = _sha1(f"{url}\n{idx}\n{ch[:200]}")
        if cid in seen_ids:
            continue
        vec = embed_text(ch, is_query=False)
        if not vec:
            continue
        existing.append({
            "id": cid,
            "url": url,
            "title": title,
            "text": ch,
            "embedding": vec,
        })
        seen_ids.add(cid)
        added += 1
        # cap
        if max_docs > 0 and len(existing) > max_docs:
            # drop oldest
            existing = existing[-max_docs:]
            seen_ids = {it.get("id") for it in existing}
    if added:
        try:
            _save_index(host, existing)
        except Exception as e:
            logger.debug("RAG save index failed: %s", e)
            return 0
    return added


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    import math
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def retrieve_top_k(host: str, query: str, *, k: int = 5) -> List[Dict[str, Any]]:
    if not host or not query:
        return []
    qvec = embed_text(query, is_query=True)
    if not qvec:
        return []
    items = _load_index(host)
    if not items:
        return []
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for it in items:
        vec = it.get("embedding") or []
        s = _cosine(qvec, vec) if isinstance(vec, list) else 0.0
        scored.append((s, it))
    scored.sort(key=lambda t: t[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for s, it in scored[: max(1, k) ]:
        out.append({
            "text": it.get("text") or "",
            "url": it.get("url") or "",
            "title": it.get("title") or "",
            "score": float(s),
        })
    return out



