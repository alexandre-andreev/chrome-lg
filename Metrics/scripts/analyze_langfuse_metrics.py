#!/usr/bin/env python3
"""
Анализ метрик Langfuse и рекомендации по оптимизации параметров.

Использование:
    python analyze_langfuse_metrics.py [--export-json] [--export-txt] [--limit N]

Опции:
    --export-json    Экспорт метрик в langfuse_metrics.json
    --export-txt     Экспорт отчёта в langfuse_report.txt
    --limit N        Получить N трассировок (по умолчанию: 100, макс: 100)

Требования:
    - LANGFUSE_PUBLIC_KEY и LANGFUSE_SECRET_KEY в .env.local
"""

import os
import sys
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, List
from dotenv import load_dotenv

# Загрузка переменных окружения - пробуем несколько путей
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
env_paths = [
    os.path.join(project_root, '.env.local'),
    os.path.join(script_dir, '.env.local'),
    '.env.local'
]
for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
        break

try:
    from langfuse import Langfuse
except ImportError:
    print("❌ langfuse не установлен. Выполните: pip install langfuse")
    sys.exit(1)

# Разбор аргументов командной строки
EXPORT_JSON = "--export-json" in sys.argv
EXPORT_TXT = "--export-txt" in sys.argv
LIMIT = 100  # Максимум Langfuse API
for i, arg in enumerate(sys.argv):
    if arg == "--limit" and i + 1 < len(sys.argv):
        try:
            LIMIT = min(int(sys.argv[i + 1]), 100)  # Ограничение 100
        except ValueError:
            pass

# Инициализация Langfuse
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
)

