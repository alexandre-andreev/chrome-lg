# Metrics System - Changelog

## 2025-10-01 - Initial Release

### ✨ Новые возможности

#### Скрипты анализа
- **`analyze_langfuse_metrics.py`** - анализ traces из Langfuse
  - Извлечение до 100 traces за запрос
  - Анализ latency, token usage, частоты операций
  - Автоматические рекомендации по оптимизации
  - Экспорт в JSON и TXT форматы
  - Поддержка множественных путей к `.env.local`

#### Скрипты визуализации
- **`visualize_langfuse_metrics.py`** - визуализация метрик
  - Круговые диаграммы (operation frequency)
  - Bar charts (latency, token usage)
  - Timeline графики (trace распределение)
  - Интерактивный HTML dashboard (Plotly)
  - Статические PNG для документации

#### Wrapper скрипты
- **`analyze_metrics.sh`** - удобный запуск анализа из корня проекта
- **`visualize_metrics.sh`** - удобный запуск визуализации из корня проекта

#### Структура каталогов
```
Metrics/
├── scripts/        # Исполняемые Python скрипты
├── data/          # JSON метрики (экспорт)
├── reports/       # Текстовые отчёты
├── charts/        # Визуализации (PNG + HTML)
└── snapshots/     # Исторические данные
```

#### Документация
- **`README.md`** - полная документация системы метрик
- **`USAGE.md`** - быстрые примеры и workflow
- **`scripts/README.md`** - детали скриптов
- **`CHANGELOG.md`** - история изменений (этот файл)
- Обновлён корневой **`../README.md`** с секцией Metrics

#### Git интеграция
- **`.gitignore`** для исключения генерируемых файлов
- `.gitkeep` файлы для сохранения структуры каталогов
- Snapshot поддержка для исторических сравнений

### 🔧 Технические детали

#### Зависимости
- `langfuse>=2.0,<3.0` - API клиент
- `matplotlib` - статические графики
- `plotly` - интерактивные визуализации
- `pandas` - обработка данных (опционально)

#### Возможности экспорта
- **JSON**: структурированные метрики для программной обработки
- **TXT**: человекочитаемые отчёты с рекомендациями
- **PNG**: статические графики для документации
- **HTML**: интерактивный dashboard для детального анализа

#### Поддерживаемые метрики
- ⏱️ Latency (avg, p95) по операциям
- 🔢 Token usage (input, output, total)
- 📊 Operation frequency (counts, percentages)
- 💰 Cost estimation (Gemini pricing)
- 📅 Temporal distribution (timeline)

### 🎯 Use Cases

1. **A/B тестирование параметров**
   - Baseline vs Experiment сравнение
   - Исторические snapshots
   - Diff анализ

2. **Оптимизация производительности**
   - Latency bottleneck выявление
   - Token usage оптимизация
   - Cost reduction рекомендации

3. **Мониторинг качества**
   - Operation balance (RAG vs Search)
   - Response length контроль
   - Error rate tracking (будущая фича)

4. **Документация и отчётность**
   - Статические графики для презентаций
   - Экспорт данных для внешних систем
   - Исторические тренды

### 📝 Примечания

- Langfuse API ограничивает до 100 traces за запрос
- Latency данные могут быть недоступны в Langfuse 2.x через API
- Token usage логируется только для Gemini generations
- Для большего количества traces используйте Langfuse UI

### 🔜 Планы на будущее

- [ ] Сравнение нескольких JSON файлов в одном скрипте
- [ ] Автоматический trending анализ (week-over-week)
- [ ] Экспорт в PDF для отчётов
- [ ] Интеграция с CI/CD для regression тестирования
- [ ] Email уведомления при деградации метрик
- [ ] Prometheus/Grafana экспорт
- [ ] Custom scoring metrics из Langfuse

---

## Авторы

Создано для проекта **Chrome-bot** (LangGraph + Langfuse)




