# План реализации: Расширение функциональности Exa get_contents

**Дата:** 2 октября 2025  
**Задача:** Добавить полноценную поддержку Exa API `get_contents` для расширения поисковой выдачи в чат

## Текущее состояние

### Что уже реализовано:
1. Базовая интеграция `get_contents` в функции `exa_search` (services.py:456-483)
2. Параметры конфигурации:
   - `EXA_GET_CONTENTS_N=2` - количество результатов для обогащения
   - `EXA_SUBPAGES=0` - поиск подстраниц
   - `EXA_EXTRAS_LINKS=0` - дополнительные ссылки
   - `EXA_TEXT_MAX_CHARS=1200` - макс. длина текста
   - `EXA_SUMMARY_ENABLED=0` - включение summaries
3. Трейсинг в Langfuse для операций Exa

### Ограничения текущей реализации:
- Используется только базовый текст (`text=True`)
- Не используются **highlights** (ключевые фрагменты)
- **Summaries** включены только через флаг, но не настроены
- Не используются **imageLinks**
- Нет поддержки **livecrawl** режимов
- Нет кастомных **query** для highlights/summaries

## Архитектура решения

### Компоненты для изменения:

```
params.override.json          # Новые параметры конфигурации
params.md                      # Документация параметров
backend_lg/app/services.py    # Расширение exa_search()
backend_lg/app/graph.py       # Использование новых данных в compose_prompt()
backend_lg/app/main.py        # Регистрация новых параметров
```

## Детальный план реализации

### 1. Новые параметры конфигурации

Добавить в `params.override.json`:

```json
{
  // Существующие...
  "EXA_GET_CONTENTS_N": "2",
  "EXA_SUBPAGES": "0",
  "EXA_EXTRAS_LINKS": "0",
  "EXA_TEXT_MAX_CHARS": "1200",
  "EXA_SUMMARY_ENABLED": "0",
  
  // НОВЫЕ параметры:
  "EXA_HIGHLIGHTS_ENABLED": "1",           // Включить highlights
  "EXA_HIGHLIGHTS_PER_URL": "2",           // Количество highlights на результат
  "EXA_HIGHLIGHTS_NUM_SENTENCES": "2",     // Предложений в каждом highlight
  "EXA_HIGHLIGHTS_QUERY": "",              // Кастомный запрос для highlights (пусто = авто)
  
  "EXA_SUMMARY_QUERY": "",                 // Кастомный запрос для summary (пусто = авто)
  
  "EXA_LIVECRAWL": "fallback",             // never/fallback/always/preferred
  "EXA_LIVECRAWL_TIMEOUT_MS": "10000",     // Таймаут livecrawl
  
  "EXA_EXTRAS_IMAGE_LINKS": "0",           // Количество imageLinks
  
  "EXA_INCLUDE_HTML_TAGS": "0"             // Включать HTML-теги в текст
}
```

### 2. Структура обогащенных результатов

Расширить возвращаемую структуру `exa_search()`:

```python
{
    "title": str,
    "url": str,
    "snippet": str,                    # Существующий текст
    # НОВЫЕ поля:
    "highlights": List[str],           # Ключевые фрагменты
    "highlightScores": List[float],    # Релевантность фрагментов
    "summary": str,                    # Краткое саммари
    "subpages": List[Dict],            # Подстраницы (рекурсивная структура)
    "extras": {
        "links": List[str],            # Дополнительные ссылки
        "imageLinks": List[str]        # Изображения
    }
}
```

### 3. Изменения в services.py

#### 3.1 Обновить функцию `exa_search()`

**Текущий код (строки 456-483):**
```python
if get_n > 0 and base:
    tops = [it["url"] for it in base[:get_n] if it.get("url")]
    if tops:
        contents = _exa_client.get_contents(
            tops,
            subpages=subpages,
            extras={"links": 1 if extras_links else 0},
            text=True,
        )
```

