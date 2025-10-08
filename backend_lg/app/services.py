import os
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from dotenv import load_dotenv
from .langfuse_tracer import trace_gemini_call, trace_exa_search

try:
    # Load from repo root .env.local if present
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env.local'))
except Exception:
    load_dotenv()

# Load overrides (non-secret) from params.override.json
try:
    from .config import load_overrides_from_json
    load_overrides_from_json()
except Exception:
    pass

# Silence noisy C++/gRPC/absl logs in non-GCP envs
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GRPC_TRACE", "")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("ABSL_LOGGING_STDERR_THRESHOLD", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from exa_py import Exa
import requests
import time
import json

logger = logging.getLogger(__name__)
# Reduce verbosity of common noisy libraries
for _name in ("google", "grpc", "absl"):
    try:
        logging.getLogger(_name).setLevel(logging.ERROR)
    except Exception:
        pass

# --- Embeddings ---
def embed_text(text: str, *, is_query: bool = False) -> Optional[list[float]]:
    """Return embedding vector using Google embeddings API. Returns None on failure.
    Uses model 'text-embedding-004'. If GEMINI_API_KEY missing, returns None.
    """
    if not GEMINI_API_KEY:
        logger.debug("embed_text: GEMINI_API_KEY missing; returning None (is_query=%s, len=%d)", is_query, len(text or ""))
        return None
    try:
        model = "text-embedding-004"
        task_type = "retrieval_query" if is_query else "retrieval_document"
        logger.debug("embed_text: calling Gemini embeddings (task=%s, len=%d)", task_type, len(text or ""))
        resp = genai.embed_content(model=model, content=text or "", task_type=task_type)
        vec = (resp.get("embedding") if isinstance(resp, dict) else getattr(resp, "embedding", None)) or None
        if isinstance(vec, list) and vec:
            logger.debug("embed_text: ok (is_query=%s, dim=%d)", is_query, len(vec))
            return vec
        logger.debug("embed_text: empty vector returned (is_query=%s)", is_query)
        return None
    except Exception as e:
        logger.debug("embed_text failed: %s", e)
        return None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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


# ===================== SBER TTS (OAuth NGW + SmartSpeech) =====================
SBER_TTS_ENABLED = (os.getenv("SBER_TTS_ENABLED", "0").lower() in ("1", "true", "yes"))
SBER_KEY = os.getenv("SBER_KEY")  # Authorization key (Base64 client_id:client_secret)

_SBER_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_SBER_TTS_REST_URL = "https://smartspeech.sber.ru/rest/v1/text:synthesize"

