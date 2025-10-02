# Langfuse Metrics Visualization Guide

## 📊 Обзор

Система анализа и визуализации метрик Langfuse для оптимизации параметров Chrome-bot.

## 🛠️ Инструменты

### 1. `analyze_langfuse_metrics.py` - Анализ метрик

**Что делает:**
- Загружает traces из Langfuse
- Анализирует latency, token usage, частоту операций
- Даёт рекомендации по оптимизации параметров
- Экспортирует в JSON и TXT

**Использование:**
```bash
# Базовый анализ (вывод в консоль)
python analyze_langfuse_metrics.py

# С экспортом в файлы
python analyze_langfuse_metrics.py --export-json --export-txt

# Ограничить количество traces (max 100)
python analyze_langfuse_metrics.py --limit 50 --export-json
```

**Выходные файлы:**
- `langfuse_report.txt` - текстовый отчёт с рекомендациями
- `langfuse_metrics.json` - структурированные метрики для визуализации

---

### 2. `visualize_langfuse_metrics.py` - Визуализация

**Что делает:**
- Создаёт графики из JSON метрик
- Генерирует интерактивный HTML dashboard
- Сохраняет PNG изображения для документации

**Использование:**
```bash
# Базовая визуализация (использует langfuse_metrics.json)
python visualize_langfuse_metrics.py

# Указать другой файл и директорию
python visualize_langfuse_metrics.py my_metrics.json --output-dir my_charts
```

**Создаваемые файлы:**

| Файл | Описание |
|------|----------|
| `operation_frequency.png` | Круговая диаграмма частоты операций |
| `latency_comparison.png` | Сравнение latency (avg vs p95) |
| `token_usage.png` | Использование токенов (input/output/total) |
| `trace_timeline.png` | Timeline трассировок по типам |
| `metrics_dashboard.html` | **Интерактивный dashboard** (открыть в браузере) |
| `summary.txt` | Текстовая сводка |

---

## 🚀 Быстрый старт

### Шаг 1: Соберите данные
```bash
# Сделайте 20-50 запросов через расширение на разных сайтах
# Langfuse автоматически собирает traces
```

### Шаг 2: Экспортируйте метрики
```bash
python analyze_langfuse_metrics.py --export-json --export-txt
```

### Шаг 3: Создайте визуализации
```bash
python visualize_langfuse_metrics.py
```

### Шаг 4: Изучите результаты
```bash
# Откройте интерактивный dashboard
firefox charts/metrics_dashboard.html  # или chromium, google-chrome

# Или посмотрите статичные графики
eog charts/*.png

# Или прочтите текстовую сводку
cat charts/summary.txt
```

---

## 📈 Интерпретация результатов

### Operation Frequency (Частота операций)

**Что показывает:** Распределение типов операций

**Примеры:**
- `gemini_generate` 70% → LLM активно используется ✅
- `rag_retrieve` + `rag_upsert` < 20% → RAG недоиспользуется ⚠️
- `exa_search` > 30% → Слишком много внешних поисков, увеличьте RAG 💡

### Latency Analysis (если доступно)

**Что показывает:** Время выполнения операций

**Пороги:**
- `gemini_generate` > 5s → уменьшите `LG_PROMPT_TEXT_CHARS`
- `rag_retrieve` > 1s → уменьшите `RAG_TOP_K` или оптимизируйте индекс
- `exa_search` > 3s → уменьшите `EXA_NUM_RESULTS`

### Token Usage (если доступно)

**Что показывает:** Среднее использование токенов

**Оптимизация:**
- `avg_input > 8000` → Слишком большой промпт, уменьшите контекст
- `avg_output > 1000` → Ответы слишком длинные, добавьте `LG_ANSWER_MAX_SENTENCES`
- `cost > $0.001/request` → Рассмотрите более дешёвую модель

---

## 🔄 Итеративная оптимизация

### Процесс A/B тестирования:

1. **Baseline (базовая линия)**
   ```bash
   # Текущие параметры
   python analyze_langfuse_metrics.py --export-json
   cp langfuse_metrics.json baseline_metrics.json
   python visualize_langfuse_metrics.py baseline_metrics.json --output-dir baseline
   ```

2. **Эксперимент (изменённые параметры)**
   ```bash
   # Измените params.override.json
   # Перезагрузите через /config или перезапустите сервер
   
   # Сделайте 20-30 запросов
   
   # Экспортируйте новые метрики
   python analyze_langfuse_metrics.py --export-json
   cp langfuse_metrics.json experiment_metrics.json
   python visualize_langfuse_metrics.py experiment_metrics.json --output-dir experiment
   ```

