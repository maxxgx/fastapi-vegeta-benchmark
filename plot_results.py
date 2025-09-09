#!/usr/bin/env python3
"""Plot benchmark results for the benchmark app with interactive HTML charts."""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
import argparse

def find_latest_benchmark_dir() -> Path:
    """Find the latest benchmark directory."""
    tmp_dir = Path(".tmp")
    if not tmp_dir.exists():
        raise FileNotFoundError("No .tmp directory found")
    
    # Look for both old and new directory patterns
    benchmark_dirs = list(tmp_dir.glob("bench_*")) + list(tmp_dir.glob("fast_cpu_bench_*"))
    if not benchmark_dirs:
        raise FileNotFoundError("No benchmark directories found")
    
    # Sort by modification time, newest first
    latest_dir = max(benchmark_dirs, key=lambda p: p.stat().st_mtime)
    return latest_dir

def load_benchmark_data(results_dir: Path) -> Dict[str, Any]:
    """Load benchmark data from the consolidated results file."""
    results_file = results_dir / "fast_cpu_results.json"
    
    if not results_file.exists():
        raise FileNotFoundError(f"No fast_cpu_results.json found in {results_dir}")
    
    with open(results_file) as f:
        data = json.load(f)
    
    # Handle both old and new data formats
    if "metadata" in data and "results" in data:
        # New format with metadata
        return data
    else:
        # Old format - wrap in new structure
        return {
            "metadata": {
                "workers": 1,  # Default for old data
                "host": "127.0.0.1",
                "port": 8000,
                "duration": 10,
                "timestamp": "unknown"
            },
            "results": data
        }

def load_cpu_data(results_dir: Path) -> List[Dict[str, Any]]:
    """Load CPU monitoring data from individual CPU files."""
    cpu_data = []
    
    for json_file in results_dir.glob("*_cpu.json"):
        match = re.match(r'(\w+)_(\d+)_cpu\.json', json_file.name)
        if not match:
            continue
            
        endpoint, rate = match.groups()
        rate = int(rate)
        
        try:
            with open(json_file) as f:
                cpu_samples = json.load(f)
            
            if cpu_samples:
                avg_cpu = sum(s['cpu_percent'] for s in cpu_samples) / len(cpu_samples)
                max_cpu = max(s['cpu_percent'] for s in cpu_samples)
                avg_memory = sum(s['rss_mb'] for s in cpu_samples) / len(cpu_samples)
                max_memory = max(s['rss_mb'] for s in cpu_samples)
                
                cpu_data.append({
                    'endpoint': endpoint,
                    'rate': rate,
                    'avg_cpu': avg_cpu,
                    'max_cpu': max_cpu,
                    'avg_memory_mb': avg_memory,
                    'max_memory_mb': max_memory,
                    'samples': len(cpu_samples)
                })
        except Exception as e:
            print(f"⚠️ Error loading CPU data from {json_file}: {e}")
    
    return cpu_data

def print_ascii_chart(data: List[Dict], title: str, group_key: str, value_key: str, max_width: int = 60):
    """Print ASCII chart."""
    if not data:
        return
    
    print(f"\n📊 {title}")
    print("=" * 80)
    
    # Group data by the group_key
    groups = {}
    for item in data:
        group = item[group_key]
        if group not in groups:
            groups[group] = []
        groups[group].append(item)
    
    # Find max value for scaling
    max_value = max(item[value_key] for item in data) if data else 1
    
    # Sort by rate for consistent display
    for group in sorted(groups.keys()):
        group_items = sorted(groups[group], key=lambda x: x['rate'])
        for item in group_items:
            value = item[value_key]
            rate = item['rate']
            endpoint = item['endpoint']
            
            # Create bar
            bar_length = int((value / max_value) * max_width) if max_value > 0 else 0
            bar = '█' * bar_length + '░' * (max_width - bar_length)

            name = f"{endpoint}@{rate}RPS"
            print(f"{name:<35} {bar} {value:.1f}")