class _SberTokenManager:
    def __init__(self) -> None:
        self.access_token: Optional[str] = None
        self.expires_at_ms: int = 0

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def is_valid(self) -> bool:
        # consider token valid if at least 60s remain
        return bool(self.access_token) and (self._now_ms() + 60_000) < self.expires_at_ms

    def fetch(self) -> bool:
        if not SBER_KEY:
            logger.warning("SBER TTS: SBER_KEY not set; cannot obtain token")
            return False
        try:
            rq = str(uuid.uuid4())
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": rq,
                "Authorization": f"Basic {SBER_KEY}",
            }
            verify_ssl = (os.getenv("SBER_TTS_VERIFY", "1").lower() in ("1", "true", "yes"))
            # Bypass proxies/VPN env for this call
            sess = requests.Session()
            sess.trust_env = False
            resp = sess.post(
                _SBER_OAUTH_URL,
                headers=headers,
                data={"scope": "SALUTE_SPEECH_PERS"},
                timeout=10,
                proxies={"http": None, "https": None},
                verify=verify_ssl,
            )
            if resp.status_code != 200:
                logger.error("SBER OAuth: ошибка HTTP %s %s", resp.status_code, resp.text[:200])
                return False
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            token = data.get("access_token") or data.get("accessToken")
            exp = int(data.get("expires_at") or data.get("expiresAt") or 0)
            if not token:
                logger.error("SBER OAuth: в ответе отсутствует access_token")
                return False
            self.access_token = token
            # If expires_at not provided, fallback to 25 minutes from now
            if exp <= 0:
                exp = self._now_ms() + 25 * 60 * 1000
            self.expires_at_ms = int(exp)
            ttl_s = max(0, (self.expires_at_ms - self._now_ms()) // 1000)
            logger.info("SBER OAuth: токен получен, время жизни %s c", ttl_s)
            return True
        except Exception as e:
            logger.exception("SBER OAuth: исключение при получении токена: %s", e)
            return False

    def get(self) -> Optional[str]:
        if self.is_valid():
            return self.access_token
        ok = self.fetch()
        return self.access_token if ok else None

_sber_token = _SberTokenManager()


def sber_tts_synthesize(text: str, *, voice: Optional[str] = None, audio_encoding: Optional[str] = None, language: Optional[str] = None) -> Tuple[bytes, str]:
    """Synthesize speech using Sber SmartSpeech REST endpoint.
    Returns (audio_bytes, mime_type). Raises on failure.
    """
    if not SBER_TTS_ENABLED:
        raise RuntimeError("SBER TTS disabled")
    if not text or not text.strip():
        return b"", "audio/ogg"
    token = _sber_token.get()
    if not token:
        raise RuntimeError("SBER OAuth token not available")
    voice = voice or os.getenv("SBER_TTS_VOICE", "Nec_24000")
    audio_encoding = (audio_encoding or os.getenv("SBER_TTS_FORMAT", "opus")).lower()
    language = language or os.getenv("SBER_TTS_LANG", "ru-RU")
    # Build request: REST expects raw text body and Content-Type application/text (or application/ssml)
    # Extra parameters are passed via query string
    params = {
        "voice": voice,
        "audio_encoding": audio_encoding,
        "language": language,
    }
    rq = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
        "Content-Type": "application/text",
        "RqUID": rq,
    }
    # Bypass proxies for Sber endpoint
    sess = requests.Session()
    sess.trust_env = False
    verify_ssl = (os.getenv("SBER_TTS_VERIFY", "1").lower() in ("1", "true", "yes"))
    resp = sess.post(
        _SBER_TTS_REST_URL,
        headers=headers,
        params=params,
        data=(text or ""),
        timeout=30,
        proxies={"http": None, "https": None},
        verify=verify_ssl,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"SBER TTS failed: HTTP {resp.status_code} {resp.text[:200]}")
    content_type = resp.headers.get("content-type", "application/octet-stream")
    data = resp.content if resp.content else b""
    logger.info("SBER TTS: голос=%s формат=%s вход=%d символов ответ=%d байт", voice, audio_encoding, len(text or ""), len(data))
    return data, content_type


def sber_token_warmup() -> bool:
    """Fetch Sber OAuth token on startup (logs result). Returns True on success."""
    if not SBER_TTS_ENABLED:
        return False
    ok = _sber_token.fetch()
    if not ok:
        logger.error("SBER OAuth: инициализация при старте — ОШИБКА")
    return ok


def sber_is_enabled() -> bool:
    return SBER_TTS_ENABLED and bool(SBER_KEY)

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


