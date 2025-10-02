# 📊 Metrics Quick Start

## За 3 минуты: от нуля до первых графиков

### Шаг 1: Убедитесь, что Langfuse настроен ✅

```bash
# Проверьте .env.local в корне проекта
cat .env.local | grep LANGFUSE

# Должно быть:
# LANGFUSE_PUBLIC_KEY=pk-...
# LANGFUSE_SECRET_KEY=sk-...
# LANGFUSE_HOST=https://cloud.langfuse.com
```

Если ключей нет → см. [`LANGFUSE_SETUP.md`](LANGFUSE_SETUP.md)

---

### Шаг 2: Соберите данные 📡

```bash
# 1. Запустите backend (если ещё не запущен)
cd backend_lg
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8010

# 2. Используйте расширение Chrome для 20-50 запросов
#    на разных сайтах (Wikipedia, e-commerce, новости и т.д.)
#    
#    Langfuse автоматически собирает traces!
```

---

### Шаг 3: Анализ и визуализация 🎨

```bash
# Вернитесь в корень проекта
cd ..

# Анализ метрик (экспорт в JSON + TXT)
./analyze_metrics.sh --export-json --export-txt

# Визуализация
./visualize_metrics.sh

# Откройте интерактивный dashboard
firefox Metrics/charts/metrics_dashboard.html
# или
google-chrome Metrics/charts/metrics_dashboard.html
```

---

### Что вы увидите? 👀

#### В консоли (analyze_metrics.sh):
```
📊 Analyzing Langfuse metrics (last 7 days, limit=100)...
============================================================
Fetching traces from Langfuse...
Found 22 traces

⏱️  LATENCY ANALYSIS
----------------------------------------
  gemini_generate    | avg: 3500ms | p95: 4200ms | count: 15
  rag_retrieve       | avg: 450ms  | p95: 580ms  | count: 3

🔢 TOKEN USAGE
----------------------------------------
  Average tokens per request:
    Input:  4500 tokens
    Output: 350 tokens

💡 Recommendations:
  ⚠️  High input tokens (4500). Consider:
     - Decrease LG_PROMPT_TEXT_CHARS
     - Increase RAG_TOP_K to reduce raw text
```

#### В dashboard (metrics_dashboard.html):
- 🥧 **Круговая диаграмма** операций (Gemini, RAG, Exa)
- 📊 **Bar charts** latency и token usage
- 📅 **Timeline** трассировок
- 🎛️ Интерактивность: zoom, hover, filter

#### В файлах:
```bash
Metrics/
├── data/langfuse_metrics.json          # Структурированные данные
├── reports/langfuse_report.txt         # Текстовый отчёт + советы
└── charts/
    ├── operation_frequency.png         # Статические графики
    ├── latency_comparison.png
    ├── token_usage.png
    ├── trace_timeline.png
    ├── metrics_dashboard.html          # Интерактивный dashboard
    └── summary.txt                     # Краткая сводка
```

---

### Шаг 4: Оптимизация параметров 🔧

На основе рекомендаций из отчёта:

```bash
# 1. Редактируйте params.override.json
nano params.override.json

# Например, если input tokens слишком высокие:
{
  "LG_PROMPT_TEXT_CHARS": "8000",    # было 12000
  "RAG_TOP_K": "12",                 # было 8
  "LG_NOTES_SHOW_MAX": "6"           # было 10
}

# 2. Перезагрузите параметры (БЕЗ перезапуска сервера!)
curl -X POST http://localhost:8010/config \
  -H "Content-Type: application/json" \
  -d @params.override.json

# 3. Сделайте ещё 20-30 запросов через расширение

# 4. Сравните метрики:
./analyze_metrics.sh --export-json
cp Metrics/data/langfuse_metrics.json Metrics/data/optimized.json
./visualize_metrics.sh Metrics/data/optimized.json Metrics/charts/optimized

# 5. Сравните результаты:
diff Metrics/charts/summary.txt Metrics/charts/optimized/summary.txt
```

---

## 🚨 Troubleshooting

### "401 Unauthorized" при analyze_metrics.sh
```bash
# Проверьте Langfuse ключи
cat .env.local | grep LANGFUSE

# Убедитесь, что они корректны:
# https://cloud.langfuse.com → Settings → API Keys
```

### "No traces found"
```bash
# Сделайте запросы через расширение
# Проверьте Langfuse dashboard:
firefox https://cloud.langfuse.com
```

### "No latency data available"
```
# Это нормально для Langfuse 2.x API
# Latency доступен только в Langfuse UI → Analytics
# Token usage и operation counts будут работать!
```

### Пустые графики
```bash
# Нужно минимум 10-20 traces
# Используйте расширение на разных сайтах
```

---

## 📚 Дальнейшие шаги

1. **Изучите документацию:**
   - [`Metrics/README.md`](Metrics/README.md) - полная документация
   - [`Metrics/USAGE.md`](Metrics/USAGE.md) - детальные примеры

2. **Попробуйте A/B тестирование:**
   - Сохраните baseline метрики
   - Измените параметры
   - Сравните результаты

3. **Создайте snapshots:**
   ```bash
   mkdir -p Metrics/snapshots/$(date +%Y%m%d)
   cp Metrics/data/langfuse_metrics.json Metrics/snapshots/$(date +%Y%m%d)/
   cp Metrics/charts/*.png Metrics/snapshots/$(date +%Y%m%d)/
   ```

4. **Настройте регулярный мониторинг:**
   ```bash
   # Добавьте в cron (1 раз в неделю):
   0 9 * * 1 cd /path/to/chrome-lg && ./analyze_metrics.sh --export-json
   ```

---

**Приятного анализа!** 🎉

Если возникнут вопросы → см. полную документацию в [`Metrics/`](Metrics/)