def print_table(data: List[Dict], title: str, columns: List[Dict]):
    """Print formatted table."""
    print(f"\n📋 {title}")
    print("=" * 100)
    
    # Print header
    header = " | ".join(f"{col['name']:<{col['width']}}" for col in columns)
    print(header)
    print("-" * len(header))
    
    # Print rows
    for item in data:
        row_parts = []
        for col in columns:
            value = item.get(col['key'], 0)
            if col['key'] == 'success_rate':
                value = f"{value * 100:.1f}%"
            elif isinstance(value, float):
                value = f"{value:.{col['precision']}f}"
            else:
                value = str(value)
            row_parts.append(f"{value:<{col['width']}}")
        
        print(" | ".join(row_parts))

def create_html_chart(data: List[Dict], title: str, x_key: str, y_key: str, 
                     group_key: str = None, chart_type: str = "line") -> str:
    """Create Chart.js HTML chart."""
    if not data:
        return ""
    
    # Prepare data for Chart.js
    if group_key:
        # Group by group_key (e.g., endpoint)
        groups = {}
        for item in data:
            group = item[group_key]
            if group not in groups:
                groups[group] = []
            groups[group].append(item)
        
        datasets = []
        colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40']
        
        for i, (group, items) in enumerate(groups.items()):
            items = sorted(items, key=lambda x: x[x_key])
            # Format data as separate x and y arrays for Chart.js
            x_values = [item[x_key] for item in items]
            y_values = [item[y_key] for item in items]
            datasets.append({
                'label': group,
                'data': list(zip(x_values, y_values)),
                'borderColor': colors[i % len(colors)],
                'backgroundColor': colors[i % len(colors)] + '20',
                'tension': 0.1
            })
    else:
        # Single dataset
        items = sorted(data, key=lambda x: x[x_key])
        x_values = [item[x_key] for item in items]
        y_values = [item[y_key] for item in items]
        datasets = [{
            'label': title,
            'data': list(zip(x_values, y_values)),
            'borderColor': '#36A2EB',
            'backgroundColor': '#36A2EB20',
            'tension': 0.1
        }]
    
    chart_config = {
        'type': chart_type,
        'data': {'datasets': datasets},
        'options': {
            'responsive': True,
            'scales': {
                'x': {
                    'title': {'display': True, 'text': x_key.replace('_', ' ').title()},
                    'type': 'linear'
                },
                'y': {
                    'title': {'display': True, 'text': y_key.replace('_', ' ').title()},
                    'type': 'linear'
                }
            },
            'plugins': {
                'title': {'display': True, 'text': title}
            }
        }
    }
    
    return f"""
    <div style="width: 100%; height: 400px; margin: 20px 0;">
        <canvas id="chart_{hash(title)}"></canvas>
    </div>
    <script>
        new Chart(document.getElementById('chart_{hash(title)}'), {json.dumps(chart_config)});
    </script>
    """

