### Первый запуск (настройка окружения)
```powershell
# 1) Перейти в бэкенд
cd D:\_project\Chrome-lg\backend_lg

# 2) Создать и активировать venv (один раз)
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# в linux:
```
source .venv/bin/activate
```

# 3) Установить зависимости (один раз; при обновлении - повторить)
```
pip install -r .\requirements.txt

```
#linux (строго в каталоге backend_lg)

```
pip install -r ./requirements.txt
```
### Переменные среды (на текущую сессию PowerShell)
```powershell
# Ключи
$env:GEMINI_API_KEY="ВАШ_GEMINI_API_KEY"
$env:EXA_API_KEY="ВАШ_EXA_API_KEY"

# Стриминг ответа
$env:STREAMING_ENABLED="1"

# Визуализация графа (mermaid будет доступен по /graph)
$env:LANGGRAPH_VIZ="1"
$env:LANGGRAPH_VIZ_PATH="D:\_project\Chrome-lg\graph.svg"

# (опционально) Гарантированно отключить кэш EXA
$env:EXA_CACHE_DISABLED="1"
```

### Старт сервера
```powershell
# (из папки D:\_project\Chrome-lg\backend_lg, venv активирован)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010

```
# для запуска в linux

```
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```


### Быстрые проверки
```powershell
# Здоровье/конфиги
Invoke-RestMethod -Uri http://127.0.0.1:8010/debug/health

# Визуализация графа (мермейд-текст; вставьте в mermaid.live)
Invoke-WebRequest -Uri http://127.0.0.1:8010/graph -OutFile D:\_project\Chrome-lg\graph.mmd
```

### Ежедневный запуск (краткая версия)
```powershell
cd D:\_project\Chrome-lg\backend_lg
.\.venv\Scripts\Activate.ps1

# В этой же сессии:
$env:GEMINI_API_KEY="ВАШ_GEMINI_API_KEY"
$env:EXA_API_KEY="ВАШ_EXA_API_KEY"
$env:STREAMING_ENABLED="1"
$env:LANGGRAPH_VIZ="1"
$env:LANGGRAPH_VIZ_PATH="D:\_project\Chrome-lg\graph.svg"
$env:EXA_CACHE_DISABLED="1"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

- Для визуального контроля графа откройте `http://127.0.0.1:8010/graph` и при необходимости вставьте текст в Mermaid Live Editor (`https://mermaid.live`).