**Новая реализация:**
```python
# Построение параметров get_contents на основе конфига
highlights_enabled = _env_flag("EXA_HIGHLIGHTS_ENABLED", "1")
highlights_per_url = int(os.getenv("EXA_HIGHLIGHTS_PER_URL", "2"))
highlights_sentences = int(os.getenv("EXA_HIGHLIGHTS_NUM_SENTENCES", "2"))
highlights_query = os.getenv("EXA_HIGHLIGHTS_QUERY", "").strip()

summary_query = os.getenv("EXA_SUMMARY_QUERY", "").strip()

livecrawl_mode = os.getenv("EXA_LIVECRAWL", "fallback")
livecrawl_timeout = int(os.getenv("EXA_LIVECRAWL_TIMEOUT_MS", "10000"))

image_links_n = int(os.getenv("EXA_EXTRAS_IMAGE_LINKS", "0"))
include_html = _env_flag("EXA_INCLUDE_HTML_TAGS", "0")

# Параметры text
text_params = {
    "maxCharacters": max(300, text_max),
    "includeHtmlTags": include_html
}

# Параметры highlights
highlights_params = None
if highlights_enabled:
    highlights_params = {
        "highlightsPerUrl": highlights_per_url,
        "numSentences": highlights_sentences
    }
    if highlights_query:
        highlights_params["query"] = highlights_query

# Параметры summary
summary_params = None
if summary_enabled:
    summary_params = {}
    if summary_query:
        summary_params["query"] = summary_query

# Вызов get_contents
contents = _exa_client.get_contents(
    tops,
    text=text_params,
    highlights=highlights_params,
    summary=summary_params,
    subpages=subpages,
    livecrawl=livecrawl_mode,
    livecrawlTimeout=livecrawl_timeout,
    extras={
        "links": 1 if extras_links else 0,
        "imageLinks": image_links_n
    }
)

# Обогащение результатов
for c in contents.results:
    url = c.url
    if url in url_to_data:
        continue
    
    enriched = {
        "text": (c.text or "")[:text_max],
        "highlights": getattr(c, "highlights", []) or [],
        "highlightScores": getattr(c, "highlightScores", []) or [],
        "summary": getattr(c, "summary", "") or "",
        "subpages": [],
        "extras": {}
    }
    
    # Subpages
    if hasattr(c, "subpages") and c.subpages:
        for sub in c.subpages[:3]:  # Лимит для производительности
            enriched["subpages"].append({
                "url": getattr(sub, "url", ""),
                "title": getattr(sub, "title", ""),
                "text": (getattr(sub, "text", "") or "")[:500]
            })
    
    # Extras
    if hasattr(c, "extras"):
        extras_obj = c.extras
        enriched["extras"] = {
            "links": getattr(extras_obj, "links", []) or [],
            "imageLinks": getattr(extras_obj, "imageLinks", []) or []
        }
    
    url_to_data[url] = enriched
```

### 4. Изменения в graph.py

#### 4.1 Обновить `compose_prompt()` (строки 495-500)

**Текущий код:**
```python
if results:
    snippets = [ (r.get("snippet") or "").replace("\n", " ")[: max(100, LG_SEARCH_SNIPPET_CHARS) ] 
                for r in results[: max(1, LG_SEARCH_RESULTS_MAX) ] ]
    snippets = [s for s in snippets if s]
    if snippets:
        parts.append("РЕЗУЛЬТАТЫ ПОИСКА:\n- " + "\n- ".join(snippets))
```

**Новая реализация:**
```python
if results:
    search_lines = []
    for idx, r in enumerate(results[: max(1, LG_SEARCH_RESULTS_MAX)], 1):
        # Основной текст/snippet
        snippet = (r.get("snippet") or "").replace("\n", " ")[: max(100, LG_SEARCH_SNIPPET_CHARS)]
        
        # Highlights (приоритетнее snippet)
        highlights = r.get("highlights") or []
        if highlights:
            # Используем highlights вместо snippet для более релевантной информации
            highlight_text = " | ".join(highlights[:2])
            search_lines.append(f"[{idx}] {r.get('title', 'Источник')}: {highlight_text}")
        elif snippet:
            search_lines.append(f"[{idx}] {snippet}")
        
        # Summary (если есть)
        summary = (r.get("summary") or "").strip()
        if summary:
            search_lines.append(f"   Краткое содержание: {summary[:300]}")
        
        # Subpages (если есть важная дополнительная информация)
        subpages = r.get("subpages") or []
        if subpages:
            for sub in subpages[:2]:  # Максимум 2 подстраницы
                sub_text = (sub.get("text") or "")[:200]
                if sub_text:
                    search_lines.append(f"   Подстраница: {sub_text}")
    
    if search_lines:
        parts.append("РЕЗУЛЬТАТЫ ПОИСКА:\n" + "\n".join(search_lines))
```

### 5. Регистрация параметров в main.py

Добавить в `_ALLOWED_CONFIG_KEYS` (строка ~285):

```python
_ALLOWED_CONFIG_KEYS = {
    # ... существующие ...
    
    # Новые EXA get_contents параметры
    "EXA_HIGHLIGHTS_ENABLED",
    "EXA_HIGHLIGHTS_PER_URL", 
    "EXA_HIGHLIGHTS_NUM_SENTENCES",
    "EXA_HIGHLIGHTS_QUERY",
    "EXA_SUMMARY_QUERY",
    "EXA_LIVECRAWL",
    "EXA_LIVECRAWL_TIMEOUT_MS",
    "EXA_EXTRAS_IMAGE_LINKS",
    "EXA_INCLUDE_HTML_TAGS",
}
```

