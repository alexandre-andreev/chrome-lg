import logging
from typing import Any, Dict, List, Optional
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

# Ensure runtime flags are loaded from params.md (API keys remain in .env.local)
try:
    from .config import load_params_from_md
    load_params_from_md()
except Exception:
    pass

from .graph import app_graph, GRAPH_VIZ_PATH
from .services import sanitize_answer, EXA_API_KEY, GEMINI_API_KEY, exa_cache_invalidate_host, call_gemini_stream, call_gemini_text

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


app = FastAPI(title="Chrome-bot Backend (LangGraph)", version="2.0.0")
_LAST_HOST: str | None = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "engine": "langgraph",
        "graph_image_exists": bool(GRAPH_VIZ_PATH and os.path.exists(GRAPH_VIZ_PATH)),
        "graph_mermaid_exists": bool(GRAPH_VIZ_PATH and os.path.exists((os.path.splitext(GRAPH_VIZ_PATH)[0] + ".mmd"))),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
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

        out = app_graph.invoke(state_in)
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
        out = build_prompt_fast(state_in)  # returns state with draft_answer
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

