# Chrome-bot

Расширение Chrome (Manifest V3) + Python FastAPI бэкенд для анализа открытой страницы и поиска контекстной информации через exa.ai.

## Быстрый старт

### 1) Бэкенд (Python)

- Требуется Python 3.10+
- Создать и активировать виртуальное окружение (PowerShell):

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

- Установить зависимости:

```powershell
pip install -r backend/requirements.txt
```

- (Опционально) задать ключ для exa.ai:

```powershell
$env:EXA_API_KEY = "ваш_ключ_exa"
```

- Запустить сервер:

```powershell
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Проверка:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/health
```

### 2) Расширение (Chrome)

- Открыть `chrome://extensions`
- Включить Developer Mode
- "Load unpacked" → выбрать папку проекта (`D:\_project\Chrome-bot`)
- В настройках расширения (Options) указать URL бэкенда (по умолчанию `http://localhost:8000`)

### 3) Использование

- Откройте нужную веб-страницу
- Клик по иконке расширения → откроется правая сайд‑панель
- Панель автоматически подхватит контекст страницы и начнет диалог

## Архитектура

- Расширение (MV3): `manifest.json`, `sidepanel.html/js`, `background.js`, `options.html/js`
- Бэкенд (FastAPI): `backend/app/main.py`, HTTP-эндпоинты `/`, `/health`, `/analyze`, `/chat`

## Переменные окружения

- `GEMINI_API_KEY` — ключ доступа к Gemini (обязателен для чата `/chat`).
- `GEMINI_MODEL` — модель Gemini (по умолчанию `gemini-2.5-pro`). Можно переопределить в `.env.local`.
- `EXA_API_KEY` — ключ доступа к exa.ai (опционально для источников).

Примеры (PowerShell):

```powershell
$env:GEMINI_API_KEY = "ваш_gemini_api_key"
$env:GEMINI_MODEL   = "gemini-2.5-flash"
$env:EXA_API_KEY    = "ваш_exa_api_key"
```

## 📊 Мониторинг и метрики (Langfuse)

Проект интегрирован с [Langfuse](https://langfuse.com) для трассировки, мониторинга и анализа производительности LLM.

> **🚀 Быстрый старт:** См. [`METRICS_QUICKSTART.md`](METRICS_QUICKSTART.md) для гида за 3 минуты!

### Быстрый старт метрик:

```bash
# 1. Анализ метрик
./analyze_metrics.sh --export-json --export-txt

# 2. Визуализация
./visualize_metrics.sh

# 3. Откройте интерактивный dashboard
firefox Metrics/charts/metrics_dashboard.html
```

### Структура каталога Metrics:

- `Metrics/scripts/` — Python скрипты для анализа
- `Metrics/data/` — JSON метрики (экспортируются)
- `Metrics/reports/` — Текстовые отчёты с рекомендациями
- `Metrics/charts/` — Графики и интерактивный HTML dashboard

**Подробнее:** 
- 🚀 [`METRICS_QUICKSTART.md`](METRICS_QUICKSTART.md) - гид за 3 минуты
- 📋 [`METRICS_CHEATSHEET.txt`](METRICS_CHEATSHEET.txt) - шпаргалка команд
- 📚 [`Metrics/README.md`](Metrics/README.md) - полная документация
- 💡 [`Metrics/USAGE.md`](Metrics/USAGE.md) - примеры workflow

### Настройка Langfuse:

1. Создайте `.env.local` в корне проекта:
```bash
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

2. Установите зависимости (если ещё не установлены):
```bash
pip install langfuse matplotlib plotly pandas
```

**Детали:** См. [`LANGFUSE_SETUP.md`](LANGFUSE_SETUP.md)