3. **Сравнение**
   ```bash
   # Сравните визуально
   diff baseline/summary.txt experiment/summary.txt
   
   # Или создайте сравнительную таблицу
   python compare_metrics.py baseline_metrics.json experiment_metrics.json
   ```

---

## 📊 Примеры оптимизации

### Пример 1: Снижение latency

**Проблема:** `gemini_generate` avg = 8s

**Действия:**
```json
// params.override.json
{
  "LG_PROMPT_TEXT_CHARS": "12000" → "6000",
  "LG_NOTES_SHOW_MAX": "10" → "6",
  "GEMINI_MODEL": "gemini-2.0-flash" → "gemini-2.5-flash-lite"
}
```

**Ожидаемый результат:** latency ↓ 40-50%

### Пример 2: Снижение стоимости

**Проблема:** cost = $0.002/request

**Действия:**
```json
{
  "LG_PROMPT_TEXT_CHARS": "12000" → "8000",
  "LG_ANSWER_MAX_SENTENCES": "0" → "7",
  "RAG_TOP_K": "8" → "12"  // Больше RAG, меньше raw text
}
```

**Ожидаемый результат:** cost ↓ 30-40%

### Пример 3: Улучшение качества

**Проблема:** Ответы неполные или нерелевантные

**Действия:**
```json
{
  "RAG_TOP_K": "8" → "15",
  "LG_CHUNK_SIZE": "900" → "1200",
  "LG_NOTES_MAX": "6" → "12"
}
```

**Ожидаемый результат:** Качество ↑, но latency и cost тоже ↑

---

## 🎯 Рекомендуемые конфигурации

### Быстрая (Low Latency)
```json
{
  "LG_PROMPT_TEXT_CHARS": "6000",
  "LG_NOTES_SHOW_MAX": "5",
  "RAG_TOP_K": "5",
  "GEMINI_MODEL": "gemini-2.5-flash-lite",
  "LG_ANSWER_MAX_SENTENCES": "5"
}
```

### Экономная (Low Cost)
```json
{
  "LG_PROMPT_TEXT_CHARS": "8000",
  "RAG_TOP_K": "12",
  "RAG_ENABLED": "1",
  "LG_SEARCH_MIN_CONTEXT_CHARS": "20000",
  "LG_ANSWER_MAX_SENTENCES": "7"
}
```

### Качественная (High Quality)
```json
{
  "LG_PROMPT_TEXT_CHARS": "15000",
  "LG_NOTES_SHOW_MAX": "15",
  "RAG_TOP_K": "15",
  "LG_CHUNK_SIZE": "1200",
  "GEMINI_MODEL": "gemini-2.0-flash"
}
```

### Сбалансированная (Recommended)
```json
{
  "LG_PROMPT_TEXT_CHARS": "12000",
  "LG_NOTES_SHOW_MAX": "10",
  "RAG_TOP_K": "10",
  "RAG_ENABLED": "1",
  "GEMINI_MODEL": "gemini-2.5-flash-lite",
  "LG_ANSWER_MAX_SENTENCES": "0"
}
```

---

## 🔍 Troubleshooting

**Проблема:** "No latency data available"
- **Причина:** Langfuse 2.x не всегда возвращает latency через API
- **Решение:** Используйте Langfuse UI (Analytics) для latency метрик

**Проблема:** "No token usage data available"
- **Причина:** Токены не логируются для всех операций
- **Решение:** Проверьте Langfuse UI → Generations для детальных данных

**Проблема:** Графики пустые
- **Причина:** Недостаточно данных (< 5 traces)
- **Решение:** Сделайте больше запросов через расширение

---

## 📚 Дополнительные ресурсы

- **Langfuse Dashboard:** https://cloud.langfuse.com
- **API Documentation:** https://api.reference.langfuse.com
- **Gemini Pricing:** https://ai.google.dev/pricing
- **Optimization Guide:** См. `LANGFUSE_SETUP.md`

---

## 🎨 Кастомизация визуализаций

Вы можете модифицировать `visualize_langfuse_metrics.py` для:
- Добавления новых типов графиков
- Изменения цветовой схемы
- Экспорта в другие форматы (PDF, SVG)
- Создания анимаций (GIF) для трендов

Примеры доработок смотрите в комментариях кода.

---

**Приятной оптимизации!** 🚀