### 6. Документация в params.md

Добавить секцию:

```markdown
## Параметры Exa get_contents

### EXA_HIGHLIGHTS_ENABLED (по умолчанию: 1)
Включить извлечение ключевых фрагментов (highlights) из контента.
Highlights - это наиболее релевантные предложения, выбранные LLM.

### EXA_HIGHLIGHTS_PER_URL (по умолчанию: 2)
Количество highlights для каждого результата поиска.
Диапазон: 1-5. Больше = подробнее, но медленнее.

### EXA_HIGHLIGHTS_NUM_SENTENCES (по умолчанию: 2)
Количество предложений в каждом highlight.
Диапазон: 1-3. Больше = больше контекста.

### EXA_HIGHLIGHTS_QUERY (по умолчанию: "")
Кастомный запрос для направления выбора highlights.
Пусто = автоматически на основе поискового запроса.
Пример: "Ключевые технические характеристики"

### EXA_SUMMARY_ENABLED (по умолчанию: 0)
Включить генерацию краткого саммари каждой страницы.
⚠️ Увеличивает стоимость API запросов.

### EXA_SUMMARY_QUERY (по умолчанию: "")
Кастомный запрос для генерации summary.
Пример: "Основные выводы и рекомендации"

### EXA_LIVECRAWL (по умолчанию: "fallback")
Режим живого краулинга страниц:
- `never`: только кеш Exa
- `fallback`: кеш → краулинг при отсутствии (рекомендуется)
- `always`: всегда краулить (медленно, свежие данные)
- `preferred`: краулить → кеш при ошибке

### EXA_LIVECRAWL_TIMEOUT_MS (по умолчанию: 10000)
Таймаут livecrawl в миллисекундах.
Диапазон: 5000-30000. Баланс: скорость vs покрытие.

### EXA_EXTRAS_IMAGE_LINKS (по умолчанию: 0)
Количество URL изображений для извлечения с каждой страницы.
0 = отключено. 1-5 = включено (для будущих визуальных фич).

### EXA_INCLUDE_HTML_TAGS (по умолчанию: 0)
Включить HTML-теги в текст для лучшего понимания структуры LLM.
0 = чистый текст. 1 = с тегами (экспериментально).
```

## Последовательность реализации

1. ✅ **Этап 1:** Анализ существующего кода (выполнено)
2. **Этап 2:** Добавление параметров конфигурации
   - Обновить `params.override.json`
   - Обновить `params.md`
   - Зарегистрировать в `main.py`
3. **Этап 3:** Расширение `exa_search()` в `services.py`
   - Построение параметров для `get_contents`
   - Обработка новых полей ответа
   - Обогащение результатов
4. **Этап 4:** Интеграция в промпт (`graph.py`)
   - Использование highlights вместо snippet
   - Добавление summaries
   - Отображение subpages
5. **Этап 5:** Тестирование
   - Проверить с разными комбинациями параметров
   - Валидация структуры результатов
   - Проверка трейсинга в Langfuse

## Преимущества реализации

1. **Качество ответов:**
   - Highlights дают наиболее релевантные фрагменты
   - Summaries предоставляют сжатый контекст
   - Subpages расширяют покрытие информации

2. **Гибкость:**
   - Все параметры настраиваемые через UI (params)
   - Можно отключить дорогие функции (summaries)
   - Контроль затрат через конфигурацию

3. **Производительность:**
   - Livecrawl fallback балансирует скорость и свежесть
   - Лимиты на количество highlights/subpages
   - Кеширование работает на уровне search

4. **Мониторинг:**
   - Трейсинг Langfuse сохраняется
   - Детальная структура для анализа в metrics

## Риски и митигация

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Увеличение стоимости API | Средняя | Параметры по умолчанию консервативные; summaries=0 |
| Увеличение latency | Средняя | Livecrawl=fallback; таймауты настроены |
| Ошибки парсинга новых полей | Низкая | Defensive coding, getattr с defaults |
| Переполнение промпта | Низкая | Лимиты на highlights/subpages, truncation |

## Метрики успеха

- Highlights используются в 70%+ результатов где доступны
- Latency увеличивается не более чем на 15%
- Качество ответов (субъективная оценка пользователя) улучшается
- Costs/request остаются в пределах бюджета

## Следующие шаги после реализации

1. Добавить UI-контролы в options.html для новых параметров
2. Визуализация highlights в sidepanel.js (подсветка)
3. Отображение изображений (imageLinks) в чате
4. A/B тестирование с/без highlights
5. Аналитика в metrics: использование highlights vs snippet

---

**Готово к реализации:** ✅  
**Ожидаемое время:** 2-3 часа  
**Приоритет:** Высокий


