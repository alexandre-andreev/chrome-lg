import logging
from typing import Any, Dict, List, Optional
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .graph import app_graph, GRAPH_VIZ_PATH
from .services import sanitize_answer, EXA_API_KEY, GEMINI_API_KEY, exa_cache_invalidate_host, call_gemini_stream

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    page_text: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    used_search: bool = False
    decision: str | None = None
    graph_trace: List[str] | None = None
    debug: Dict[str, Any] | None = None


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
        }
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
        debug = {
            "entities": out.get("entities"),
            "intent_explicit_search": out.get("intent_explicit_search"),
            "missing_entities_on_page": out.get("missing_entities_on_page"),
            "notes_count": len(out.get("notes") or []),
            "focus_count": len(out.get("focus") or []),
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

    user_message = (payload.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")

    state_in = {
        "user_message": user_message,
        "page": {
            "url": payload.page_url,
            "title": payload.page_title,
            "text": payload.page_text,
        }
    }

    # Build the graph up to compose_prompt, then stream LLM tokens
    try:
        # Run only prep/context/search/compose without call_gemini
        from .graph import build_prompt_fast
        out = build_prompt_fast(state_in)  # returns state with draft_answer
        prompt = out.get("draft_answer") or ""
        sources = out.get("search_results") or []
        used_search = bool(out.get("used_search"))
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