def call_gemini_text(prompt: str, model_name: Optional[str] = None, timeout_s: Optional[float] = None) -> str:
    """Generate text with Gemini. If GEMINI_API_KEY is missing, return an empty string
    so the caller can fall back without raising 500.
    
    Args:
        prompt: Text prompt for generation
        model_name: Optional model name override
        timeout_s: Optional timeout override (default: 20s from env or param)
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is missing; returning empty text fallback")
        return ""
    model = genai.GenerativeModel(
        model_name=(model_name or GEMINI_MODEL),
        system_instruction=SYSTEM_INSTRUCTION,
    )
    # Hard timeout for generation to avoid hangs on network/SDK issues
    if timeout_s is None:
        timeout_s = float(os.getenv("GEMINI_TIMEOUT_S", "20"))
    timeout_s = float(timeout_s)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(model.generate_content, prompt)
            resp = fut.result(timeout=timeout_s)
    except FuturesTimeout:
        logger.error("Gemini generate_content timed out after %.1fs", timeout_s)
        return "Не удалось дождаться ответа от модели (таймаут). Попробуйте ещё раз или уменьшите объём контекста."
    except Exception as e:
        logger.exception("Gemini generate_content failed: %s", e)
        msg = str(e) if e else ""
        low = msg.lower()
        if "quota" in low or "resourceexhausted" in msg or "429" in low:
            return "Лимит запросов к модели исчерпан. Попробуйте позже или смените модель (GEMINI_MODEL)."
        return ""
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
    
    # Trace to Langfuse
    try:
        trace_gemini_call(
            prompt=prompt,
            response=txt,
            model=model_name or GEMINI_MODEL,
            metadata={"timeout_s": timeout_s, "mode": "text"}
        )
    except Exception:
        pass
    
    return txt


def call_gemini_stream(prompt: str, model_name: Optional[str] = None):
    """Yield text chunks as they arrive from Gemini. If API key is missing,
    yield a single explanatory chunk instead of raising.
    """
    if not GEMINI_API_KEY:
        yield "[stream-error] GEMINI_API_KEY is missing"
        return
    model = genai.GenerativeModel(
        model_name=(model_name or GEMINI_MODEL),
        system_instruction=SYSTEM_INSTRUCTION,
    )
    try:
        resp = model.generate_content(prompt, stream=True)
    except TypeError:
        # Fallback for SDKs without stream kwarg
        resp = model.generate_content(prompt, stream=True)  # type: ignore
    except Exception as e:
        msg = str(e) if e else ""
        low = msg.lower()
        if "quota" in low or "resourceexhausted" in msg or "429" in low:
            yield "Лимит запросов к модели исчерпан. Попробуйте позже или смените модель (GEMINI_MODEL)."
            return
        yield f"[stream-error] {e}"
        return
    except Exception as e:
        yield f"[stream-error] {e}"
        return
    
    # Collect chunks for Langfuse tracing
    full_response = []
    for chunk in resp:
        try:
            if getattr(chunk, "text", None):
                full_response.append(chunk.text)
                yield chunk.text
            else:
                parts = []
                for p in getattr(chunk, "candidates", [])[0].content.parts:
                    if getattr(p, "text", None):
                        parts.append(p.text)
                if parts:
                    text = " ".join(parts)
                    full_response.append(text)
                    yield text
        except Exception:
            continue
    
    # Trace to Langfuse after streaming completes
    try:
        trace_gemini_call(
            prompt=prompt,
            response="".join(full_response),
            model=model_name or GEMINI_MODEL,
            metadata={"mode": "stream"}
        )
    except Exception:
        pass


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


def call_gemini_json(prompt: str, model_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Ask Gemini to return JSON only. Parse defensively."""
    instruction = (
        "Ты отвечаешь ТОЛЬКО валидным JSON-объектом без лишнего текста и форматирования. "
        "Не используй markdown. Не добавляй комментарии."
    )
    final_prompt = instruction + "\n\n" + prompt
    raw = call_gemini_text(final_prompt, model_name=(model_name or GEMINI_MODEL))
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

def _env_flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").lower() in ("1", "true", "yes")


