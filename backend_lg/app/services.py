import os
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

try:
    # Load from repo root .env.local if present
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env.local'))
except Exception:
    load_dotenv()

import google.generativeai as genai
from exa_py import Exa
import requests
import time
import json

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.exception("Gemini configure failed: %s", e)
else:
    logger.warning("GEMINI_API_KEY is not set")

_exa_client: Optional[Exa] = None
if EXA_API_KEY:
    try:
        _exa_client = Exa(api_key=EXA_API_KEY)
    except Exception as e:
        logger.exception("Exa init failed: %s", e)
else:
    logger.warning("EXA_API_KEY is not set")


SYSTEM_INSTRUCTION = (
    "Ты — умный ассистент, специализируешься на анализе веб-страниц в браузере. "
    "Отвечай строго по контексту текущей страницы. Если контекста достаточно — не выполняй поиск. "
    "Если данных не хватает — обращайся к внешнему поиску (EXA), но избегай нерелевантных источников. "
    "Если в контексте есть раздел STRUCTURED — считай его источником правды и обязательно используй его. "
    "Игнорируй нерелевантные результаты поиска; если они не о текущем объекте — не используй. "
    "Отвечай кратко и по делу. Формат: отдельные мысли с новой строки; списки — '- '. Без служебных пометок."
)


def sanitize_answer(text: str) -> str:
    if not text:
        return text
    # Convert markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove stray bracketed tokens
    text = re.sub(r"\[([^\]]+)\]", r"\1", text)
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Normalize bullets to '- '
    text = re.sub(r"\n\s*[-*]\s+", "\n- ", text)
    # Collapse 3+ consecutive newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim trailing spaces on each line and overall
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    return text


def call_gemini_text(prompt: str, model_name: str = "gemini-2.5-flash") -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_INSTRUCTION,
    )
    resp = model.generate_content(prompt)
    txt = getattr(resp, "text", "") or ""
    if not txt:
        # Try candidates/parts fallback
        try:
            parts = resp.candidates[0].content.parts if resp.candidates else []
            texts = []
            for p in parts:
                if getattr(p, "text", None):
                    texts.append(p.text)
            txt = " ".join(texts)
        except Exception:
            txt = ""
    return txt


def call_gemini_stream(prompt: str, model_name: str = "gemini-2.5-flash"):
    """Yield text chunks as they arrive from Gemini."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_INSTRUCTION,
    )
    try:
        resp = model.generate_content(prompt, stream=True)
    except TypeError:
        # Fallback for SDKs without stream kwarg
        resp = model.generate_content(prompt, stream=True)  # type: ignore
    for chunk in resp:
        try:
            if getattr(chunk, "text", None):
                yield chunk.text
            else:
                parts = []
                for p in getattr(chunk, "candidates", [])[0].content.parts:
                    if getattr(p, "text", None):
                        parts.append(p.text)
                if parts:
                    yield " ".join(parts)
        except Exception:
            continue


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        # Try to extract first JSON object
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end+1])
        except Exception:
            return None
    return None


def call_gemini_json(prompt: str, model_name: str = "gemini-2.5-flash") -> Optional[Dict[str, Any]]:
    """Ask Gemini to return JSON only. Parse defensively."""
    instruction = (
        "Ты отвечаешь ТОЛЬКО валидным JSON-объектом без лишнего текста и форматирования. "
        "Не используй markdown. Не добавляй комментарии."
    )
    final_prompt = instruction + "\n\n" + prompt
    raw = call_gemini_text(final_prompt, model_name=model_name)
    return _safe_parse_json(raw)


def synthesize_search_queries_llm(user_message: str, page: Dict[str, Optional[str]], notes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Return dict {"queries": [str,...], "rationale": str}.
    LLM builds short, language-appropriate web search queries from page context.
    """
    title = page.get("title") or ""
    url = page.get("url") or ""
    text = (page.get("text") or "")[:2000]
    notes = notes or []
    # Extract lightweight structured hints if present in text
    structured: List[str] = []
    try:
        for m in re.finditer(r"^(PRODUCT|BRAND|PRICE):\s*(.+)$", text, flags=re.M):
            structured.append(f"{m.group(1)}: {m.group(2)}")
    except Exception:
        pass
    notes_str = "\n- ".join(notes[:6]) if notes else ""
    structured_str = "\n- ".join(structured[:6]) if structured else ""
    prompt = (
        "Сформируй 1–3 кратких веб-запроса для поиска дополнительной информации. "
        "Запросы должны быть на языке вопроса/страницы и без лишних слов. "
        "Верни JSON строго формата {\"queries\": [\"...\"], \"rationale\": \"...\"}.\n\n"
        f"Вопрос пользователя: {user_message}\n"
        f"URL: {url}\nTITLE: {title}\nTEXT:\n{text}\n"
    )
    if structured_str:
        prompt += f"СТРУКТУРА:\n- {structured_str}\n"
    if notes_str:
        prompt += f"ЗАМЕТКИ:\n- {notes_str}\n"
    data = call_gemini_json(prompt)
    if not isinstance(data, dict):
        return {"queries": [user_message.strip() or title.strip()], "rationale": "fallback:parse_failed"}
    queries = [q.strip() for q in (data.get("queries") or []) if isinstance(q, str) and q.strip()]
    if not queries:
        queries = [user_message.strip() or title.strip()]
    return {"queries": list(dict.fromkeys(queries))[:3], "rationale": data.get("rationale") or ""}