def generate_html_report(benchmark_data: Dict[str, Any], cpu_data: List[Dict], output_file: Path, metadata: Dict[str, Any] = None):
    """Generate comprehensive HTML report with charts."""
    
    # Flatten data for easier processing
    flat_data = []
    for rate, endpoints in benchmark_data.items():
        for endpoint, metrics in endpoints.items():
            flat_data.append({
                'endpoint': endpoint,
                'rate': int(rate),
                'achieved_rps': metrics['achieved_rps'],
                'target_rps': metrics['target_rps'],
                'p50_ms': metrics['p50_ms'],
                'p95_ms': metrics['p95_ms'],
                'p99_ms': metrics['p99_ms'],
                'avg_ms': metrics['avg_ms'],
                'success_rate': metrics['success_rate'],
                'error_rate': metrics['error_rate'],
                'cpu_avg': metrics.get('cpu_avg', 0),
                'cpu_max': metrics.get('cpu_max', 0),
                'memory_avg_mb': metrics.get('memory_avg_mb', 0),
                'memory_max_mb': metrics.get('memory_max_mb', 0)
            })
    
    # Get unique endpoints and rates
    endpoints = sorted(set(item['endpoint'] for item in flat_data))
    rates = sorted(set(item['rate'] for item in flat_data))
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Benchmark Results Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .chart-container {{ margin: 30px 0; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .endpoint {{ margin: 10px 0; padding: 10px; background: #e9ecef; border-radius: 3px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 FastAPI Benchmark Results</h1>
        <p>Generated on {Path().cwd()}</p>
    </div>
    
    <div class="summary">
        <h2>📊 Summary</h2>
        <p><strong>Endpoints tested:</strong> {', '.join(endpoints)}</p>
        <p><strong>Rates tested:</strong> {', '.join(map(str, rates))} RPS</p>
        <p><strong>Total tests:</strong> {len(flat_data)}</p>
        {f'<p><strong>Workers:</strong> {metadata.get("workers", "Unknown")}</p>' if metadata else ''}
        {f'<p><strong>Host:</strong> {metadata.get("host", "Unknown")}:{metadata.get("port", "Unknown")}</p>' if metadata else ''}
        {f'<p><strong>Duration:</strong> {metadata.get("duration", "Unknown")}python per test</p>' if metadata else ''}
        {f'<p><strong>Timestamp:</strong> {metadata.get("timestamp", "Unknown")}</p>' if metadata else ''}
    </div>
    
    <div class="chart-container">
        <h2>📈 Performance Charts</h2>
        {create_html_chart(flat_data, "Achieved RPS vs Target Rate", "rate", "achieved_rps", "endpoint")}
        {create_html_chart(flat_data, "P95 Latency vs Target Rate", "rate", "p95_ms", "endpoint")}
        {create_html_chart(flat_data, "Success Rate vs Target Rate", "rate", "success_rate", "endpoint")}
        {create_html_chart(flat_data, "Average Latency vs Target Rate", "rate", "avg_ms", "endpoint")}
    </div>
    
    <div class="chart-container">
        <h2>💻 Resource Usage Charts</h2>
        {create_html_chart(flat_data, "CPU Usage vs Target Rate", "rate", "cpu_avg", "endpoint")}
        {create_html_chart(flat_data, "Memory Usage vs Target Rate", "rate", "memory_avg_mb", "endpoint")}
    </div>
    
    <div class="chart-container">
        <h2>📋 Detailed Results Table</h2>
        <table>
            <tr>
                <th>Endpoint</th>
                <th>Rate</th>
                <th>Achieved RPS</th>
                <th>P50 (ms)</th>
                <th>Avg (ms)</th>
                <th>P95 (ms)</th>
                <th>Success %</th>
                <th>CPU Avg %</th>
                <th>Memory Avg (MB)</th>
            </tr>
"""
    
    # Add table rows
    for item in sorted(flat_data, key=lambda x: (x['endpoint'], x['rate'])):
        html_content += f"""
            <tr>
                <td>{item['endpoint']}</td>
                <td>{item['rate']}</td>
                <td>{item['achieved_rps']:.1f}</td>
                <td>{item['p50_ms']:.1f}</td>
                <td>{item['avg_ms']:.1f}</td>
                <td>{item['p95_ms']:.1f}</td>
                <td>{item['success_rate']*100:.1f}%</td>
                <td>{item['cpu_avg']:.1f}</td>
                <td>{item['memory_avg_mb']:.1f}</td>
            </tr>
"""
    
    html_content += """
        </table>
    </div>
    
    <div class="summary">
        <h2>🏆 Performance Analysis</h2>
"""
    
    # Add performance analysis
    for endpoint in endpoints:
        endpoint_data = [item for item in flat_data if item['endpoint'] == endpoint]
        max_sustainable = max((item['achieved_rps'] for item in endpoint_data if item['success_rate'] > 0.95), default=0)
        avg_cpu = sum(item['cpu_avg'] for item in endpoint_data) / len(endpoint_data) if endpoint_data else 0
        avg_latency = sum(item['p95_ms'] for item in endpoint_data) / len(endpoint_data) if endpoint_data else 0
        
        html_content += f"""
        <div class="endpoint">
            <h3>{endpoint}</h3>
            <p><strong>Max Sustainable RPS (Success > 95%):</strong> {max_sustainable:.1f}</p>
            <p><strong>Average CPU Usage:</strong> {avg_cpu:.1f}%</p>
            <p><strong>Average P95 Latency:</strong> {avg_latency:.1f}ms</p>
        </div>
"""
    
    html_content += """
    </div>
</body>
</html>
"""
    
    with open(output_file, 'w') as f:
        f.write(html_content)

def main():
    """Main plotting function."""
    parser = argparse.ArgumentParser(description="Plot benchmark results")
    parser.add_argument("--dir", help="Specific benchmark directory to use")
    parser.add_argument("--no-html", action="store_true", help="Skip HTML report generation")
    parser.add_argument("--output", default="benchmark_report.html", help="HTML output filename")
    
    args = parser.parse_args()
    
    try:
        # Find benchmark directory
        if args.dir:
            results_dir = Path(args.dir)
            if not results_dir.exists():
                print(f"❌ Directory {results_dir} does not exist")
                return
        else:
            results_dir = find_latest_benchmark_dir()
        
        print(f"📁 Using data from: {results_dir}")
        
        # Load data
        print("📊 Loading benchmark data...")
        full_data = load_benchmark_data(results_dir)
        cpu_data = load_cpu_data(results_dir)
        
        # Extract metadata and results
        metadata = full_data.get('metadata', {})
        benchmark_data = full_data.get('results', full_data)  # Fallback for old format
        
        if not benchmark_data:
            print("❌ No benchmark data found")
            return
        
        # Flatten data for easier processing
        flat_data = []
        for rate, endpoints in benchmark_data.items():
            for endpoint, metrics in endpoints.items():
                flat_data.append({
                    'endpoint': endpoint,
                    'rate': int(rate),
                    'achieved_rps': metrics['achieved_rps'],
                    'target_rps': metrics['target_rps'],
                    'p50_ms': metrics['p50_ms'],
                    'p95_ms': metrics['p95_ms'],
                    'p99_ms': metrics['p99_ms'],
                    'avg_ms': metrics['avg_ms'],
                    'success_rate': metrics['success_rate'],
                    'error_rate': metrics['error_rate'],
                    'cpu_avg': metrics.get('cpu_avg', 0),
                    'cpu_max': metrics.get('cpu_max', 0),
                    'memory_avg_mb': metrics.get('memory_avg_mb', 0),
                    'memory_max_mb': metrics.get('memory_max_mb', 0)
                })
        
        print(f"✅ Loaded {len(flat_data)} benchmark results")
        print(f"✅ Loaded {len(cpu_data)} CPU monitoring results")
        
        # Get unique endpoints and rates
        endpoints = sorted(set(item['endpoint'] for item in flat_data))
        rates = sorted(set(item['rate'] for item in flat_data))
        
        print(f"\n🎯 Found {len(endpoints)} endpoints: {', '.join(endpoints)}")
        print(f"🎯 Found {len(rates)} rates: {', '.join(map(str, rates))}")
        
        # Print ASCII charts
        print_ascii_chart(flat_data, "Achieved RPS", 'endpoint', 'achieved_rps')
        print_ascii_chart(flat_data, "P50 Latency (ms)", 'endpoint', 'p50_ms')
        print_ascii_chart(flat_data, "Average Latency (ms)", 'endpoint', 'avg_ms')
        print_ascii_chart(flat_data, "P95 Latency (ms)", 'endpoint', 'p95_ms')
        print_ascii_chart(flat_data, "Success Rate", 'endpoint', 'success_rate')
        
        if any(item['cpu_avg'] > 0 for item in flat_data):
            print_ascii_chart(flat_data, "Average CPU %", 'endpoint', 'cpu_avg')
            print_ascii_chart(flat_data, "Average Memory (MB)", 'endpoint', 'memory_avg_mb')
        
        # Print detailed tables
        print_table(flat_data, "Performance Results", [
            {'name': 'Endpoint', 'key': 'endpoint', 'width': 25, 'precision': 0},
            {'name': 'Rate', 'key': 'rate', 'width': 6, 'precision': 0},
            {'name': 'Achieved RPS', 'key': 'achieved_rps', 'width': 12, 'precision': 1},
            {'name': 'P50(ms)', 'key': 'p50_ms', 'width': 8, 'precision': 1},
            {'name': 'Avg(ms)', 'key': 'avg_ms', 'width': 8, 'precision': 1},
            {'name': 'P95(ms)', 'key': 'p95_ms', 'width': 8, 'precision': 1},
            {'name': 'P99(ms)', 'key': 'p99_ms', 'width': 8, 'precision': 1},
            {'name': 'Success%', 'key': 'success_rate', 'width': 8, 'precision': 1},
            {'name': 'CPU Avg%', 'key': 'cpu_avg', 'width': 10, 'precision': 1}
        ])
        
        # Performance analysis
        print("\n" + "="*80)
        print("🏆 PERFORMANCE ANALYSIS")
        print("="*80)
        
        # Find maximum sustainable RPS for each endpoint
        print(f"Maximum Sustainable RPS (Success Rate > 95%):")
        for endpoint in endpoints:
            max_sustainable = 0
            for item in flat_data:
                if item['endpoint'] == endpoint and item['success_rate'] > 0.95:
                    max_sustainable = max(max_sustainable, item['achieved_rps'])
            
            print(f"  {endpoint:<25}: {max_sustainable:.1f} RPS")
        
        # CPU usage analysis
        if any(item['cpu_avg'] > 0 for item in flat_data):
            print(f"\nCPU Usage Analysis:")
            for endpoint in endpoints:
                endpoint_cpu = [item for item in flat_data if item['endpoint'] == endpoint]
                if endpoint_cpu:
                    avg_cpu = sum(item['cpu_avg'] for item in endpoint_cpu) / len(endpoint_cpu)
                    max_cpu = max(item['cpu_max'] for item in endpoint_cpu)
                    print(f"  {endpoint:<25}: {avg_cpu:.1f}% avg, {max_cpu:.1f}% max")
        
        # Latency analysis
        print(f"\nLatency Analysis (P95):")
        for endpoint in endpoints:
            endpoint_latency = [item for item in flat_data if item['endpoint'] == endpoint]
            if endpoint_latency:
                avg_latency = sum(item['p95_ms'] for item in endpoint_latency) / len(endpoint_latency)
                max_latency = max(item['p95_ms'] for item in endpoint_latency)
                print(f"  {endpoint:<25}: {avg_latency:.1f}ms avg, {max_latency:.1f}ms max")
        
        # Generate HTML report (default behavior)
        if not args.no_html:
            output_file = Path(args.output)
            print(f"\n🌐 Generating HTML report: {output_file}")
            generate_html_report(benchmark_data, cpu_data, output_file, metadata)
            print(f"✅ HTML report saved to: {output_file}")

            # Get absolute path for clickable link
            abs_path = output_file.absolute()
            print(f"🔗 Open report: file://{abs_path}")
        else:
            print("\n⏭️  Skipping HTML report generation (--no-html specified)")
        
        print(f"\n🎉 Analysis complete! Data from: {results_dir}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()