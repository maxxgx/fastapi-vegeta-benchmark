#!/usr/bin/env python3
"""
Clean Benchmark Script - Restarts server between each test to ensure reliable results.

This version addresses the major flaw where server state from previous tests
affects subsequent test results by restarting the server for each test.
"""

import argparse
import json
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import inspect
import sys
import os
import signal
import atexit
import psutil

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

# Global process tracking for cleanup
active_processes = []
cleanup_done = False

def cleanup_all_processes():
    """Clean up all tracked processes and orphaned Python processes."""
    global cleanup_done, active_processes
    
    if cleanup_done:
        return
    
    cleanup_done = True
    print("\n🧹 Cleaning up processes...")
    
    # Clean up tracked processes
    for proc in active_processes:
        if proc and proc.poll() is None:  # Process is still running
            try:
                print(f"  🛑 Terminating process {proc.pid}")
                proc.terminate()
                proc.wait(timeout=3)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    print(f"  💀 Force killing process {proc.pid}")
                    proc.kill()
                except ProcessLookupError:
                    pass  # Process already dead
    
    # Clean up orphaned Python processes from this project
    try:
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if (proc.info['name'] == 'python' and 
                    proc.info['pid'] != current_pid and
                    any('fastapi_vegeta_benchmark' in str(cmd) for cmd in proc.info['cmdline'])):
                    
                    print(f"  🧹 Cleaning up orphaned process {proc.info['pid']}")
                    proc.terminate()
                    proc.wait(timeout=2)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
    except Exception as e:
        print(f"  ⚠️  Error during orphan cleanup: {e}")
    
    active_processes.clear()
    print("  ✅ Cleanup complete")

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    print(f"\n🛑 Received signal {signum}, cleaning up...")
    cleanup_all_processes()
    sys.exit(0)

def register_cleanup():
    """Register cleanup handlers."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Register cleanup on exit
    atexit.register(cleanup_all_processes)

def wait_for_server(host: str, port: int, timeout: int = 30) -> bool:
    """Wait for server to be ready."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = subprocess.run([
                "curl", "-s", "-f", f"http://{host}:{port}/health"
            ], capture_output=True, timeout=5)
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        time.sleep(1)
    return False

def discover_benchmark_endpoints(path_filter: str = None) -> Dict[str, Dict[str, Any]]:
    """Discover all benchmark endpoints dynamically with optional path filtering."""
    try:
        from app.main import app
        
        endpoints = {}
        for route in app.routes:
            if hasattr(route, 'endpoint') and hasattr(route, 'path'):
                # Skip routes that don't have GET or POST methods and special routes
                if not hasattr(route, 'methods') or not any(method in route.methods for method in ['GET', 'POST']):
                    continue
                if route.path in ['/', '/health', '/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc', '/api/db/seed']:
                    continue
                
                # Apply path filter if provided
                if path_filter:
                    if not route.path.startswith(path_filter):
                        continue
                
                func_name = route.endpoint.__name__
                endpoints[func_name] = {
                    'url': route.path,
                    'method': getattr(route, 'methods', ['GET']),
                    'function': route.endpoint
                }
        
        return endpoints
    except Exception as e:
        print(f"❌ Error discovering endpoints: {e}")
        return {}