def _split_list(name: str) -> List[str]:
    raw = os.getenv(name, "") or ""
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def exa_search(query: str, *, num_results: int = 6, host: Optional[str] = None, lang: Optional[str] = None, use_cache: bool = True) -> List[Dict[str, Any]]:
    if not _exa_client:
        logger.error("Exa client not configured")
        return [{"error": "Exa client not configured"}]
    norm_q = _normalize_query(query)
    lang = (os.getenv("EXA_LANG") or None) or lang or _detect_lang(query)
    host = (host or "_")
    # Config
    cfg_num = int(os.getenv("EXA_NUM_RESULTS", str(num_results)))
    get_n = int(os.getenv("EXA_GET_CONTENTS_N", "2"))
    subpages = int(os.getenv("EXA_SUBPAGES", "0"))
    extras_links = _env_flag("EXA_EXTRAS_LINKS", "1")
    text_max = int(os.getenv("EXA_TEXT_MAX_CHARS", "1000"))
    timeout_s = float(os.getenv("EXA_TIMEOUT_S", "10"))
    excluded = set(_split_list("EXA_EXCLUDE_DOMAINS"))
    research_enabled = _env_flag("EXA_RESEARCH_ENABLED", "1")
    research_timeout = int(os.getenv("EXA_RESEARCH_TIMEOUT_S", "15"))
    summary_enabled = _env_flag("EXA_SUMMARY_ENABLED", "0")
    key = (host, lang, norm_q)
    cache_disabled_env = (os.getenv("EXA_CACHE_DISABLED") or "").lower() in ("1", "true", "yes")
    if use_cache and not cache_disabled_env:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    try:
        # site-bias when host present and query lacks site:
        q = norm_q
        try:
            if host and host != "_" and "site:" not in q:
                q = f"site:{host} {q}"
        except Exception:
            pass
        results = _exa_client.search_and_contents(
            q,
            num_results=cfg_num,
            text={"max_characters": max(300, text_max)},
        )
        # base list
        base = [
            {"title": r.title, "url": r.url, "snippet": r.text or ""}
            for r in results.results
            if not (r.url and any(r.url.startswith(f"http://{d}") or r.url.startswith(f"https://{d}") for d in excluded))
        ]
        # enrich top-N with get_contents if requested
        val = base
        try:
            if get_n > 0 and base:
                tops = [it["url"] for it in base[:get_n] if it.get("url")]
                if tops:
                    # Load new get_contents parameters
                    highlights_enabled = _env_flag("EXA_HIGHLIGHTS_ENABLED", "1")
                    highlights_per_url = int(os.getenv("EXA_HIGHLIGHTS_PER_URL", "2"))
                    highlights_sentences = int(os.getenv("EXA_HIGHLIGHTS_NUM_SENTENCES", "2"))
                    highlights_query = os.getenv("EXA_HIGHLIGHTS_QUERY", "").strip()
                    
                    summary_query = os.getenv("EXA_SUMMARY_QUERY", "").strip()
                    
                    livecrawl_mode = os.getenv("EXA_LIVECRAWL", "fallback").strip()
                    livecrawl_timeout = int(os.getenv("EXA_LIVECRAWL_TIMEOUT_MS", "10000"))
                    
                    image_links_n = int(os.getenv("EXA_EXTRAS_IMAGE_LINKS", "0"))
                    include_html = _env_flag("EXA_INCLUDE_HTML_TAGS", "0")
                    
                    # Build text parameters
                    text_params = {
                        "maxCharacters": max(300, text_max),
                        "includeHtmlTags": include_html
                    }
                    
                    # Build highlights parameters
                    highlights_params = None
                    if highlights_enabled:
                        highlights_params = {
                            "highlightsPerUrl": highlights_per_url,
                            "numSentences": highlights_sentences
                        }
                        if highlights_query:
                            highlights_params["query"] = highlights_query
                    
                    # Build summary parameters
                    summary_params = None
                    if summary_enabled:
                        summary_params = {}
                        if summary_query:
                            summary_params["query"] = summary_query
                    
                    # Build extras parameters
                    extras_params = {}
                    if extras_links:
                        extras_params["links"] = 1
                    if image_links_n > 0:
                        extras_params["imageLinks"] = image_links_n
                    
                    # Call get_contents with all parameters
                    # Note: Python SDK uses snake_case for parameter names
                    get_contents_kwargs = {
                        "text": text_params,
                        "subpages": subpages,
                        "livecrawl": livecrawl_mode,
                    }
                    
                    # Add optional parameters only if they are set
                    if highlights_params is not None:
                        get_contents_kwargs["highlights"] = highlights_params
                    if summary_params is not None:
                        get_contents_kwargs["summary"] = summary_params
                    if extras_params:
                        get_contents_kwargs["extras"] = extras_params
                    # livecrawl_timeout must be int (milliseconds in SDK, despite docs saying seconds)
                    if livecrawl_timeout and livecrawl_timeout > 0:
                        get_contents_kwargs["livecrawl_timeout"] = int(livecrawl_timeout)
                    
                    contents = _exa_client.get_contents(tops, **get_contents_kwargs)
                    
                    # Map enriched data by URL
                    url_to_enriched = {}
                    for c in contents.results if hasattr(contents, 'results') else []:
                        try:
                            enriched = {
                                "text": (c.text or "")[:text_max] if hasattr(c, "text") else "",
                                "highlights": list(getattr(c, "highlights", [])) if hasattr(c, "highlights") else [],
                                "highlightScores": list(getattr(c, "highlightScores", [])) if hasattr(c, "highlightScores") else [],
                                "summary": (getattr(c, "summary", "") or "") if hasattr(c, "summary") else "",
                                "subpages": [],
                                "extras": {}
                            }
                            
                            # Process subpages
                            if hasattr(c, "subpages") and c.subpages:
                                for sub in (c.subpages[:3] if isinstance(c.subpages, list) else []):
                                    try:
                                        subpage_data = {
                                            "url": getattr(sub, "url", "") or "",
                                            "title": getattr(sub, "title", "") or "",
                                            "text": (getattr(sub, "text", "") or "")[:500]
                                        }
                                        enriched["subpages"].append(subpage_data)
                                    except Exception:
                                        continue
                            
                            # Process extras
                            if hasattr(c, "extras"):
                                extras_obj = c.extras
                                try:
                                    enriched["extras"] = {
                                        "links": list(getattr(extras_obj, "links", [])) if hasattr(extras_obj, "links") else [],
                                        "imageLinks": list(getattr(extras_obj, "imageLinks", [])) if hasattr(extras_obj, "imageLinks") else []
                                    }
                                except Exception:
                                    pass
                            
                            url_to_enriched[c.url] = enriched
                        except Exception as ex:
                            logger.debug("Failed to process get_contents result: %s", ex)
                            continue
                    
                    # Merge enriched data into base results
                    new_val = []
                    for it in val:
                        u = it.get("url")
                        if u and u in url_to_enriched:
                            enriched = url_to_enriched[u]
                            it = dict(it)
                            # Use highlights as primary content if available, fallback to text
                            if enriched["highlights"]:
                                it["snippet"] = " | ".join(enriched["highlights"][:2])
                            elif enriched["text"]:
                                it["snippet"] = enriched["text"][:max(300, text_max)]
                            # Add new fields
                            it["highlights"] = enriched["highlights"]
                            it["highlightScores"] = enriched["highlightScores"]
                            it["summary"] = enriched["summary"]
                            it["subpages"] = enriched["subpages"]
                            it["extras"] = enriched["extras"]
                        new_val.append(it)
                    val = new_val
        except Exception as ex:
            logger.exception("get_contents enrichment failed: %s", ex)
        # optional summary fallback when model quota hit will be handled in graph; keep val
        if use_cache and not cache_disabled_env:
            _cache_set(key, val)
        
        # Trace to Langfuse
        try:
            trace_exa_search(
                query=query,
                results=val,
                metadata={
                    "host": host,
                    "lang": lang,
                    "num_results": cfg_num,
                    "cached": False
                }
            )
        except Exception:
            pass
        
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

