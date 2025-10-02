#!/bin/bash
# Wrapper script for Langfuse metrics visualization

cd "$(dirname "$0")"

# Activate virtual environment
if [ -f "backend_lg/.venv/bin/activate" ]; then
    source backend_lg/.venv/bin/activate
fi

# Default paths
INPUT="${1:-Metrics/data/langfuse_metrics.json}"
OUTPUT_DIR="${2:-Metrics/charts}"

python3 Metrics/scripts/visualize_langfuse_metrics.py "$INPUT" --output-dir "$OUTPUT_DIR" && \
echo "" && \
echo "📁 Визуализации сохранены в: $OUTPUT_DIR/" && \
echo "" && \
echo "💡 Откройте dashboard:" && \
echo "   firefox $OUTPUT_DIR/metrics_dashboard.html"


