#!/usr/bin/env python3
"""
Visualize Langfuse metrics from exported JSON files.

Usage:
    python visualize_langfuse_metrics.py [langfuse_metrics.json] [--output-dir charts]

This creates:
    - operation_frequency.png - pie chart of operation types
    - latency_comparison.png - bar chart of latency by operation
    - token_usage.png - bar chart of token usage (input/output)
    - cost_trend.png - line chart of cost over time (if multiple JSON files)
    - metrics_dashboard.html - interactive HTML dashboard

Requirements:
    pip install matplotlib plotly pandas
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️  plotly not installed. HTML dashboard will be skipped.")
    print("   Install with: pip install plotly")

# Parse arguments
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
input_file = os.path.join(script_dir, "data", "langfuse_metrics.json")
output_dir = os.path.join(script_dir, "charts")

if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
    input_file = sys.argv[1]
if "--output-dir" in sys.argv:
    idx = sys.argv.index("--output-dir")
    if idx + 1 < len(sys.argv):
        output_dir = sys.argv[idx + 1]

# Create output directory
Path(output_dir).mkdir(exist_ok=True)

def load_metrics(filepath: str) -> Dict[str, Any]:
    """Load metrics from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)

def create_operation_frequency_chart(data: Dict[str, Any], output_path: str):
    """Create pie chart of operation frequency."""
    ops = data.get("operation_counts", {})
    if not ops:
        print("⚠️  No operation data for frequency chart")
        return
    
    labels = list(ops.keys())
    sizes = list(ops.values())
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8']
    
    plt.figure(figsize=(10, 7))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors[:len(labels)], startangle=90)
    plt.title('Operation Frequency Distribution', fontsize=16, fontweight='bold')
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Created: {output_path}")

