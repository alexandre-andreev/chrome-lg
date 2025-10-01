 Отличная идея! Langfuse — мощный инструмент для трассировки LangGraph, мониторинга стоимости и анализа производительности. Вот детальный план интеграции:

## План интеграции Langfuse

### 1. **Архитектура и подход**
- Langfuse поддерживает LangGraph нативно через декораторы и callbacks
- Будем отслеживать: промпты, токены, latency, стоимость, traces по узлам графа
- Данные будут доступны в веб-интерфейсе Langfuse для анализа

### 2. **Установка и настройка (этап 1)**

**Действия:**
1. Добавить в `requirements.txt`:
   ```
   langfuse>=2.0.0
   ```
2. Создать аккаунт на [langfuse.com](https://langfuse.com) (или self-hosted)
3. Получить ключи: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
4. Добавить в `.env.local`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com  # или свой хост
   ```

### 3. **Интеграция с LangGraph (этап 2)**

**Файл: `backend_lg/app/langfuse_callback.py` (новый)**
```python
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
import os
from typing import Optional

# Инициализация клиента
langfuse = None
if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
    langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    )

def get_langfuse_callback():
    """Return Langfuse callback handler for LangGraph."""
    if not langfuse:
        return None
    from langfuse.callback import CallbackHandler
    return CallbackHandler()
```

**Модификации в `graph.py`:**
- Обернуть узлы графа декоратором `@observe()`
- Добавить трассировку для вызовов Gemini и Exa
- Логировать метрики на каждом узле

### 4. **Трассировка ключевых операций (этап 3)**

**a) Gemini calls (`services.py`):**
```python
@observe(name="gemini_generate")
def call_gemini_text(prompt: str, ...) -> str:
    langfuse_context.update_current_observation(
        input=prompt[:500],
        metadata={"model": GEMINI_MODEL, "timeout": timeout_s}
    )
    # ... существующий код ...
    langfuse_context.update_current_observation(
        output=result[:500],
        usage={"prompt_tokens": len(prompt)//4, "completion_tokens": len(result)//4}
    )
    return result
```

**b) Exa search (`services.py`):**
```python
@observe(name="exa_search")
def exa_search(query: str, ...) -> List[Dict]:
    langfuse_context.update_current_observation(
        input={"query": query, "num_results": num_results}
    )
    # ... существующий код ...
    langfuse_context.update_current_observation(
        output={"count": len(results), "cached": use_cache}
    )
    return results
```

**c) RAG operations (`rag.py`):**
```python
@observe(name="rag_upsert")
def upsert_page(...):
    langfuse_context.update_current_observation(
        input={"host": host, "text_len": len(text)}
    )
    # ... код ...
    langfuse_context.update_current_observation(
        output={"chunks_added": added}
    )

@observe(name="rag_retrieve")
def retrieve_top_k(...):
    langfuse_context.update_current_observation(
        input={"host": host, "query": query, "k": k}
    )
    # ... код ...
    langfuse_context.update_current_observation(
        output={"retrieved": len(items)}
    )
```

### 5. **Интеграция в main.py (этап 4)**

**В `/chat` endpoint:**
```python
from .langfuse_callback import get_langfuse_callback

@app.post("/chat", response_model=ChatResponse)
@observe(name="chat_request")
async def chat(payload: ChatRequest) -> ChatResponse:
    langfuse_context.update_current_observation(
        user_id=payload.page_url,  # или другой ID
        session_id=None,  # можно добавить session tracking
        metadata={
            "url": payload.page_url,
            "title": payload.page_title,
            "force_search": payload.force_search
        }
    )

    # Вызов графа с callback
    callback = get_langfuse_callback()
    if callback:
        out = app.state.app_graph.invoke(state_in, config={"callbacks": [callback]})
    else:
        out = app.state.app_graph.invoke(state_in)

    # Логируем итоговые метрики
    langfuse_context.update_current_observation(
        output={
            "answer_length": len(answer),
            "sources_count": len(sources),
            "used_search": used_search,
            "rag_stats": debug.get("rag") if debug else None
        }
    )
```

### 6. **Расширенная аналитика (этап 5)**

**Файл: `backend_lg/app/langfuse_analytics.py` (новый)**
```python
def track_costs(trace_id: str, model: str, tokens: dict):
    """Track API costs per request."""
    cost_per_1k = {
        "gemini-2.5-flash-lite": {"input": 0.00001, "output": 0.00003},
        "gemini-2.0-flash": {"input": 0.00002, "output": 0.00006}
    }
    # Calculate and log to Langfuse

def analyze_bottlenecks():
    """Fetch traces from Langfuse and identify slow nodes."""
    # Использовать Langfuse API для анализа
```

### 7. **Dashboard и мониторинг (этап 6)**

**Langfuse Dashboard покажет:**
- 📊 Trace tree: визуализация графа выполнения
- 💰 Cost tracking: стоимость по моделям и операциям
- ⏱️ Latency: задержки на каждом узле (chunk, search, RAG, LLM)
- 📈 Usage metrics: количество вызовов, кэш hit rate
- 🔍 Debug: инспекция промптов и ответов

### 8. **Опциональные параметры в params.override.json**

```json
{
  "LANGFUSE_ENABLED": "1",
  "LANGFUSE_DEBUG": "0",
  "LANGFUSE_SAMPLE_RATE": "1.0"  // 1.0 = логировать всё, 0.1 = 10%
}
```

### 9. **Порядок реализации (что делать первым)**

**Приоритет 1 (основа):**
1. ✅ Установить `langfuse` пакет
2. ✅ Получить ключи и добавить в `.env.local`
3. ✅ Создать `langfuse_callback.py`
4. ✅ Обернуть `/chat` endpoint декоратором `@observe`

**Приоритет 2 (детализация):**
5. ✅ Добавить трассировку в `call_gemini_text`, `call_gemini_stream`
6. ✅ Добавить трассировку в `exa_search`, `exa_research`
7. ✅ Добавить трассировку в RAG: `upsert_page`, `retrieve_top_k`

**Приоритет 3 (аналитика):**
8. ✅ Создать функции расчёта стоимости
9. ✅ Настроить custom scoring в Langfuse
10. ✅ Создать дашборды для мониторинга

---

## Что это даст?

✅ **Прозрачность**: полная видимость, что происходит внутри графа
✅ **Оптимизация**: найти узкие места (медленные узлы, дорогие промпты)
✅ **Отладка**: инспектировать промпты и ответы для улучшения качества
✅ **Контроль затрат**: отслеживать расходы на Gemini и Exa в реальном времени
✅ **A/B тестирование**: сравнивать разные конфигурации параметров

---

**Начать реализацию?** Могу последовательно:
1. Добавить зависимости в `requirements.txt`
2. Создать `langfuse_callback.py`
3. Интегрировать в `main.py` и `services.py`
4. Или сначала показать пример для одного endpoint, а потом масштабировать?