def assess_need_search_llm(user_message: str, page: Dict[str, Optional[str]], notes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Return dict with keys: need_search(bool), search_query(str), rationale(str)."""
    page_title = page.get("title") or ""
    page_url = page.get("url") or ""
    page_text = (page.get("text") or "")[:4000]
    notes = notes or []
    notes_str = "\n- ".join(notes[:6]) if notes else ""
    prompt = (
        "Оцени, хватает ли контента страницы, чтобы ответить на вопрос пользователя. "
        "Верни JSON со структурой {\"need_search\": bool, \"search_query\": string, \"rationale\": string}. "
        "Если информации не хватает, сформируй осмысленный запрос для веб-поиска (кратко и по-делу).\n\n"
        f"Вопрос: {user_message}\n"
        f"URL: {page_url}\nTITLE: {page_title}\nTEXT: {page_text}\n"
    )
    if notes_str:
        prompt += f"NOTES:\n- {notes_str}\n"
    data = call_gemini_json(prompt)
    if not isinstance(data, dict):
        return {"need_search": False, "search_query": "", "rationale": "fallback:parse_failed"}
    # Normalize
    need = bool(data.get("need_search"))
    q = data.get("search_query") or ""
    rat = data.get("rationale") or ""
    return {"need_search": need, "search_query": q, "rationale": rat}


def evaluate_answer_sufficiency(user_message: str, answer_text: str) -> Dict[str, Any]:
    """Return dict with keys: insufficient(bool), should_search(bool), search_query(str)."""
    prompt = (
        "Оцени полноту ответа относительно вопроса. Верни JSON {\"insufficient\": bool, \"should_search\": bool, \"search_query\": string}.\n\n"
        f"Вопрос: {user_message}\n"
        f"Ответ: {answer_text}\n"
    )
    data = call_gemini_json(prompt)
    if not isinstance(data, dict):
        return {"insufficient": False, "should_search": False, "search_query": ""}
    return {
        "insufficient": bool(data.get("insufficient")),
        "should_search": bool(data.get("should_search")),
        "search_query": data.get("search_query") or "",
    }


_EXA_CACHE_TTL_S = int(os.getenv("EXA_CACHE_TTL_S", "600"))  # default 10 minutes
_EXA_CACHE_MAX = int(os.getenv("EXA_CACHE_MAX", "512"))
_exa_cache: Dict[Tuple[str, str, str], Tuple[float, List[Dict[str, Any]]]] = {}

def _normalize_query(q: str) -> str:
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q

def _detect_lang(text: str) -> str:
    t = (text or "")
    if re.search(r"[а-яё]", t, flags=re.I):
        return "ru"
    if re.search(r"[a-z]", t, flags=re.I):
        return "en"
    return "auto"

def _cache_get(key: Tuple[str, str, str]) -> Optional[List[Dict[str, Any]]]:
    item = _exa_cache.get(key)
    if not item:
        return None
    ts, val = item
    if (time.time() - ts) > _EXA_CACHE_TTL_S:
        try:
            del _exa_cache[key]
        except Exception:
            pass
        return None
    return val

def _cache_set(key: Tuple[str, str, str], val: List[Dict[str, Any]]) -> None:
    # Lightweight size cap cleanup
    if len(_exa_cache) >= _EXA_CACHE_MAX:
        try:
            # remove oldest ~10% by timestamp
            items = sorted(_exa_cache.items(), key=lambda kv: kv[1][0])
            for k, _ in items[: max(1, _EXA_CACHE_MAX // 10)]:
                _exa_cache.pop(k, None)
        except Exception:
            _exa_cache.clear()
    _exa_cache[key] = (time.time(), val)

def exa_cache_invalidate_host(host: str) -> int:
    """Invalidate all cache entries for a given host. Returns number of removed items."""
    if not host:
        return 0
    keys = list(_exa_cache.keys())
    removed = 0
    for k in keys:
        try:
            if k[0] == host:
                _exa_cache.pop(k, None)
                removed += 1
        except Exception:
            continue
    return removed

def exa_cache_clear() -> None:
    """Clear entire EXA cache."""
    _exa_cache.clear()

def exa_search(query: str, *, num_results: int = 6, host: Optional[str] = None, lang: Optional[str] = None, use_cache: bool = True) -> List[Dict[str, Any]]:
    if not _exa_client:
        logger.error("Exa client not configured")
        return [{"error": "Exa client not configured"}]
    norm_q = _normalize_query(query)
    lang = lang or _detect_lang(query)
    host = (host or "_")
    key = (host, lang, norm_q)
    cache_disabled_env = (os.getenv("EXA_CACHE_DISABLED") or "").lower() in ("1", "true", "yes")
    if use_cache and not cache_disabled_env:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    try:
        results = _exa_client.search_and_contents(
            query,
            num_results=num_results,
            text={"max_characters": 1000},
        )
        val = [
            {"title": r.title, "url": r.url, "snippet": r.text}
            for r in results.results
        ]
        if use_cache and not cache_disabled_env:
            _cache_set(key, val)
        return val
    except Exception as e:
        logger.exception("Exa search failed: %s", e)
        err = [{"error": f"Search failed with exception: {e}"}]
        if use_cache and not cache_disabled_env:
            _cache_set(key, err)
        return err


def exa_research(instructions: str, *, model: str = "exa-research", timeout_s: int = 15) -> List[Dict[str, Any]]:
    """Use Exa Research API to get synthesized findings across sources.
    Returns list of dicts with title/url/snippet.
    """
    if not EXA_API_KEY:
        return [{"error": "Exa API key missing"}]
    try:
        base = "https://api.exa.ai/research/v1"
        headers = {"x-api-key": EXA_API_KEY, "content-type": "application/json"}
        resp = requests.post(base, headers=headers, json={"instructions": instructions, "model": model}, timeout=10)
        resp.raise_for_status()
        rid = (resp.json() or {}).get("research_id") or (resp.json() or {}).get("id")
        if not rid:
            return [{"error": "Exa research_id missing in response"}]
        # Poll
        deadline = time.time() + timeout_s
        results: List[Dict[str, Any]] = []
        while time.time() < deadline:
            r = requests.get(f"{base}/{rid}", headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json() or {}
                items = data.get("results") or data.get("events") or []
                # Normalize a few top items
                for it in items:
                    url = it.get("url") or it.get("source_url") or it.get("link")
                    title = it.get("title") or it.get("headline") or ""
                    snippet = it.get("content") or it.get("text") or it.get("summary") or ""
                    if url or snippet:
                        results.append({"title": title, "url": url, "snippet": snippet})
                if results:
                    break
            time.sleep(0.8)
        return results[:6] if results else [{"error": "Exa research returned no results"}]
    except Exception as e:
        logger.exception("Exa research failed: %s", e)
        return [{"error": f"Exa research failed: {e}"}]

