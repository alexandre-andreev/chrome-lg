#!/bin/bash
# Wrapper script for Langfuse metrics analysis

cd "$(dirname "$0")"

# Activate virtual environment
if [ -f "backend_lg/.venv/bin/activate" ]; then
    source backend_lg/.venv/bin/activate
fi

python3 Metrics/scripts/analyze_langfuse_metrics.py "$@" && \
echo "" && \
echo "📁 Результаты сохранены в:" && \
echo "   - Metrics/data/langfuse_metrics.json" && \
echo "   - Metrics/reports/langfuse_report.txt"