def create_latency_chart(data: Dict[str, Any], output_path: str):
    """Create bar chart of latency by operation."""
    latency = data.get("latency", {})
    if not latency:
        print("⚠️  No latency data available")
        return
    
    ops = list(latency.keys())
    avg_times = [latency[op].get("avg", 0) for op in ops]
    p95_times = [latency[op].get("p95", 0) for op in ops]
    
    x = range(len(ops))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar([i - width/2 for i in x], avg_times, width, label='Average', color='#4ECDC4')
    ax.bar([i + width/2 for i in x], p95_times, width, label='P95', color='#FF6B6B')
    
    ax.set_xlabel('Operation', fontsize=12)
    ax.set_ylabel('Latency (ms)', fontsize=12)
    ax.set_title('Latency by Operation (avg vs p95)', fontsize=16, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(ops, rotation=45, ha='right')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Created: {output_path}")

def create_token_usage_chart(data: Dict[str, Any], output_path: str):
    """Create bar chart of token usage."""
    token_usage = data.get("token_usage", {})
    if not token_usage or token_usage.get("avg_total", 0) == 0:
        print("⚠️  No token usage data available")
        return
    
    categories = ['Input', 'Output', 'Total']
    values = [
        token_usage.get("avg_input", 0),
        token_usage.get("avg_output", 0),
        token_usage.get("avg_total", 0)
    ]
    colors = ['#45B7D1', '#FFA07A', '#98D8C8']
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(categories, values, color=colors)
    
    ax.set_ylabel('Tokens', fontsize=12)
    ax.set_title('Average Token Usage per Request', fontsize=16, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    # Add cost estimate
    cost_per_1k_input = 0.00001
    cost_per_1k_output = 0.00003
    est_cost = (values[0] * cost_per_1k_input / 1000) + (values[1] * cost_per_1k_output / 1000)
    ax.text(0.5, 0.95, f'Est. cost/request: ${est_cost:.6f}',
            transform=ax.transAxes, ha='center', va='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
            fontsize=11)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Created: {output_path}")

def create_trace_timeline_chart(data: Dict[str, Any], output_path: str):
    """Create timeline of traces by operation type."""
    traces = data.get("traces", [])
    if not traces:
        print("⚠️  No trace data available")
        return
    
    # Group by operation
    op_traces = {}
    for trace in traces:
        op = trace.get("name", "unknown")
        if op not in op_traces:
            op_traces[op] = []
        try:
            ts = datetime.fromisoformat(trace["timestamp"].replace("+00:00", ""))
            op_traces[op].append(ts)
        except:
            pass
    
    if not op_traces:
        print("⚠️  No valid timestamps in traces")
        return
    
    fig, ax = plt.subplots(figsize=(14, 6))
    colors = {'gemini_generate': '#FF6B6B', 'rag_retrieve': '#4ECDC4', 
              'rag_upsert': '#45B7D1', 'exa_search': '#FFA07A'}
    
    y_pos = 0
    for op, timestamps in sorted(op_traces.items()):
        ax.scatter(timestamps, [y_pos] * len(timestamps), 
                  label=op, color=colors.get(op, '#999999'), s=100, alpha=0.6)
        y_pos += 1
    
    ax.set_yticks(range(len(op_traces)))
    ax.set_yticklabels(list(op_traces.keys()))
    ax.set_xlabel('Time', fontsize=12)
    ax.set_title('Trace Timeline by Operation', fontsize=16, fontweight='bold')
    ax.legend(loc='upper right')
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Created: {output_path}")

def create_interactive_dashboard(data: Dict[str, Any], output_path: str):
    """Create interactive HTML dashboard with Plotly."""
    if not PLOTLY_AVAILABLE:
        return
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Operation Frequency', 'Token Usage', 
                       'Latency (if available)', 'Trace Count Over Time'),
        specs=[[{"type": "pie"}, {"type": "bar"}],
               [{"type": "bar"}, {"type": "scatter"}]]
    )
    
    # 1. Operation Frequency (Pie)
    ops = data.get("operation_counts", {})
    if ops:
        fig.add_trace(
            go.Pie(labels=list(ops.keys()), values=list(ops.values()), 
                  marker=dict(colors=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A'])),
            row=1, col=1
        )
    
    # 2. Token Usage (Bar)
    token_usage = data.get("token_usage", {})
    if token_usage.get("avg_total", 0) > 0:
        fig.add_trace(
            go.Bar(x=['Input', 'Output', 'Total'],
                  y=[token_usage.get("avg_input", 0), 
                     token_usage.get("avg_output", 0),
                     token_usage.get("avg_total", 0)],
                  marker=dict(color=['#45B7D1', '#FFA07A', '#98D8C8'])),
            row=1, col=2
        )
    
    # 3. Latency (Bar) - if available
    latency = data.get("latency", {})
    if latency:
        ops_lat = list(latency.keys())
        avg_times = [latency[op].get("avg", 0) for op in ops_lat]
        p95_times = [latency[op].get("p95", 0) for op in ops_lat]
        
        fig.add_trace(
            go.Bar(name='Avg', x=ops_lat, y=avg_times, marker=dict(color='#4ECDC4')),
            row=2, col=1
        )
        fig.add_trace(
            go.Bar(name='P95', x=ops_lat, y=p95_times, marker=dict(color='#FF6B6B')),
            row=2, col=1
        )
    
    # 4. Trace count over time
    traces = data.get("traces", [])
    if traces:
        timestamps = []
        for trace in traces:
            try:
                ts = datetime.fromisoformat(trace["timestamp"].replace("+00:00", ""))
                timestamps.append(ts)
            except:
                pass
        
        if timestamps:
            timestamps.sort()
            counts = list(range(1, len(timestamps) + 1))
            fig.add_trace(
                go.Scatter(x=timestamps, y=counts, mode='lines+markers',
                          line=dict(color='#45B7D1', width=2),
                          marker=dict(size=6)),
                row=2, col=2
            )
    
    # Update layout
    fig.update_layout(
        title_text=f"Langfuse Metrics Dashboard<br><sub>Generated: {data.get('timestamp', 'N/A')}</sub>",
        title_font_size=20,
        showlegend=True,
        height=800
    )
    
    fig.write_html(output_path)
    print(f"✅ Created: {output_path}")

def create_summary_report(data: Dict[str, Any], output_path: str):
    """Create text summary report."""
    with open(output_path, 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("LANGFUSE METRICS SUMMARY\n")
        f.write("=" * 60 + "\n\n")
        
        f.write(f"Report Generated: {data.get('timestamp', 'N/A')}\n")
        f.write(f"Total Traces: {data.get('total_traces', 0)}\n\n")
        
        # Operations
        f.write("OPERATION FREQUENCY:\n")
        f.write("-" * 40 + "\n")
        ops = data.get("operation_counts", {})
        total = sum(ops.values())
        for op, count in sorted(ops.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total * 100) if total > 0 else 0
            f.write(f"  {op:20} {count:4} ({pct:.1f}%)\n")
        f.write("\n")
        
        # Tokens
        token_usage = data.get("token_usage", {})
        if token_usage.get("avg_total", 0) > 0:
            f.write("TOKEN USAGE (avg per request):\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Input:  {token_usage.get('avg_input', 0):.0f} tokens\n")
            f.write(f"  Output: {token_usage.get('avg_output', 0):.0f} tokens\n")
            f.write(f"  Total:  {token_usage.get('avg_total', 0):.0f} tokens\n\n")
            
            cost = (token_usage.get('avg_input', 0) * 0.00001 / 1000) + \
                   (token_usage.get('avg_output', 0) * 0.00003 / 1000)
            f.write(f"  Est. cost/request: ${cost:.6f}\n\n")
        
        # Latency
        latency = data.get("latency", {})
        if latency:
            f.write("LATENCY:\n")
            f.write("-" * 40 + "\n")
            for op, stats in sorted(latency.items()):
                f.write(f"  {op:20} avg: {stats.get('avg', 0):.2f}ms | ")
                f.write(f"p95: {stats.get('p95', 0):.2f}ms\n")
            f.write("\n")
        
        f.write("=" * 60 + "\n")
    
    print(f"✅ Created: {output_path}")

if __name__ == "__main__":
    print(f"\n📊 Visualizing Langfuse Metrics from: {input_file}")
    print(f"📁 Output directory: {output_dir}\n")
    
    try:
        data = load_metrics(input_file)
        
        # Create charts
        create_operation_frequency_chart(data, os.path.join(output_dir, "operation_frequency.png"))
        create_latency_chart(data, os.path.join(output_dir, "latency_comparison.png"))
        create_token_usage_chart(data, os.path.join(output_dir, "token_usage.png"))
        create_trace_timeline_chart(data, os.path.join(output_dir, "trace_timeline.png"))
        create_interactive_dashboard(data, os.path.join(output_dir, "metrics_dashboard.html"))
        create_summary_report(data, os.path.join(output_dir, "summary.txt"))
        
        print(f"\n✅ All visualizations created in: {output_dir}/")
        print(f"\n💡 Next steps:")
        print(f"   1. Open {output_dir}/metrics_dashboard.html in browser for interactive charts")
        print(f"   2. Compare PNG files with previous runs to track trends")
        print(f"   3. Adjust parameters in params.override.json based on insights")
        print(f"   4. Re-run analysis after changes: python analyze_langfuse_metrics.py --export-json")
        print()
        
    except FileNotFoundError:
        print(f"❌ Error: File not found: {input_file}")
        print(f"\nRun this first: python analyze_langfuse_metrics.py --export-json")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

