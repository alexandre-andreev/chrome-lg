# Metrics Scripts

## 📝 Описание скриптов

### `analyze_langfuse_metrics.py`

**Назначение:** Анализ traces из Langfuse и генерация отчётов

**Возможности:**
- Извлечение traces из Langfuse API (до 100 за раз)
- Анализ latency, token usage, частоты операций
- Рекомендации по оптимизации параметров
- Экспорт в JSON и TXT

**Использование:**
```bash
# Базовый анализ (только консоль)
python analyze_langfuse_metrics.py

# С экспортом
python analyze_langfuse_metrics.py --export-json --export-txt

# Ограничить количество traces
python analyze_langfuse_metrics.py --limit 50 --export-json
```

**Требования:**
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` в `.env.local`
- Установленный пакет `langfuse`

**Выходные файлы:**
- `../data/langfuse_metrics.json` - структурированные метрики
- `../reports/langfuse_report.txt` - текстовый отчёт

---

### `visualize_langfuse_metrics.py`

**Назначение:** Визуализация метрик из JSON

**Возможности:**
- Создание PNG графиков (matplotlib)
- Генерация интерактивного HTML dashboard (plotly)
- Текстовая сводка

**Использование:**
```bash
# Использовать файл по умолчанию (../data/langfuse_metrics.json)
python visualize_langfuse_metrics.py

# Указать другой файл
python visualize_langfuse_metrics.py /path/to/metrics.json

# Указать директорию для вывода
python visualize_langfuse_metrics.py --output-dir /path/to/output
```

**Требования:**
- Установленные пакеты: `matplotlib`, `plotly`, `pandas`
- Существующий JSON файл с метриками

**Создаваемые файлы:**
- `operation_frequency.png` - круговая диаграмма операций
- `latency_comparison.png` - сравнение latency (если доступно)
- `token_usage.png` - использование токенов
- `trace_timeline.png` - timeline трассировок
- `metrics_dashboard.html` - интерактивный dashboard
- `summary.txt` - текстовая сводка

---

## 🔧 Установка зависимостей

```bash
# Активируйте виртуальное окружение проекта
cd ../../backend_lg
source .venv/bin/activate  # Linux/Mac
# или
.venv\Scripts\Activate.ps1  # Windows

# Установите необходимые пакеты
pip install langfuse matplotlib plotly pandas
```

---

## 🚀 Быстрый пример

```bash
# 1. Перейдите в директорию скриптов
cd /path/to/chrome-lg/Metrics/scripts

# 2. Соберите и экспортируйте метрики
python analyze_langfuse_metrics.py --export-json --export-txt

# 3. Создайте визуализации
python visualize_langfuse_metrics.py

# 4. Откройте результаты
firefox ../charts/metrics_dashboard.html
cat ../charts/summary.txt
```

---

## 🎯 Использование из корня проекта

Для удобства созданы wrapper скрипты в корне проекта:

```bash
cd /path/to/chrome-lg

# Анализ
./analyze_metrics.sh --export-json --export-txt

# Визуализация
./visualize_metrics.sh
```

---

## 📊 Примеры output

### Консольный вывод (analyze_langfuse_metrics.py):
```
📊 Analyzing Langfuse metrics (last 7 days, limit=100)...
============================================================
Fetching traces from Langfuse...
Found 22 traces

⏱️  LATENCY ANALYSIS
----------------------------------------
  gemini_generate    | avg: 3500.00ms | p95: 4200.00ms | count: 15
  rag_retrieve       | avg: 450.00ms  | p95: 580.00ms  | count: 3

🔢 TOKEN USAGE ANALYSIS
----------------------------------------
  Average tokens per request:
    Input:  4500 tokens
    Output: 350 tokens
    Total:  4850 tokens

  Estimated cost per request: $0.000055
```

### HTML Dashboard (visualize_langfuse_metrics.py):
Интерактивные графики с возможностью zoom, hover, filtering.

---

## 🐛 Troubleshooting

**Проблема:** `401 Unauthorized`
```bash
# Проверьте .env.local в корне проекта
cat ../../.env.local | grep LANGFUSE
```

**Проблема:** `ModuleNotFoundError: No module named 'langfuse'`
```bash
# Активируйте venv и установите зависимости
cd ../../backend_lg
source .venv/bin/activate
pip install langfuse matplotlib plotly pandas
```

**Проблема:** "No traces found"
```bash
# Используйте расширение для генерации traces
# Проверьте, что Langfuse keys корректны
# Проверьте Langfuse dashboard: https://cloud.langfuse.com
```

---

## 📚 Дополнительные ресурсы

- Основная документация: `../README.md`
- Руководство по использованию: `../USAGE.md`
- Настройка Langfuse: `../../LANGFUSE_SETUP.md`