def analyze_metrics(days=7):
    """Анализирует метрики Langfuse за последние N дней."""
    
    output_lines = []
    def log(msg=""):
        print(msg)
        output_lines.append(msg)
    
    log(f"\n📊 Анализ метрик Langfuse (последние {days} дней, лимит={LIMIT})...")
    log("=" * 60)
    
    # Получение трассировок
    log("Загрузка трассировок из Langfuse...")
    traces = langfuse.fetch_traces(limit=LIMIT)
    
    if not traces.data:
        log("❌ Трассировки не найдены. Убедитесь, что в Langfuse есть данные.")
        return output_lines, {}
    
    log(f"Найдено {len(traces.data)} трассировок\n")
    
    # Агрегация метрик
    latencies = defaultdict(list)
    token_usage = {"input": [], "output": [], "total": []}
    operation_counts = defaultdict(int)
    trace_details = []
    
    for trace in traces.data:
        trace_info = {
            "id": getattr(trace, 'id', None),
            "name": getattr(trace, 'name', "unknown"),
            "timestamp": str(getattr(trace, 'timestamp', None)),
            "latency": None,
            "tokens": {},
            "metadata": getattr(trace, 'metadata', {})
        }
        
        if hasattr(trace, 'name'):
            operation_counts[trace.name] += 1
        
        if hasattr(trace, 'latency') and trace.latency:
            latencies[trace.name or "unknown"].append(trace.latency)
            trace_info["latency"] = trace.latency
        
        if hasattr(trace, 'usage') and trace.usage:
            if hasattr(trace.usage, 'input'):
                inp = trace.usage.input or 0
                token_usage["input"].append(inp)
                trace_info["tokens"]["input"] = inp
            if hasattr(trace.usage, 'output'):
                out = trace.usage.output or 0
                token_usage["output"].append(out)
                trace_info["tokens"]["output"] = out
            if hasattr(trace.usage, 'total'):
                tot = trace.usage.total or 0
                token_usage["total"].append(tot)
                trace_info["tokens"]["total"] = tot
        
        trace_details.append(trace_info)
    
    # === АНАЛИЗ LATENCY ===
    log("\n⏱️  АНАЛИЗ ЗАДЕРЖКИ (LATENCY)")
    log("-" * 60)
    
    if latencies:
        for op, times in sorted(latencies.items()):
            if times:
                avg = sum(times) / len(times)
                p95 = sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0]
                log(f"  {op:20} | среднее: {avg:.2f}мс | p95: {p95:.2f}мс | кол-во: {len(times)}")
        
        # Рекомендации
        log("\n💡 Рекомендации по latency:")
        for op, times in latencies.items():
            avg = sum(times) / len(times)
            if op == "gemini_generate" and avg > 5000:
                log(f"  ⚠️  {op} медленный ({avg:.0f}мс). Рассмотрите:")
                log(f"     - Уменьшите LG_PROMPT_TEXT_CHARS (текущее рек.: 8000-10000)")
                log(f"     - Уменьшите LG_NOTES_SHOW_MAX (текущее рек.: 6-8)")
                log(f"     - Используйте GEMINI_MODEL=gemini-2.5-flash-lite")
            elif op == "rag_retrieve" and avg > 1000:
                log(f"  ⚠️  {op} медленный ({avg:.0f}мс). Рассмотрите:")
                log(f"     - Уменьшите RAG_TOP_K (текущее: 8, попробуйте 5-6)")
                log(f"     - Проверьте размер RAG_INDEX_DIR (много старых данных?)")
            elif op == "exa_search" and avg > 4000:
                log(f"  ⚠️  {op} медленный ({avg:.0f}мс). Рассмотрите:")
                log(f"     - Уменьшите EXA_NUM_RESULTS (рек.: 4-6)")
                log(f"     - Уменьшите EXA_GET_CONTENTS_N (рек.: 2)")
                log(f"     - Уменьшите LG_EXA_TIME_BUDGET_S (рек.: 3.0-4.0)")
                log(f"     - Установите EXA_RESEARCH_ENABLED=0 (если включен)")
    else:
        log("  Данные о latency недоступны (трассировки могут не содержать latency)")
    
    # === АНАЛИЗ ИСПОЛЬЗОВАНИЯ ТОКЕНОВ ===
    log("\n🔢 АНАЛИЗ ИСПОЛЬЗОВАНИЯ ТОКЕНОВ")
    log("-" * 60)
    
    if token_usage["total"]:
        avg_input = sum(token_usage["input"]) / len(token_usage["input"]) if token_usage["input"] else 0
        avg_output = sum(token_usage["output"]) / len(token_usage["output"]) if token_usage["output"] else 0
        avg_total = sum(token_usage["total"]) / len(token_usage["total"]) if token_usage["total"] else 0
        
        log(f"  Среднее количество токенов на запрос:")
        log(f"    Входные:  {avg_input:.0f} токенов")
        log(f"    Выходные: {avg_output:.0f} токенов")
        log(f"    Всего:    {avg_total:.0f} токенов")
        
        # Оценка стоимости (для gemini-2.5-flash-lite)
        cost_per_1k_input = 0.00001  # $0.01 за 1M токенов
        cost_per_1k_output = 0.00003  # $0.03 за 1M токенов
        est_cost = (avg_input * cost_per_1k_input / 1000) + (avg_output * cost_per_1k_output / 1000)
        log(f"\n  Примерная стоимость за запрос: ${est_cost:.6f}")
        
        # Рекомендации
        log("\n💡 Рекомендации по токенам:")
        if avg_input > 8000:
            log(f"  ⚠️  Высокое количество входных токенов ({avg_input:.0f}). Рассмотрите:")
            log(f"     - Уменьшите LG_PROMPT_TEXT_CHARS (текущее рек.: 8000-10000)")
            log(f"     - Уменьшите LG_NOTES_SHOW_MAX (текущее рек.: 6-8)")
            log(f"     - Увеличьте RAG_TOP_K для замены сырого текста (рек.: 10-12)")
            log(f"     - Уменьшите LG_SEARCH_SNIPPET_CHARS (текущее рек.: 400-500)")
        if avg_output > 1000:
            log(f"  ⚠️  Высокое количество выходных токенов ({avg_output:.0f}). Рассмотрите:")
            log(f"     - Установите LG_ANSWER_MAX_SENTENCES=7 (ограничить длину)")
            log(f"     - Скорректируйте системный промпт для краткости")
        if avg_input > 0 and avg_input < 2000:
            log(f"  ℹ️  Низкое количество входных токенов ({avg_input:.0f}).")
            log(f"     Можно увеличить качество ответов:")
            log(f"     - Увеличьте LG_PROMPT_TEXT_CHARS (рек.: 12000-15000)")
            log(f"     - Увеличьте LG_NOTES_SHOW_MAX (рек.: 10-12)")
            log(f"     - Увеличьте LG_SEARCH_RESULTS_MAX (рек.: 4-5)")
    else:
        log("  Данные об использовании токенов недоступны")
    
    # === ЧАСТОТА ОПЕРАЦИЙ ===
    log("\n📈 ЧАСТОТА ОПЕРАЦИЙ")
    log("-" * 60)
    
    if operation_counts:
        total_ops = sum(operation_counts.values())
        for op, count in sorted(operation_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_ops) * 100 if total_ops > 0 else 0
            log(f"  {op:20} | {count:4} раз ({pct:.1f}%)")
        
        # Рекомендации
        log("\n💡 Рекомендации по частоте:")
        rag_ops = operation_counts.get("rag_retrieve", 0) + operation_counts.get("rag_upsert", 0)
        search_ops = operation_counts.get("exa_search", 0)
        gemini_ops = operation_counts.get("gemini_generate", 0)
        
        if search_ops > rag_ops * 0.5:
            log(f"  ⚠️  Высокое использование поиска ({search_ops} vs {rag_ops} RAG). Рассмотрите:")
            log(f"     - Увеличьте RAG_TOP_K (текущее рекомендуемое: 12-15)")
            log(f"     - Убедитесь что RAG_ENABLED=1 (включен)")
            log(f"     - Увеличьте LG_SEARCH_MIN_CONTEXT_CHARS (реже запускать поиск)")
            log(f"     - Установите LG_SEARCH_HEURISTICS=0 (отключить эвристики поиска)")
        
        if rag_ops < gemini_ops * 0.2:
            log(f"  ⚠️  Низкое использование RAG ({rag_ops} vs {gemini_ops} Gemini). Проверьте:")
            log(f"     - RAG_ENABLED=1 (должен быть включен)")
            log(f"     - RAG_TOP_K >= 8 (минимум для эффективной работы)")
            log(f"     - RAG_INDEX_DIR корректно настроен")
        
        if search_ops == 0 and gemini_ops > 10:
            log(f"  ℹ️  Поиск Exa не используется. Это нормально если:")
            log(f"     - LG_SEARCH_HEURISTICS=0 (эвристики отключены)")
            log(f"     - LG_SEARCH_MIN_CONTEXT_CHARS > длина контекста страниц")
            log(f"     - Пользователи не задают вопросы требующие внешнего поиска")
    else:
        log("  Данные об операциях недоступны")
    
    # === ИТОГИ ===
    log("\n" + "=" * 60)
    log("📋 ИТОГИ И ДЕЙСТВИЯ")
    log("=" * 60)
    log("\nРекомендуемые изменения параметров:")
    log("  1. Проверьте params.override.json и скорректируйте на основе анализа выше")
    log("  2. Используйте endpoint /config для горячей перезагрузки параметров без перезапуска")
    log("  3. Запустите этот скрипт снова после изменений для сравнения метрик")
    log("\nСледующие шаги:")
    log("  - Настройте Langfuse Datasets для регрессионного тестирования")
    log("  - Настройте пользовательские оценки в Langfuse для метрик качества")
    log("  - Создайте дашборды в Langfuse для мониторинга в реальном времени")
    log("")
    
    # Подготовка данных для экспорта
    export_data = {
        "timestamp": datetime.now().isoformat(),
        "total_traces": len(traces.data),
        "latency": {op: {
            "avg": sum(times) / len(times) if times else 0,
            "p95": sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else (times[0] if times else 0),
            "count": len(times)
        } for op, times in latencies.items()},
        "token_usage": {
            "avg_input": sum(token_usage["input"]) / len(token_usage["input"]) if token_usage["input"] else 0,
            "avg_output": sum(token_usage["output"]) / len(token_usage["output"]) if token_usage["output"] else 0,
            "avg_total": sum(token_usage["total"]) / len(token_usage["total"]) if token_usage["total"] else 0,
        },
        "operation_counts": dict(operation_counts),
        "traces": trace_details
    }
    
    return output_lines, export_data

