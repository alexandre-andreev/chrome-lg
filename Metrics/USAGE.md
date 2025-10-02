# Metrics Analysis - Quick Start Guide

## 🚀 Быстрое использование

### Из корня проекта (рекомендуется):

```bash
# 1. Анализ и экспорт метрик
./analyze_metrics.sh --export-json --export-txt

# 2. Визуализация
./visualize_metrics.sh
```

### Из каталога Metrics:

```bash
cd Metrics

# 1. Анализ и экспорт
python scripts/analyze_langfuse_metrics.py --export-json --export-txt

# 2. Визуализация
python scripts/visualize_langfuse_metrics.py
```

## 📁 Структура каталогов

```
Metrics/
├── scripts/                    # Исполняемые скрипты
│   ├── analyze_langfuse_metrics.py
│   └── visualize_langfuse_metrics.py
├── data/                       # JSON метрики (экспорт)
│   └── langfuse_metrics.json
├── reports/                    # Текстовые отчёты
│   └── langfuse_report.txt
├── charts/                     # Графики и визуализации
│   ├── operation_frequency.png
│   ├── latency_comparison.png
│   ├── token_usage.png
│   ├── trace_timeline.png
│   ├── metrics_dashboard.html  # ← Откройте в браузере!
│   └── summary.txt
└── README.md                   # Полная документация
```

## 🔄 Типичный workflow

### 1. Накопите данные
```bash
# Используйте расширение для 20-50 запросов на разных сайтах
# Langfuse автоматически собирает traces
```

### 2. Экспортируйте и визуализируйте
```bash
# Из корня проекта
./analyze_metrics.sh --export-json --export-txt
./visualize_metrics.sh

# Откройте dashboard
firefox Metrics/charts/metrics_dashboard.html
```

### 3. Анализируйте результаты
```bash
# Текстовая сводка
cat Metrics/charts/summary.txt

# Или детальный отчёт
cat Metrics/reports/langfuse_report.txt

# Или откройте графики
eog Metrics/charts/*.png
```

### 4. Оптимизируйте параметры
```bash
# Редактируйте params.override.json на основе рекомендаций
# Перезагрузите через /config или перезапустите сервер

# Повторите шаг 1-3 для сравнения
```

## 📊 Примеры команд

### Сохранить baseline метрики
```bash
./analyze_metrics.sh --export-json
cp Metrics/data/langfuse_metrics.json Metrics/data/baseline_$(date +%Y%m%d).json
./visualize_metrics.sh Metrics/data/baseline_$(date +%Y%m%d).json Metrics/charts/baseline
```

### Сравнить с новыми параметрами
```bash
# После изменения params.override.json и 20+ запросов:
./analyze_metrics.sh --export-json
cp Metrics/data/langfuse_metrics.json Metrics/data/experiment_$(date +%Y%m%d).json
./visualize_metrics.sh Metrics/data/experiment_$(date +%Y%m%d).json Metrics/charts/experiment

# Сравните:
diff Metrics/charts/baseline/summary.txt Metrics/charts/experiment/summary.txt
```

### Экспорт для документации
```bash
# Создайте snapshot всех метрик
SNAPSHOT_DIR="Metrics/snapshots/$(date +%Y%m%d_%H%M)"
mkdir -p "$SNAPSHOT_DIR"
cp Metrics/data/langfuse_metrics.json "$SNAPSHOT_DIR/"
cp Metrics/reports/langfuse_report.txt "$SNAPSHOT_DIR/"
cp Metrics/charts/*.png "$SNAPSHOT_DIR/"
echo "📸 Snapshot saved to: $SNAPSHOT_DIR"
```

## 🎯 Рекомендации

1. **Регулярность**: Экспортируйте метрики 1-2 раза в неделю
2. **Сохранение**: Держите исторические JSON для трендов
3. **A/B тестирование**: Всегда сравнивайте с baseline
4. **Документация**: Добавляйте комментарии в `params.override.json`

## 🔍 Troubleshooting

**Проблема**: "File not found: langfuse_metrics.json"
```bash
# Решение: Сначала запустите анализ
./analyze_metrics.sh --export-json
```

**Проблема**: "No traces found"
```bash
# Решение: Сделайте запросы через расширение
# Проверьте, что Langfuse включён (.env.local)
```

**Проблема**: Пустые графики
```bash
# Решение: Нужно больше данных (минимум 10-20 traces)
# Используйте расширение на разных сайтах
```

## 📚 Дополнительная информация

- Полная документация: `Metrics/README.md`
- Настройка Langfuse: `../LANGFUSE_SETUP.md`
- Параметры конфигурации: `../params.override.json`



