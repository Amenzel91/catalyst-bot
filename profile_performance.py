"""
Performance Profiler for Catalyst-Bot
======================================

Monitors GPU usage, CPU, memory, and execution time during bot operation.

Usage:
    # Monitor GPU continuously
    python profile_performance.py --gpu

    # Profile a single bot cycle
    python profile_performance.py --cycle

    # Full profiling report
    python profile_performance.py --full
"""

import argparse
import os
import sys
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()


def detect_gpu_type():
    """Detect GPU vendor (nvidia, amd, or none)."""
    # Try Nvidia first
    try:
        result = subprocess.run(
            ['nvidia-smi', '--version'],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return 'nvidia'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try AMD
    try:
        result = subprocess.run(
            ['rocm-smi', '--version'],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return 'amd'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


class GPUMonitor:
    """Monitor GPU usage in background thread (supports Nvidia and AMD)."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.samples = []
        self.gpu_type = detect_gpu_type()

    def start(self):
        """Start monitoring GPU."""
        if self.gpu_type is None:
            print("[WARN] No GPU detected - skipping monitoring")
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print(f"[INFO] GPU monitoring started ({self.gpu_type.upper()})...")

    def stop(self):
        """Stop monitoring and return stats."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

        if not self.samples:
            return {}

        gpu_utils = [s['gpu_util'] for s in self.samples if s['gpu_util'] is not None]
        mem_utils = [s['mem_util'] for s in self.samples if s['mem_util'] is not None]
        mem_used = [s['mem_used'] for s in self.samples if s['mem_used'] is not None]

        return {
            'samples': len(self.samples),
            'avg_gpu_util': sum(gpu_utils) / len(gpu_utils) if gpu_utils else 0,
            'max_gpu_util': max(gpu_utils) if gpu_utils else 0,
            'avg_mem_util': sum(mem_utils) / len(mem_utils) if mem_utils else 0,
            'max_mem_used_mb': max(mem_used) if mem_used else 0,
            'gpu_type': self.gpu_type,
        }

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.running:
            try:
                if self.gpu_type == 'nvidia':
                    self._monitor_nvidia()
                elif self.gpu_type == 'amd':
                    self._monitor_amd()

            except Exception as e:
                # Only log first error to avoid spam
                if len(self.samples) == 0:
                    print(f"[WARN] GPU monitoring error: {e}")

            time.sleep(0.5)  # Sample every 500ms

    def _monitor_nvidia(self):
        """Monitor Nvidia GPU using nvidia-smi."""
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,utilization.memory,memory.used',
             '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=2
        )

        if result.returncode == 0:
            line = result.stdout.strip()
            parts = [p.strip() for p in line.split(',')]

            if len(parts) >= 3:
                sample = {
                    'timestamp': time.time(),
                    'gpu_util': float(parts[0]) if parts[0] else None,
                    'mem_util': float(parts[1]) if parts[1] else None,
                    'mem_used': float(parts[2]) if parts[2] else None,
                }
                self.samples.append(sample)

    def _monitor_amd(self):
        """Monitor AMD GPU using rocm-smi."""
        # Try rocm-smi first (newer ROCm)
        try:
            result = subprocess.run(
                ['rocm-smi', '--showuse', '--showmeminfo', 'vram'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                # Parse output (format varies by ROCm version)
                output = result.stdout
                gpu_util = None
                mem_used = None

                # Look for "GPU use (%)" or similar
                for line in output.split('\n'):
                    if 'GPU use' in line or 'busy' in line.lower():
                        # Extract percentage
                        import re
                        match = re.search(r'(\d+)\s*%', line)
                        if match:
                            gpu_util = float(match.group(1))

                    if 'VRAM' in line and 'MB' in line:
                        # Extract memory usage
                        match = re.search(r'(\d+)\s*MB', line)
                        if match:
                            mem_used = float(match.group(1))

                sample = {
                    'timestamp': time.time(),
                    'gpu_util': gpu_util,
                    'mem_util': None,  # Not always available
                    'mem_used': mem_used,
                }
                self.samples.append(sample)
                return

        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: Try Windows Task Manager approach (if on Windows)
        if os.name == 'nt':
            try:
                # Use wmic to query GPU (Windows only, basic info)
                result = subprocess.run(
                    ['wmic', 'path', 'win32_VideoController', 'get', 'AdapterRAM,CurrentRefreshRate'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )

                # This gives limited info, but at least confirms GPU exists
                if result.returncode == 0:
                    sample = {
                        'timestamp': time.time(),
                        'gpu_util': None,  # Can't get from wmic
                        'mem_util': None,
                        'mem_used': None,
                    }
                    self.samples.append(sample)

            except Exception:
                pass


def profile_cycle():
    """Profile a single bot cycle."""
    print("\n" + "="*60)
    print("Profiling Single Bot Cycle")
    print("="*60)

    # Import here to avoid loading at module level
    from catalyst_bot.runner import _cycle
    from catalyst_bot.config import get_settings
    from catalyst_bot.logging_utils import get_logger

    settings = get_settings()
    log = get_logger("profiler")

    # Start GPU monitoring
    gpu_monitor = GPUMonitor()
    gpu_monitor.start()

    # Profile cycle execution
    import cProfile
    import pstats
    from io import StringIO

    profiler = cProfile.Profile()

    print("\n[INFO] Running cycle with profiler...")
    start_time = time.time()

    profiler.enable()
    _cycle(log, settings)
    profiler.disable()

    elapsed = time.time() - start_time

    # Stop GPU monitoring
    gpu_stats = gpu_monitor.stop()

    # Print results
    print(f"\n[OK] Cycle completed in {elapsed:.2f}s")

    print("\n" + "="*60)
    print("GPU Statistics")
    print("="*60)
    print(f"Samples collected: {gpu_stats.get('samples', 0)}")
    print(f"Avg GPU utilization: {gpu_stats.get('avg_gpu_util', 0):.1f}%")
    print(f"Max GPU utilization: {gpu_stats.get('max_gpu_util', 0):.1f}%")
    print(f"Avg memory utilization: {gpu_stats.get('avg_mem_util', 0):.1f}%")
    print(f"Max memory used: {gpu_stats.get('max_mem_used_mb', 0):.0f} MB")

    # Print top CPU time consumers
    print("\n" + "="*60)
    print("Top CPU Time Consumers")
    print("="*60)

    s = StringIO()
    stats = pstats.Stats(profiler, stream=s)
    stats.sort_stats('cumulative')
    stats.print_stats(20)

    output = s.getvalue()
    for line in output.split('\n')[5:25]:  # Skip header, show top 20
        print(line)

    # Identify bottlenecks
    print("\n" + "="*60)
    print("Bottleneck Analysis")
    print("="*60)

    # Parse stats to identify bottlenecks
    stats.sort_stats('cumulative')
    for func, stat in list(stats.stats.items())[:10]:
        filename, line, func_name = func
        cc, nc, tt, ct, callers = stat

        if 'chart' in filename.lower() or 'chart' in func_name.lower():
            print(f"[CHART] {func_name} - {ct:.3f}s cumulative")
        elif 'sentiment' in filename.lower() or 'sentiment' in func_name.lower():
            print(f"[SENTIMENT] {func_name} - {ct:.3f}s cumulative")
        elif 'llm' in filename.lower() or 'llm' in func_name.lower():
            print(f"[LLM] {func_name} - {ct:.3f}s cumulative")
        elif 'matplotlib' in filename.lower():
            print(f"[MATPLOTLIB] {func_name} - {ct:.3f}s cumulative")

    print("\n[RECOMMENDATIONS]")

    if gpu_stats.get('avg_gpu_util', 0) < 20:
        print("  - GPU underutilized - consider enabling more LLM features")
    elif gpu_stats.get('avg_gpu_util', 0) > 80:
        print("  - GPU highly utilized - consider batching or reducing LLM calls")

    if elapsed > 10:
        print("  - Cycle time >10s - consider implementing async chart generation")

    # Check if chart generation is slow
    chart_heavy = any('chart' in str(func).lower() for func in stats.stats.keys())
    if chart_heavy:
        print("  - Chart generation detected - implement worker pool for parallel rendering")


def monitor_gpu_continuous():
    """Monitor GPU usage continuously."""
    print("\n" + "="*60)
    print("Continuous GPU Monitoring")
    print("="*60)
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            result = subprocess.run(
                ['nvidia-smi', 'dmon', '-c', '1'],
                capture_output=True,
                text=True,
                timeout=3
            )

            print(result.stdout)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[OK] Monitoring stopped")


def full_profile():
    """Full profiling report with recommendations."""
    print("\n" + "="*60)
    print("Full Performance Profile")
    print("="*60)

    # Check GPU availability
    print("\n[1] GPU Availability Check")
    print("-" * 60)
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,driver_version,memory.total',
             '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=3
        )

        if result.returncode == 0:
            print(f"[OK] GPU detected: {result.stdout.strip()}")
        else:
            print("[FAIL] No GPU detected")
    except FileNotFoundError:
        print("[FAIL] nvidia-smi not found - GPU drivers not installed")
    except Exception as e:
        print(f"[FAIL] GPU check failed: {e}")

    # Check Ollama
    print("\n[2] LLM (Ollama) Status")
    print("-" * 60)
    try:
        import requests
        response = requests.get('http://localhost:11434/api/tags', timeout=3)
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"[OK] Ollama running with {len(models)} model(s)")
            for model in models:
                print(f"   - {model.get('name')}")
        else:
            print("[WARN] Ollama running but unexpected response")
    except requests.exceptions.ConnectionError:
        print("[FAIL] Ollama not running (start with: ollama serve)")
    except Exception as e:
        print(f"[FAIL] Ollama check failed: {e}")

    # Check feature flags
    print("\n[3] Feature Flags")
    print("-" * 60)
    llm_enabled = os.getenv('FEATURE_LLM_CLASSIFIER', '0') in ('1', 'true', 'yes', 'on')
    llm_fallback = os.getenv('FEATURE_LLM_FALLBACK', '0') in ('1', 'true', 'yes', 'on')
    llm_sec = os.getenv('FEATURE_LLM_SEC_ANALYSIS', '0') in ('1', 'true', 'yes', 'on')

    print(f"LLM Classifier: {'[ON]' if llm_enabled else '[OFF]'}")
    print(f"LLM Fallback: {'[ON]' if llm_fallback else '[OFF]'}")
    print(f"LLM SEC Analysis: {'[ON]' if llm_sec else '[OFF]'}")

    # Profile cycle
    print("\n[4] Cycle Profiling")
    print("-" * 60)
    profile_cycle()


def main():
    parser = argparse.ArgumentParser(description='Profile Catalyst-Bot performance')
    parser.add_argument('--gpu', action='store_true', help='Monitor GPU continuously')
    parser.add_argument('--cycle', action='store_true', help='Profile single cycle')
    parser.add_argument('--full', action='store_true', help='Full profiling report')

    args = parser.parse_args()

    if args.gpu:
        monitor_gpu_continuous()
    elif args.cycle:
        profile_cycle()
    elif args.full:
        full_profile()
    else:
        # Default: full profile
        full_profile()


if __name__ == '__main__':
    main()