if __name__ == "__main__":
    try:
        output_lines, export_data = analyze_metrics(days=7)
        
        # Определить пути вывода относительно каталога Metrics
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(script_dir, "data")
        reports_dir = os.path.join(script_dir, "reports")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(reports_dir, exist_ok=True)
        
        # Экспорт в TXT
        if EXPORT_TXT:
            txt_file = os.path.join(reports_dir, "langfuse_report.txt")
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write("\n".join(output_lines))
            print(f"✅ Отчёт экспортирован в: {txt_file}")
        
        # Экспорт в JSON
        if EXPORT_JSON:
            json_file = os.path.join(data_dir, "langfuse_metrics.json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Метрики экспортированы в: {json_file}")
        
        if EXPORT_TXT or EXPORT_JSON:
            print(f"\n💡 Используйте эти файлы для:")
            print(f"   - Сравнения метрик между разными конфигурациями параметров")
            print(f"   - Создания пользовательских визуализаций (например, с matplotlib/plotly)")
            print(f"   - Отслеживания трендов производительности во времени")
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        print("\nУбедитесь что:")
        print("  1. LANGFUSE_PUBLIC_KEY и LANGFUSE_SECRET_KEY установлены в .env.local")
        print("  2. У вас есть трассировки в Langfuse (выполните несколько запросов)")
        sys.exit(1)
