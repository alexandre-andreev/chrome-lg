from typing import TypedDict, Optional, List, Dict, Any
import re
import os
import logging
# module logger
logger = logging.getLogger(__name__)
from langgraph.graph import StateGraph, END

from .services import (
    exa_search,
    exa_research,
    call_gemini_text,
    sanitize_answer,
    synthesize_search_queries_llm,
    evaluate_answer_sufficiency,
	assess_need_search_llm,
)


class AgentState(TypedDict, total=False):
    user_message: str
    page: Dict[str, Optional[str]]
    need_search: Optional[bool]
    search_query: Optional[str]
    search_results: Optional[List[Dict[str, Any]]]
    draft_answer: Optional[str]
    final_answer: Optional[str]
    error: Optional[str]
    used_search: Optional[bool]
    decision: Optional[str]
    graph_trace: List[str]
    notes: List[str]
    entities: List[str]
    intent_explicit_search: Optional[bool]
    missing_entities_on_page: Optional[bool]
    focus: List[str]
    search_attempts: Optional[int]


def prepare_context(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("prepare_context")
    state["graph_trace"] = trace
    page = state.get("page") or {}
    txt = (page.get("text") or "")
    # Увеличим лимит для первичной передачи
    page["text"] = txt[:24000]
    state["page"] = page
    # Инициализации
    state.setdefault("graph_trace", [])
    state.setdefault("notes", [])
    state.setdefault("focus", [])
    return state


def _chunk_text(text: str, chunk_size: int = 4000, overlap: int = 200) -> List[str]:
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


def need_chunk(state: AgentState) -> str:
    txt = (state.get("page", {}).get("text") or "")
    if len(txt) > 6000:
        state["graph_trace"] = (state.get("graph_trace") or []) + ["need_chunk:chunk"]
        return "chunk"
    state["graph_trace"] = (state.get("graph_trace") or []) + ["need_chunk:no_chunk"]
    return "no_chunk"


def chunk_notes(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("chunk_notes")
    state["graph_trace"] = trace
    page_txt = (state.get("page", {}).get("text") or "")
    if not page_txt:
        return state
    chunks = _chunk_text(page_txt, chunk_size=3500, overlap=150)

    collected: List[str] = []
    for idx, ch in enumerate(chunks[:6]):
        prompt = (
            "Внимательно изучи текст текущей страницы от начала до конца. "
            "Выдели ключевые факты, цифры, определения и подзаголовки. "
            "Отвечай по возможности строго в контексте теущей веб-страницы. При необходимости прочитай страницу еще раз"
            "При подготовке ответа списком перчисляй по одному факту на строку, каждый пункт начинай с '- '.\n\n"
            f"ФРАГМЕНТ {idx+1}/{len(chunks)}:\n{ch}"
        )
        try:
            note_text = call_gemini_text(prompt)
        except Exception:
            note_text = ""
        if not note_text:
            continue
        for line in note_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("- "):
                collected.append(line[2:].strip())
            else:
                collected.append(line)
        if len(collected) >= 12:
            break
    if collected:
        state["notes"] = collected[:12]
    return state


# Убраны устаревшие эвристики (_has_explicit_search_intent, entity extraction)


def _extract_focus_snippets(query: str, page_text: str, *, window: int = 260, max_snippets: int = 6) -> List[str]:
    # Упрощённый безопасный вариант: не используем словари и "бусты"
    q = (query or "").lower()
    t = (page_text or "")
    tl = t.lower()
    terms = list(dict.fromkeys(re.findall(r"[a-zа-яё0-9]{3,}", q)))
    matches: List[str] = []
    used = set()
    for term in terms:
        pos = 0
        while len(matches) < max_snippets:
            idx = tl.find(term, pos)
            if idx == -1:
                break
            start = max(0, idx - window)
            end = min(len(t), idx + len(term) + window)
            snippet = t[start:end].strip()
            key = (start, end)
            if key not in used and snippet:
                used.add(key)
                matches.append(snippet)
            pos = idx + len(term)
            if len(matches) >= max_snippets:
                break
    return matches[:max_snippets]


def _prepare_focus(state: AgentState) -> None:
    # Лёгкая подсветка релевантных кусочков страницы без эвристических списков
    focus = _extract_focus_snippets(state.get("user_message") or "", state.get("page", {}).get("text") or "")
    if focus:
        state["focus"] = focus


def build_search_query(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("build_search_query")
    state["graph_trace"] = trace
    user = (state.get("user_message") or "").strip()
    title = (state.get("page", {}).get("title") or "").strip()
    url = (state.get("page", {}).get("url") or "").strip()
    host = None
    try:
        if url:
            host = __import__("urllib.parse").urllib.parse.urlparse(url).hostname
    except Exception:
        host = None

    # LLM-классификация необходимости поиска (быстрая развилка)
    try:
        assess = assess_need_search_llm(user, state.get("page") or {}, state.get("notes") or [])
    except Exception:
        assess = {"need_search": True, "search_query": "", "rationale": "fallback:error"}

    state["need_search"] = bool(assess.get("need_search"))
    if not state["need_search"]:
        state["search_queries"] = []
        state["search_query"] = ""
        return state

    # LLM-синтез 1–3 запросов на основе контекста страницы
    synth = synthesize_search_queries_llm(user, state.get("page") or {}, state.get("notes") or [])
    queries = synth.get("queries") or []
    if not queries:
        base_q = f"{user} {title}".strip() if title else user
        queries = [base_q]
    state["search_query"] = queries[0]
    state["search_queries"] = queries
    # Сохраним хост для фильтрации на фронте/бэке при необходимости
    if host:
        state.setdefault("page", {})["host"] = host
    return state


def exa_search_node(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("exa_search")
    state["graph_trace"] = trace
    queries = state.get("search_queries") or [state.get("search_query") or ""]
    # Time budget per EXA node execution (seconds)
    time_budget_s = 2.5
    import time as _time
    started = _time.time()
    try:
        logger.debug("EXA search queries: %s", queries[:3])
    except Exception:
        pass
    results: List[Dict[str, Any]] = []
    # Пробуем до 2 запросов максимум в рамках узла и не превышаем time budget
    host = (state.get("page", {}).get("host") or None)
    # Quick language guess from user message or page title
    umsg = (state.get("user_message") or "")
    ptitle = (state.get("page", {}).get("title") or "")
    lang_hint = None
    if re.search(r"[а-яё]", umsg + " " + ptitle, flags=re.I):
        lang_hint = "ru"
    elif re.search(r"[a-z]", umsg + " " + ptitle, flags=re.I):
        lang_hint = "en"

    for q in (queries[:2] if queries else []):
        if _time.time() - started > time_budget_s:
            break
        r = exa_search(q, num_results=5, host=host, lang=lang_hint, use_cache=False)
        if r and not (len(r) == 1 and r[0].get("error")):
            results = r
            break
        results = r  # сохраняем последний ответ (для диагностики)
    # Research fallback только если остался бюджет времени
    if (not results or (len(results) == 1 and results[0].get("error"))) and (_time.time() - started) <= time_budget_s:
        q0 = (queries[0] if queries else "").strip()
        research_results = exa_research(f"{q0}. Сжато перечисли 3-5 фактов без лишней воды")
        if research_results and not research_results[0].get("error"):
            results = research_results
    state["search_results"] = results
    state["used_search"] = True
    return state


def compose_prompt(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("compose_prompt")
    state["graph_trace"] = trace
    sys = (
        "Ты — умный ассистент по анализу веб-страниц. "
        "Сначала внимательно изучи весь предоставленный текст страницы, включая списки и подзаголовки, затем отвечай. "
        "Отвечай строго по контексту страницы, но если тебе не хватает информации используй все доступные данные чтобы подготовить ответ. "
        "Формат: короткие ясные пункты; списки начинай с '- '. Без ссылок и служебных пометок."
    )
    parts: List[str] = [sys]
    page = state.get("page") or {}
    lines: List[str] = []
    if page.get("url"): lines.append(f"URL: {page['url']}")
    if page.get("title"): lines.append(f"TITLE: {page['title']}")
    # Фокусные сниппеты — в начало, чтобы направить модель
    focus = state.get("focus") or []
    if focus:
        lines.append("FOCUS SNIPPETS:\n- " + "\n- ".join([s.replace("\n", " ")[:400] for s in focus]))

    # STRUCTURED из PRODUCT/BRAND/PRICE в page_text
    page_text_full = page.get("text") or ""
    structured = []
    for m in re.finditer(r"^(PRODUCT|BRAND|PRICE):\s*(.+)$", page_text_full, flags=re.M):
        k, v = m.group(1), m.group(2)
        structured.append(f"\u200b{k}: {v}")
    if structured:
        lines.append("STRUCTURED:\n- " + "\n- ".join(structured[:6]))

    # Включаем усечённый TEXT всегда, чтобы сохранить конкретику (цифры/факты)
    notes = state.get("notes") or []
    if page_text_full:
        lines.append(f"TEXT: {page_text_full[:12000]}")
    # Добавим сжатые заметки, если есть
    if notes:
        lines.append("NOTES:\n- " + "\n- ".join(notes[:6]))
    if lines:
        parts.append("КОНТЕКСТ СТРАНИЦЫ:\n" + "\n".join(lines))
    results = state.get("search_results") or []
    if results:
        snippets = [ (r.get("snippet") or "").replace("\n", " ")[:300] for r in results[:3] ]
        snippets = [s for s in snippets if s]
        if snippets:
            parts.append("РЕЗУЛЬТАТЫ ПОИСКА:\n- " + "\n- ".join(snippets))
    parts.append("ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n" + (state.get("user_message") or ""))
    state["draft_answer"] = "\n\n".join(parts)
    return state


def call_gemini(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("call_gemini")
    state["graph_trace"] = trace
    prompt = state.get("draft_answer") or ""
    state["final_answer"] = call_gemini_text(prompt)
    return state


def postprocess_answer(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("postprocess_answer")
    state["graph_trace"] = trace
    ans = state.get("final_answer") or ""
    cleaned = sanitize_answer(ans)
    # Heuristic: if the user asked a general overview question, limit to 10 sentences
    try:
        q = (state.get("user_message") or "").strip().lower()
        def _is_general_overview_question(text: str) -> bool:
            patterns = [
                r"\bо\s+ч[её]м\s+эта\s+страниц",
                r"\bчто\s+за\s+страниц",
                r"\bкратко\s+опиши\s+страниц",
                r"\bwhat\s+is\s+this\s+page\s+about",
                r"\bwhat\s+is\s+this\s+site",
                r"\boverview\b",
                r"\bsummary\b",
            ]
            for p in patterns:
                if re.search(p, text):
                    return True
            return False
        def _limit_sentences(text: str, max_sentences: int = 10) -> str:
            # naive sentence split
            parts = re.split(r"(?<=[\.!?])\s+", text)
            if len(parts) <= max_sentences:
                return text
            return " ".join(parts[:max_sentences]).strip()
        if _is_general_overview_question(q) and cleaned:
            cleaned = _limit_sentences(cleaned, 10)
    except Exception:
        pass
    state["final_answer"] = cleaned
    return state


# Убран повторный цикл оценки полноты — поиск выполняется заранее для каждого запроса


def finalize(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("finalize")
    state["graph_trace"] = trace
    results = state.get("search_results") or []
    state["search_results"] = results[:3]
    return state


builder = StateGraph(AgentState)
GRAPH_NODES: List[str] = []
GRAPH_EDGES: List[Dict[str, str]] = []  # {src, dst, label}
builder.add_node("prepare_context", prepare_context)
builder.add_node("chunk_notes", chunk_notes)
builder.add_node("build_search_query", build_search_query)
builder.add_node("exa_search", exa_search_node)
builder.add_node("compose_prompt", compose_prompt)
builder.add_node("call_gemini", call_gemini)
builder.add_node("postprocess_answer", postprocess_answer)
GRAPH_NODES.extend([
    "prepare_context",
    "chunk_notes",
    "build_search_query",
    "exa_search",
    "compose_prompt",
    "call_gemini",
    "postprocess_answer",
    "assess",
    "ensure_answer",
    "finalize",
])
def ensure_answer(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("ensure_answer")
    state["graph_trace"] = trace
    txt = (state.get("final_answer") or "").strip()
    if txt:
        return state
    # Fallback: синтез из notes или короткого текста страницы с приоритетом числовых фактов
    notes = state.get("notes") or []
    if notes:
        # Выделим пункты с цифрами
        prioritized = [n for n in notes if re.search(r"\d", n)] + [n for n in notes if not re.search(r"\d", n)]
        bullets = "- " + "\n- ".join(prioritized[:6])
        state["final_answer"] = bullets
        return state
    snippet = (state.get("page", {}).get("text") or "")[:800]
    if snippet:
        state["final_answer"] = snippet
    return state
builder.add_node("finalize", finalize)

builder.set_entry_point("prepare_context")
builder.add_conditional_edges("prepare_context", need_chunk, {
    "chunk": "chunk_notes",
    "no_chunk": "build_search_query",
})
GRAPH_EDGES.extend([
    {"src": "prepare_context", "dst": "chunk_notes", "label": "chunk"},
    {"src": "prepare_context", "dst": "build_search_query", "label": "no_chunk"},
])
builder.add_edge("chunk_notes", "build_search_query")
def _after_build_router(state: AgentState) -> str:
    return "search" if state.get("need_search") else "no_search"
builder.add_conditional_edges("build_search_query", _after_build_router, {
    "search": "exa_search",
    "no_search": "compose_prompt",
})
builder.add_edge("exa_search", "compose_prompt")
builder.add_edge("compose_prompt", "call_gemini")
builder.add_edge("call_gemini", "postprocess_answer")
def assess(state: AgentState) -> AgentState:
    trace = state.get("graph_trace") or []
    trace.append("assess")
    state["graph_trace"] = trace
    user = (state.get("user_message") or "")
    ans = (state.get("final_answer") or "")
    info = evaluate_answer_sufficiency(user, ans)
    need = bool(info.get("should_search")) or bool(info.get("insufficient"))
    attempts = int(state.get("search_attempts") or 0)
    # Total passes: initial (0) + 1 retry => attempts < 1 allows one more return to exa_search
    if need and attempts < 1:
        q = (info.get("search_query") or "").strip()
        if not q:
            title = (state.get("page", {}).get("title") or "").strip()
            q = f"{user} {title}".strip()
        existing = state.get("search_queries") or []
        new_list = [q] + [x for x in existing if x != q]
        state["search_queries"] = new_list[:3]
        state["search_query"] = q
        state["search_attempts"] = attempts + 1
        state["decision"] = "retry"
    else:
        state["decision"] = "continue"
    return state
def assess_router(state: AgentState) -> str:
    return state.get("decision") or "continue"
builder.add_node("assess", assess)
builder.add_node("ensure_answer", ensure_answer)
builder.add_edge("postprocess_answer", "assess")
builder.add_conditional_edges("assess", assess_router, {
    "retry": "exa_search",
    "continue": "ensure_answer",
})
builder.add_edge("ensure_answer", "finalize")
builder.add_edge("finalize", END)
GRAPH_EDGES.extend([
    {"src": "chunk_notes", "dst": "build_search_query", "label": ""},
    {"src": "build_search_query", "dst": "exa_search", "label": "need_search"},
    {"src": "build_search_query", "dst": "compose_prompt", "label": "no_search"},
    {"src": "exa_search", "dst": "compose_prompt", "label": ""},
    {"src": "compose_prompt", "dst": "call_gemini", "label": ""},
    {"src": "call_gemini", "dst": "postprocess_answer", "label": ""},
    {"src": "postprocess_answer", "dst": "assess", "label": ""},
    {"src": "assess", "dst": "exa_search", "label": "retry"},
    {"src": "assess", "dst": "ensure_answer", "label": "continue"},
    {"src": "ensure_answer", "dst": "finalize", "label": ""},
    {"src": "finalize", "dst": "END", "label": ""},
])

app_graph = builder.compile()

# Visualization (optional)
# Enable if:
# - LANGGRAPH_VIZ in ("1","true","yes","open","save") OR
# - LANGGRAPH_VIZ_PATH is set (always save to custom path)
_viz_mode = (os.environ.get("LANGGRAPH_VIZ") or "").lower().strip()
_custom_path = os.environ.get("LANGGRAPH_VIZ_PATH")
_fmt = (os.environ.get("LANGGRAPH_VIZ_FORMAT") or "").lower().strip()

def _infer_ext_from_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".svg"):
        return ext.lstrip(".")
    return "svg"

_default_ext = "svg"
if _custom_path:
    _default_ext = _infer_ext_from_path(_custom_path)
elif _fmt in ("png", "svg"):
    _default_ext = _fmt

_default_filename = f"_graph.{_default_ext}"
GRAPH_VIZ_PATH = _custom_path or os.path.join(os.path.dirname(__file__), _default_filename)

def _save_graph_image(path: str, ext: str) -> bool:
    """Attempt multiple visualization methods depending on langgraph version.
    Returns True if saved successfully.
    """
    # 1) Try builder.visualize if available (works on some versions)
    try:
        if hasattr(builder, "visualize"):
            builder.visualize(path)
            return True
    except Exception as e:
        logger.debug("builder.visualize failed: %s", e)

    # 2) Try compiled.visualize if available (older docs suggest this)
    try:
        if hasattr(app_graph, "visualize"):
            app_graph.visualize(path)
            return True
    except Exception as e:
        logger.debug("compiled.visualize failed: %s", e)

    # 3) Try builder.get_graph() with draw_* methods
    try:
        get_graph = getattr(builder, "get_graph", None)
        if callable(get_graph):
            g = get_graph()
            if ext == "png" and hasattr(g, "draw_png"):
                g.draw_png(path)
                return True
            if ext == "svg" and hasattr(g, "draw_svg"):
                g.draw_svg(path)
                return True
            # Mermaid fallback
            to_mermaid = getattr(g, "to_mermaid", None)
            if callable(to_mermaid):
                m = to_mermaid()
                if isinstance(m, str) and m.strip():
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(m)
                    return True
    except Exception as e:
        logger.debug("get_graph/draw fallback failed: %s", e)

    return False

def _build_mermaid() -> str:
    lines: List[str] = ["graph TD"]
    # nodes
    uniq_nodes = list(dict.fromkeys(GRAPH_NODES + ["END"]))
    for n in uniq_nodes:
        safe = n.replace("\"", "'")
        lines.append(f"  {safe}({safe})")
    # edges
    for e in GRAPH_EDGES:
        src = e.get("src") or ""
        dst = e.get("dst") or ""
        label = e.get("label") or ""
        if label:
            lines.append(f"  {src}--|{label}|-->{dst}")
        else:
            lines.append(f"  {src}-->{dst}")
    return "\n".join(lines) + "\n"

try:
    _enabled = bool(_viz_mode in ("1", "true", "yes", "open", "save") or _custom_path)
    if _enabled:
        try:
            dirpath = os.path.dirname(GRAPH_VIZ_PATH) or "."
            if not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
        except Exception as mkdir_e:
            logger.warning("LangGraph viz: failed to ensure directory %s: %s", os.path.dirname(GRAPH_VIZ_PATH), mkdir_e)
        ok = _save_graph_image(GRAPH_VIZ_PATH, _default_ext)
        if ok:
            logger.info("LangGraph visualization saved: %s", GRAPH_VIZ_PATH)
            # best-effort open if supported by this version
            if _viz_mode == "open":
                try:
                    if hasattr(builder, "visualize"):
                        builder.visualize()
                    elif hasattr(app_graph, "visualize"):
                        app_graph.visualize()
                except Exception as e:
                    logger.debug("open-visualize failed: %s", e)
        else:
            # Mermaid fallback file alongside requested path
            base, _ = os.path.splitext(GRAPH_VIZ_PATH)
            mermaid_path = base + ".mmd"
            try:
                with open(mermaid_path, "w", encoding="utf-8") as f:
                    f.write(_build_mermaid())
                logger.info("LangGraph mermaid saved: %s", mermaid_path)
            except Exception as e:
                logger.warning("LangGraph mermaid save failed: %s (path=%s)", e, mermaid_path)
except Exception as e:
    # Do not fail app import on visualization errors
    logger.warning("LangGraph visualization failed: %s (path=%s)", e, GRAPH_VIZ_PATH)

# Fast helper to build prompt without running the whole graph
def build_prompt_fast(state_in: AgentState) -> AgentState:
    state: AgentState = dict(state_in)
    state = prepare_context(state)
    nxt = need_chunk(state)
    if nxt == "chunk":
        state = chunk_notes(state)
    state = build_search_query(state)
    if state.get("need_search"):
        state = exa_search_node(state)
    state = compose_prompt(state)
    return state
