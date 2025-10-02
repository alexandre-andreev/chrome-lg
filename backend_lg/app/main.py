import logging
from typing import Any, Dict, List, Optional
import os
import re
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

# Ensure runtime flags are loaded from params.override.json (API keys remain in .env.local)
try:
    from .config import load_overrides_from_json
    load_overrides_from_json()
except Exception:
    pass

from .graph import app_graph as _compiled_graph, GRAPH_VIZ_PATH
from .services import sanitize_answer, EXA_API_KEY, GEMINI_API_KEY, exa_cache_invalidate_host, call_gemini_stream, call_gemini_text, embed_text
from .config import load_overrides_from_json, save_overrides_to_json
from .langfuse_tracer import get_langfuse_handler, is_enabled as langfuse_is_enabled, flush as langfuse_flush
import threading
import importlib

# Configure root logging (can be overridden by LOG_LEVEL env)
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
try:
    logging.basicConfig(level=getattr(logging, _log_level, logging.INFO))
except Exception:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    page_text: Optional[str] = None
    force_search: Optional[bool] = False


class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    used_search: bool = False
    decision: str | None = None
    graph_trace: List[str] | None = None
    debug: Dict[str, Any] | None = None


class ExportResponse(BaseModel):
    filename: str
    content: str


app = FastAPI(title="Chrome-bot Backend (LangGraph)", version="2.1.0")
_LAST_HOST: str | None = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize compiled graph pointer and mutex
app.state.app_graph = _compiled_graph
_cfg_lock = threading.Lock()


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "engine": "langgraph",
        "graph_image_exists": bool(GRAPH_VIZ_PATH and os.path.exists(GRAPH_VIZ_PATH)),
        "graph_mermaid_exists": bool(GRAPH_VIZ_PATH and os.path.exists((os.path.splitext(GRAPH_VIZ_PATH)[0] + ".mmd"))),
        "version": app.version,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    user_message = (payload.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")

    # Log page context for debugging
    page_text = (payload.page_text or "").strip()
    logger.info("Chat request: message=%r url=%r text_len=%d", 
                user_message[:50], payload.page_url, len(page_text))
    
    # Warn if page text looks suspicious
    if page_text and "DIAG" in page_text[:500]:
        logger.warning("Page text contains DIAG markers (possible extraction issue). Sample: %s", 
                      page_text[:200])
    
    if len(page_text) < 200 and payload.page_url:
        logger.warning("Short page text (%d chars) for URL: %s", len(page_text), payload.page_url)

    state_in = {
        "user_message": user_message,
        "page": {
            "url": payload.page_url,
            "title": payload.page_title,
            "text": page_text,
        },
        "force_search": bool(payload.force_search or False),
    }

    try:
        # Auto cache invalidation on host change (process-global, simple heuristic)
        host = None
        try:
            if payload.page_url:
                host = __import__("urllib.parse").urllib.parse.urlparse(payload.page_url).hostname
        except Exception:
            host = None
        global _LAST_HOST
        if host and host != _LAST_HOST:
            try:
                removed = exa_cache_invalidate_host(host)
                logger.info("EXA cache invalidated for host=%s, removed=%s", host, removed)
            except Exception:
                pass
            _LAST_HOST = host

        # Invoke LangGraph with Langfuse tracing if enabled
        langfuse_handler = get_langfuse_handler()
        if langfuse_handler:
            out = app.state.app_graph.invoke(state_in, config={"callbacks": [langfuse_handler]})
        else:
            out = app.state.app_graph.invoke(state_in)
        
        answer = (out.get("final_answer") or "").strip()
        sources = out.get("search_results") or []
        used_search = bool(out.get("used_search"))
        decision = out.get("decision")
        graph_trace = out.get("graph_trace") or []
        if not answer:
            answer = "Не удалось получить содержательный ответ."
        rag_debug = None
        try:
            if (os.getenv("RAG_DEBUG") or "").lower() in ("1", "true", "yes"):
                rag_items = out.get("rag_items") or []
                rag_debug = {
                    "enabled": (os.getenv("RAG_ENABLED") or "").lower() in ("1", "true", "yes"),
                    "upserted": int(out.get("rag_upserted") or 0),
                    "retrieved_count": len(rag_items),
                    "top_urls": [it.get("url") for it in rag_items[:5] if it.get("url")],
                }
        except Exception:
            rag_debug = None
        debug = {
            "entities": out.get("entities"),
            "intent_explicit_search": out.get("intent_explicit_search"),
            "missing_entities_on_page": out.get("missing_entities_on_page"),
            "notes_count": len(out.get("notes") or []),
            "focus_count": len(out.get("focus") or []),
            "rag": rag_debug,
        }

        return ChatResponse(
            answer=sanitize_answer(answer),
            sources=sources,
            used_search=used_search,
            decision=decision,
            graph_trace=graph_trace,
            debug=debug,
        )
    except Exception as e:
        logger.exception("Error in /chat: %s", e)
        raise HTTPException(status_code=500, detail="Internal error while generating answer")
@app.post("/chat_stream")
async def chat_stream(payload: ChatRequest):
    if not (os.getenv("STREAMING_ENABLED") or "").lower() in ("1", "true", "yes"):
        raise HTTPException(status_code=403, detail="Streaming is disabled")
    # Require Gemini key for streaming; without it, instruct client to fall back to /chat
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=403, detail="Streaming requires GEMINI_API_KEY")

    user_message = (payload.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")

    state_in = {
        "user_message": user_message,
        "page": {
            "url": payload.page_url,
            "title": payload.page_title,
            "text": payload.page_text,
        },
        "force_search": bool(payload.force_search or False),
    }

    # Build the graph up to compose_prompt, then stream LLM tokens
    try:
        # Run only prep/context/search/compose without call_gemini
        from .graph import build_prompt_fast
        
        # Use Langfuse tracing if enabled
        langfuse_handler = get_langfuse_handler()
        if langfuse_handler:
            out = build_prompt_fast(state_in, config={"callbacks": [langfuse_handler]})
        else:
            out = build_prompt_fast(state_in)
        
        prompt = out.get("draft_answer") or ""
        sources = out.get("search_results") or []
        used_search = bool(out.get("used_search"))
        # RAG debug snapshot for footer (optional)
        rag_footer = None
        try:
            if (os.getenv("RAG_DEBUG") or "").lower() in ("1", "true", "yes"):
                rag_items = out.get("rag_items") or []
                rag_footer = f"\n\n[RAG] on; upserted={int(out.get('rag_upserted') or 0)}; retrieved={len(rag_items)}"
        except Exception:
            rag_footer = None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare prompt: {e}")

    async def token_gen():
        first = True
        try:
            for chunk in call_gemini_stream(prompt):
                if not chunk:
                    continue
                # SSE-like text chunks
                yield chunk
                first = False
        except Exception as e:
            yield f"\n[stream-error] {e}"
        # Final footer with sources marker (optional)
        if used_search and sources:
            # keep it compact
            urls = [s.get("url") for s in sources if s.get("url")]
            if urls:
                yield "\n\nИсточники:\n" + "\n".join(urls[:3])
        # RAG footer (optional)
        if rag_footer:
            yield rag_footer

    return StreamingResponse(token_gen(), media_type="text/plain; charset=utf-8")


@app.get("/graph")
async def get_graph() -> Any:
    path = GRAPH_VIZ_PATH
    if path and os.path.exists(path):
        media_type = "image/svg+xml" if path.endswith(".svg") else "image/png"
        return FileResponse(path, media_type=media_type)
    # Mermaid fallback
    mmd_path = os.path.splitext(path or "")[0] + ".mmd"
    if mmd_path and os.path.exists(mmd_path):
        with open(mmd_path, "r", encoding="utf-8") as f:
            content = f.read()
        return PlainTextResponse(content, media_type="text/plain; charset=utf-8")
    raise HTTPException(status_code=404, detail="Graph image not found. Enable with LANGGRAPH_VIZ=1 or set LANGGRAPH_VIZ_PATH")


@app.get("/debug/health")
async def health() -> Dict[str, Any]:
    return {
        "exa_configured": bool(EXA_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
        "graph_path": GRAPH_VIZ_PATH,
        "graph_exists": bool(GRAPH_VIZ_PATH and os.path.exists(GRAPH_VIZ_PATH)),
    }


_ALLOWED_CONFIG_KEYS = {
    "STREAMING_ENABLED",
    "RAG_ENABLED", "RAG_TOP_K", "RAG_DEBUG",
    "RAG_CHUNK_SIZE", "RAG_OVERLAP", "RAG_MAX_DOCS_PER_HOST",
    "LG_CHUNK_SIZE", "LG_CHUNK_OVERLAP", "LG_CHUNK_MIN_TOTAL",
    "LG_CHUNK_NOTES_MAX_CHUNKS",
    "LG_NOTES_MAX", "LG_NOTES_SHOW_MAX",
    "LG_SEARCH_MIN_CONTEXT_CHARS", "LG_PROMPT_TEXT_CHARS",
    "LG_EXA_TIME_BUDGET_S", "LG_SEARCH_RESULTS_MAX", "LG_SEARCH_SNIPPET_CHARS",
    "LG_ANSWER_MAX_SENTENCES",
    "LG_SEARCH_HEURISTICS",
    "GEMINI_MODEL",
    # EXA tuning
    "EXA_NUM_RESULTS", "EXA_GET_CONTENTS_N", "EXA_SUBPAGES", "EXA_EXTRAS_LINKS",
    "EXA_TEXT_MAX_CHARS", "EXA_LANG", "EXA_EXCLUDE_DOMAINS", "EXA_TIMEOUT_S",
    "EXA_RESEARCH_ENABLED", "EXA_RESEARCH_TIMEOUT_S", "EXA_SUMMARY_ENABLED",
    "RAG_INDEX_DIR",
}


@app.get("/config")
async def get_config() -> Dict[str, Any]:
    # Reload overlay to reflect file changes if any
    try:
        load_overrides_from_json()
    except Exception:
        pass
    return {k: os.getenv(k) for k in sorted(_ALLOWED_CONFIG_KEYS)}


def _hot_reload_graph_locked() -> None:
    # Re-apply overrides, then reload graph module and swap compiled graph
    load_overrides_from_json()
    mod_name = f"{__package__}.graph" if __package__ else "backend_lg.app.graph"
    mod = importlib.import_module(mod_name)
    importlib.reload(mod)
    app.state.app_graph = getattr(mod, "app_graph")


@app.post("/config")
async def post_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    values = {}
    for k, v in payload.items():
        if k in _ALLOWED_CONFIG_KEYS:
            values[k] = v
    if not values:
        return {"updated": 0}
    save_overrides_to_json(values)
    with _cfg_lock:
        try:
            _hot_reload_graph_locked()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Reload failed: {e}")
    return {"updated": len(values)}


@app.get("/debug/embed_ok")
async def debug_embed_ok() -> Dict[str, Any]:
    try:
        ok_doc = bool(embed_text("diagnostics:doc", is_query=False))
        ok_q = bool(embed_text("diagnostics:query", is_query=True))
        return {"doc": ok_doc, "query": ok_q}
    except Exception as e:
        return {"error": str(e)}


@app.api_route("/debug/rag_upsert_test", methods=["GET", "POST"])
async def debug_rag_upsert_test(payload: Optional[Dict[str, Any]] = None, host: Optional[str] = None, url: Optional[str] = None, title: Optional[str] = None, text: Optional[str] = None) -> Dict[str, Any]:
    try:
        from .rag import upsert_page, _index_path
        data = payload or {}
        _host = (host or data.get("host") or "example.com").strip()
        _url = (url or data.get("url") or f"https://{_host}/test").strip()
        _title = (title or data.get("title") or "RAG Diagnostics").strip()
        _text = (text or data.get("text") or ("DIAG\n" * 200)).strip()
        added = upsert_page(_host, _url, _title, _text, chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")), overlap=int(os.getenv("RAG_OVERLAP", "120")), max_docs=int(os.getenv("RAG_MAX_DOCS_PER_HOST", "5000")))
        return {"host": _host, "added": int(added), "index_path": _index_path(_host)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rag_upsert_test failed: {e}")


@app.api_route("/debug/rag_clear", methods=["GET", "POST"])
async def debug_rag_clear(payload: Optional[Dict[str, Any]] = None, host: Optional[str] = None) -> Dict[str, Any]:
    try:
        from .rag import _host_dir, _index_path
        data = payload or {}
        _host = (host or data.get("host") or "").strip()
        if not _host:
            raise HTTPException(status_code=400, detail="host is required")
        idx = _index_path(_host)
        removed = False
        try:
            if os.path.exists(idx):
                os.remove(idx)
                removed = True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"remove failed: {e}")
        # attempt to remove empty dir
        try:
            d = _host_dir(_host)
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        except Exception:
            pass
        return {"host": _host, "index_path": idx, "removed": removed}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rag_clear failed: {e}")


@app.api_route("/debug/rag_retrieve_test", methods=["GET", "POST"])
async def debug_rag_retrieve_test(payload: Optional[Dict[str, Any]] = None, host: Optional[str] = None, q: Optional[str] = None, k: Optional[int] = None) -> Dict[str, Any]:
    try:
        from .rag import retrieve_top_k
        _host = (host or (payload or {}).get("host") or "").strip()
        _q = (q or (payload or {}).get("q") or "пять ключевых принципов DevOps").strip()
        _k = int(k or (payload or {}).get("k") or os.getenv("RAG_TOP_K", "5"))
        if not _host:
            raise HTTPException(status_code=400, detail="host is required")
        items = retrieve_top_k(_host, _q, k=max(1, _k))
        return {"host": _host, "q": _q, "k": _k, "count": len(items or []), "items": items[:3] if items else []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rag_retrieve_test failed: {e}")


@app.api_route("/debug/rag_upsert_page", methods=["GET", "POST"])
async def debug_rag_upsert_page(payload: Optional[Dict[str, Any]] = None, page_url: Optional[str] = None, page_title: Optional[str] = None, page_text: Optional[str] = None) -> Dict[str, Any]:
    """Upsert real page chunks into RAG index for debugging/testing."""
    try:
        from .rag import upsert_page
        _url = (page_url or (payload or {}).get("page_url") or "").strip()
        _title = (page_title or (payload or {}).get("page_title") or "").strip()
        _text = (page_text or (payload or {}).get("page_text") or "").strip()
        if not _url:
            raise HTTPException(status_code=400, detail="page_url is required")
        if not _text:
            raise HTTPException(status_code=400, detail="page_text is required")
        
        # Parse host from URL
        try:
            from urllib.parse import urlparse
            host = urlparse(_url).hostname
            if not host:
                raise ValueError("Cannot parse hostname from URL")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid page_url: {e}")
        
        # Upsert chunks
        chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "900"))
        overlap = int(os.getenv("RAG_OVERLAP", "120"))
        max_docs = int(os.getenv("RAG_MAX_DOCS_PER_HOST", "5000"))
        added = upsert_page(host, _url, _title, _text, chunk_size=chunk_size, overlap=overlap, max_docs=max_docs)
        
        return {
            "host": host,
            "url": _url,
            "title": _title,
            "text_len": len(_text),
            "chunk_size": chunk_size,
            "overlap": overlap,
            "added": added
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("rag_upsert_page failed: %s", e)
        raise HTTPException(status_code=500, detail=f"rag_upsert_page failed: {e}")


@app.post("/export_md", response_model=ExportResponse)
async def export_md(payload: Dict[str, Any]) -> ExportResponse:
    page_url = (payload.get("page_url") or "").strip()
    page_title = (payload.get("page_title") or "").strip()
    page_text = (payload.get("page_text") or "").strip()
    if not page_text and not page_title and not page_url:
        raise HTTPException(status_code=400, detail="Empty page content")
    # Build markdown using Gemini if available; otherwise fallback to simple formatting
    title = page_title or (page_url or "Страница").split("/")[-1]
    safe_title = re.sub(r"[^\w\-а-яА-ЯёЁ ]+", "_", title).strip() or "page"
    filename = safe_title[:80] + ".md"
    md_content = f"# {title}\n\nURL: {page_url}\n\n" if title else ""
    body = page_text
    # Try literary processing via Gemini if key present
    try:
        if GEMINI_API_KEY:
            prompt = (
                "Суммируй и структурируй содержимое веб-страницы в Markdown. "
                "Добавь оглавление, основные разделы, списки, важные факты и определения. "
                "Не вставляй рекламные блоки, меню и навигацию. Язык — исходный.\n\n"
                f"TITLE: {page_title}\nURL: {page_url}\nTEXT:\n{page_text[:20000]}"
            )
            generated = call_gemini_text(prompt)
            if generated:
                md_content = generated
            else:
                md_content = md_content + body
        else:
            # Fallback: include structured attributes prominently if present
            try:
                parts = []
                for m in re.finditer(r"^(PRODUCT|BRAND|PRICE|MATERIAL|COLOR|SIZE|COMPOSITION|SKU|COUNTRY):\s*(.+)$", body, flags=re.M):
                    parts.append(f"- {m.group(1)}: {m.group(2)}")
                if parts:
                    md_content = md_content + "## Характеристики\n" + "\n".join(parts) + "\n\n" + body
                else:
                    md_content = md_content + body
            except Exception:
                md_content = md_content + body
    except Exception:
        md_content = md_content + body
    return ExportResponse(filename=filename, content=md_content)