def monitor_cpu_fast(pid: int, duration: int, output_file: Path, progress_callback=None) -> None:
    """Monitor CPU usage for a specific process."""
    samples = []
    start_time = time.time()
    
    while time.time() - start_time < duration:
        try:
            # Use different ps command format for macOS
            result = subprocess.run([
                "ps", "-p", str(pid), "-o", "pcpu,rss", "-h", "-r"
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0] != '%CPU':
                        try:
                            cpu_percent = float(parts[0])
                            rss_kb = int(parts[1])
                            rss_mb = rss_kb / 1024
                            
                            samples.append({
                                'timestamp': time.time(),
                                'cpu_percent': cpu_percent,
                                'rss_mb': rss_mb
                            })
                        except ValueError:
                            continue
            
            if progress_callback:
                elapsed = time.time() - start_time
                progress_callback(samples, 20, f"CPU monitoring ({elapsed:.0f}s)")
            
            time.sleep(1)
        except Exception as e:
            print(f"⚠️  CPU monitoring error: {e}")
            break
    
    # Save samples
    with open(output_file, 'w') as f:
        json.dump(samples, f, indent=2)

def analyze_cpu_data(cpu_data: List[Dict]) -> Dict[str, float]:
    """Analyze CPU monitoring data."""
    if not cpu_data:
        return {
            'avg_cpu': 0.0,
            'max_cpu': 0.0,
            'avg_memory_mb': 0.0,
            'max_memory_mb': 0.0
        }
    
    cpu_values = [s['cpu_percent'] for s in cpu_data]
    memory_values = [s['rss_mb'] for s in cpu_data]
    
    return {
        'avg_cpu': sum(cpu_values) / len(cpu_values),
        'max_cpu': max(cpu_values),
        'avg_memory_mb': sum(memory_values) / len(memory_values),
        'max_memory_mb': max(memory_values)
    }

def print_progress(samples: List, width: int, desc: str) -> None:
    """Print progress bar."""
    if not samples:
        return
    
    elapsed = samples[-1]['timestamp'] - samples[0]['timestamp'] if len(samples) > 1 else 0
    progress = min(elapsed / 10, 1.0)  # Assume 10s duration
    filled = int(progress * width)
    bar = '█' * filled + '░' * (width - filled)
    print(f"\r🔄 [{bar}] {len(samples)}/20 {desc}", end='', flush=True)

def start_server(host: str, port: int, workers: int) -> subprocess.Popen:
    """Start a fresh server instance."""
    uvicorn_cmd = [
        "uvicorn", "app.main:app", 
        "--host", host, "--port", str(port),
        "--workers", str(workers),
        "--no-access-log",  # Disable access logging for cleaner output
        "--log-level", "warning"  # Reduce log verbosity
    ]
    
    proc = subprocess.Popen(uvicorn_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    active_processes.append(proc)
    return proc

def stop_server(server_proc: subprocess.Popen) -> None:
    """Stop server gracefully, then forcefully if needed."""
    if server_proc is None:
        return
    
    # Remove from active processes list
    if server_proc in active_processes:
        active_processes.remove(server_proc)
    
    try:
        server_proc.terminate()
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            server_proc.kill()
            server_proc.wait(timeout=2)
        except Exception as e:
            print(f"⚠️  Error killing server: {e}")
    except ProcessLookupError:
        pass  # Process already dead

def main():
    """Main benchmark function with clean server restarts."""
    # Register cleanup handlers
    register_cleanup()
    
    parser = argparse.ArgumentParser(description="Clean FastAPI Benchmark with Server Restarts")
    parser.add_argument("--rates", nargs="+", type=int, default=[1000, 5000, 10000], 
                       help="Rates to test (default: 1000, 5000, 10000)")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--duration", default="10s", help="Test duration (default: 10s)")
    parser.add_argument("--workers", type=int, default=1, help="Number of uvicorn worker processes (default: 1)")
    parser.add_argument("--filter", help="Filter endpoints by path prefix (e.g., '/api/simple' for simple endpoints only)")
    
    args = parser.parse_args()
    
    rates = args.rates
    host = args.host
    port = args.port
    duration = args.duration
    
    print("🚀 Clean FastAPI Benchmark (Server Restart Between Tests)")
    print("="*70)
    print(f"📊 Testing rates: {rates} RPS")
    print(f"⏱️  Duration: {duration}")
    print(f"🌐 Server: {host}:{port}")
    print(f"👥 Workers: {args.workers}")
    if args.filter:
        print(f"🔍 Filter: {args.filter}")
    
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f".tmp/clean_bench_{timestamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output: {out_dir}")
    
    # Discover endpoints
    print("🔍 Discovering benchmark endpoints...")
    if args.filter:
        print(f"   Filtering by path prefix: {args.filter}")
    discovered_endpoints = discover_benchmark_endpoints(args.filter)
    
    if not discovered_endpoints:
        print("❌ No benchmark endpoints found")
        return
    
    print(f"✅ Found {len(discovered_endpoints)} endpoints: {list(discovered_endpoints.keys())}")
    
    # Create target files for Vegeta
    for func_name, endpoint_info in discovered_endpoints.items():
        target_file = out_dir / f"t_{func_name}.txt"
        # Replace {item_id} with actual item ID
        url = f"http://{host}:{port}{endpoint_info['url']}".replace("{item_id}", "1000")
        
        # Determine HTTP method based on endpoint path
        if '/write/' in endpoint_info['url']:
            # POST request for write endpoints
            target_file.write_text(f"POST {url}\n")
        else:
            # GET request for read endpoints
            target_file.write_text(f"GET {url}\n")
    
    # Run benchmarks with server restarts
    total_tests = len(rates) * len(discovered_endpoints)
    current_test = 0
    benchmark_results = {}
    
    print(f"\n🏃 Running {total_tests} tests with clean server restarts...")
    start_time = time.time()
    
    for rate in rates:
        benchmark_results[rate] = {}
        
        for func_name in discovered_endpoints:
            current_test += 1
            
            print(f"\n📊 Test {current_test}/{total_tests}: {func_name} at {rate} RPS")
            
            # Start fresh server for each test
            print(f"  🔄 Starting fresh server...")
            server_proc = start_server(host, port, args.workers)
            
            # Wait for server to be ready
            print(f"  ⏳ Waiting for server...")
            if not wait_for_server(host, port, timeout=30):
                print(f"  ❌ Server failed to start")
                stop_server(server_proc)
                continue
            print(f"  ✅ Server is ready")
            
            # Seed data
            print(f"  🌱 Seeding data...")
            try:
                subprocess.run([
                    "curl", "-X", "POST", f"http://{host}:{port}/api/db/seed"
                ], check=True, capture_output=True, timeout=10)
                time.sleep(1)  # Brief pause to ensure DB is ready
            except subprocess.CalledProcessError as e:
                print(f"  ❌ Failed to seed data: {e}")
                stop_server(server_proc)
                continue
            
            # Test endpoint
            print(f"  🧪 Testing endpoint...")
            try:
                # Replace {item_id} with actual item ID for testing
                test_url = f"http://{host}:{port}{discovered_endpoints[func_name]['url']}".replace("{item_id}", "1000")
                
                # Determine HTTP method based on endpoint path
                if '/write/' in discovered_endpoints[func_name]['url']:
                    # POST request for write endpoints
                    result = subprocess.run([
                        "curl", "-s", "-X", "POST", test_url
                    ], capture_output=True, text=True, timeout=5)
                else:
                    # GET request for read endpoints
                    result = subprocess.run([
                        "curl", "-s", test_url
                    ], capture_output=True, text=True, timeout=5)
                
                if result.returncode != 0:
                    print(f"  ❌ Endpoint test failed: {result.stderr}")
                    stop_server(server_proc)
                    continue
                print(f"  ✅ Endpoint response: {result.stdout.strip()}")
            except subprocess.TimeoutExpired:
                print(f"  ❌ Endpoint test timed out")
                stop_server(server_proc)
                continue
            
            # Additional wait to ensure server is fully ready
            print(f"  ⏳ Final server readiness check...")
            time.sleep(2)
            
            # Prepare files
            bin_path = out_dir / f"{func_name}_{rate}.bin"
            json_path = out_dir / f"{func_name}_{rate}.json"
            cpu_path = out_dir / f"{func_name}_{rate}_cpu.json"
            
            # Start CPU monitoring
            cpu_data = []
            cpu_thread = threading.Thread(
                target=lambda: monitor_cpu_fast(
                    server_proc.pid, 12, cpu_path,
                    lambda samples, width, desc: print_progress(samples, width, desc)
                )
            )
            cpu_thread.daemon = True
            cpu_thread.start()
            
            # Run Vegeta attack
            try:
                print(f"  🎯 Running load test...")
                with open(bin_path, "wb") as f:
                    result = subprocess.run([
                        "vegeta", "attack",
                        "-duration", duration,
                        "-rate", str(rate),
                        "-timeout", "10s",
                        "-targets", str(out_dir / f"t_{func_name}.txt")
                    ], stdout=f, stderr=subprocess.PIPE)
                
                if result.returncode != 0:
                    print(f"  ❌ Vegeta failed: {result.stderr.decode()}")
                    stop_server(server_proc)
                    continue
                
                # Generate JSON report
                print(f"  📈 Generating report...")
                with open(json_path, "wb") as f:
                    subprocess.run([
                        "vegeta", "report", "-type=json", str(bin_path)
                    ], stdout=f)
                
                # Wait for CPU monitoring to finish
                cpu_thread.join(timeout=5)
                
                # Load and analyze data
                if cpu_path.exists():
                    with open(cpu_path) as f:
                        cpu_data = json.load(f)
                
                cpu_stats = analyze_cpu_data(cpu_data)
                
                with open(json_path) as f:
                    bench_data = json.load(f)
                
                # Calculate metrics
                total_requests = bench_data.get('requests', 0)
                success_rate = bench_data.get('success', 0)
                duration_seconds = int(duration[:-1])
                
                successful_requests = total_requests * success_rate
                actual_achieved_rps = successful_requests / duration_seconds if duration_seconds > 0 else 0
                
                # Debug output
                vegeta_reported_rate = bench_data.get('rate', 0)
                print(f"    Debug: Target={rate}, Vegeta_rate={vegeta_reported_rate:.1f}, Success_rate={success_rate:.1%}, "
                      f"Total_requests={total_requests}, Successful={successful_requests:.0f}, Achieved={actual_achieved_rps:.1f}")
                
                # Store results
                latencies = bench_data.get('latencies', {})
                benchmark_results[rate][func_name] = {
                    "achieved_rps": actual_achieved_rps,
                    "target_rps": rate,
                    "p50_ms": latencies.get('50th', 0) / 1e6,
                    "p95_ms": latencies.get('95th', 0) / 1e6,
                    "p99_ms": latencies.get('99th', 0) / 1e6,
                    "avg_ms": latencies.get('mean', 0) / 1e6,
                    "success_rate": success_rate,
                    "error_rate": 1 - success_rate,
                    "total_requests": total_requests,
                    "cpu_avg": cpu_stats['avg_cpu'],
                    "cpu_max": cpu_stats['max_cpu'],
                    "memory_avg_mb": cpu_stats['avg_memory_mb'],
                    "memory_max_mb": cpu_stats['max_memory_mb'],
                }
                
                elapsed = time.time() - start_time
                print(f"  ✅ Completed in {elapsed:.1f}s - CPU: {cpu_stats['avg_cpu']:.1f}% avg")
                
            except Exception as e:
                print(f"  ❌ Test failed: {e}")
            
            finally:
                # Always stop the server after each test
                print(f"  🛑 Stopping server...")
                stop_server(server_proc)
                time.sleep(2)  # Brief pause between tests
    
    # Generate summary
    print("\n" + "="*100)
    print("📊 CLEAN BENCHMARK RESULTS")
    print("="*100)
    
    for rate, data in benchmark_results.items():
        print(f"\n📈 Rate {rate} RPS:")
        
        # Calculate dynamic column width
        max_name_length = max(len(name) for name in data.keys()) if data else 0
        endpoint_width = max(25, max_name_length + 2)
        total_width = endpoint_width + 6 + 8 + 8 + 8 + 8 + 8 + 8 + 8
        
        print(f"{'Endpoint':<{endpoint_width}} {'Target':<6} {'Achieved':<8} {'P50(ms)':<8} {'Avg(ms)':<8} {'P95(ms)':<8} {'Success%':<8} {'CPU Avg%':<8}")
        print("-" * total_width)
        
        for name, metrics in data.items():
            print(f"{name:<{endpoint_width}} {metrics['target_rps']:<6} {metrics['achieved_rps']:<8.1f} {metrics['p50_ms']:<8.1f} "
                  f"{metrics['avg_ms']:<8.1f} {metrics['p95_ms']:<8.1f} {metrics['success_rate']*100:<8.1f} {metrics['cpu_avg']:<8.1f}")
    
    # Save results with metadata
    results_data = {
        "metadata": {
            "workers": args.workers,
            "host": args.host,
            "port": args.port,
            "duration": args.duration,
            "timestamp": datetime.now().isoformat(),
            "clean_restart": True
        },
        "results": benchmark_results
    }
    
    results_path = out_dir / "clean_results.json"
    with open(results_path, "w") as f:
        json.dump(results_data, f, indent=2)
    
    print(f"\n💾 Results saved: {results_path}")
    
    # Performance analysis
    print("\n" + "="*80)
    print("🏆 PERFORMANCE ANALYSIS")
    print("="*80)
    
    if benchmark_results:
        all_endpoints = list(next(iter(benchmark_results.values())).keys())
    else:
        all_endpoints = []
    
    # Find maximum sustainable RPS for each endpoint
    print(f"Maximum Sustainable RPS (Success Rate > 95%):")
    for endpoint in all_endpoints:
        max_sustainable = 0
        for rate, data in benchmark_results.items():
            if endpoint in data and data[endpoint]['success_rate'] > 0.95:
                max_sustainable = max(max_sustainable, data[endpoint]['achieved_rps'])
        
        print(f"  {endpoint:<25}: {max_sustainable:.1f} RPS")
    
    # CPU usage analysis
    if any(any(data[endpoint]['cpu_avg'] > 0 for endpoint in data.keys()) for data in benchmark_results.values()):
        print(f"\nCPU Usage Analysis:")
        for endpoint in all_endpoints:
            endpoint_cpu = []
            for rate, data in benchmark_results.items():
                if endpoint in data:
                    endpoint_cpu.append(data[endpoint]['cpu_avg'])
            
            if endpoint_cpu:
                avg_cpu = sum(endpoint_cpu) / len(endpoint_cpu)
                max_cpu = max(endpoint_cpu)
                print(f"  {endpoint:<25}: {avg_cpu:.1f}% avg, {max_cpu:.1f}% max")
    
    # Latency analysis
    print(f"\nLatency Analysis (P95):")
    for endpoint in all_endpoints:
        endpoint_latency = []
        for rate, data in benchmark_results.items():
            if endpoint in data:
                endpoint_latency.append(data[endpoint]['p95_ms'])
        
        if endpoint_latency:
            avg_latency = sum(endpoint_latency) / len(endpoint_latency)
            max_latency = max(endpoint_latency)
            print(f"  {endpoint:<25}: {avg_latency:.1f}ms avg, {max_latency:.1f}ms max")
    
    print(f"\n🎉 Clean benchmark completed in {time.time() - start_time:.1f}s")
    print(f"📁 Results directory: {out_dir}")
    print(f"📊 Generate interactive HTML report: `python plot_results.py`")
    
    # Final cleanup
    cleanup_all_processes()

if __name__ == "__main__":
    main()
