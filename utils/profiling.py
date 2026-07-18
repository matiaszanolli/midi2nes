"""Memory and performance profiling utilities for MIDI2NES."""

import functools
import time
import psutil
import tracemalloc
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
import json
import threading


# Reference-counted tracemalloc start/stop shared by every profiler in this
# module (and benchmarks/performance_suite.py's PerformanceProfiler). Each
# profiler previously called the bare, process-global tracemalloc.start()/
# stop() independently, so a @profile_memory_usage-decorated function called
# inside a PerformanceContext (or any other nesting) had its inner stop() tear
# down tracing for the still-running outer profiler — the outer's later
# get_traced_memory() then raised, was swallowed by a bare except, and it
# silently fell back to reporting current RSS instead of the traced peak
# (#118). Only the outermost acquire starts tracing and only the outermost
# release stops it.
_tracemalloc_depth = 0
_tracemalloc_lock = threading.Lock()


def _tracemalloc_acquire():
    """Start tracemalloc if not already tracing; bump the nesting depth."""
    global _tracemalloc_depth
    with _tracemalloc_lock:
        if _tracemalloc_depth == 0 and not tracemalloc.is_tracing():
            tracemalloc.start()
        _tracemalloc_depth += 1


def _tracemalloc_release():
    """Drop the nesting depth; only stop tracemalloc once the outermost
    profiler releases it."""
    global _tracemalloc_depth
    with _tracemalloc_lock:
        _tracemalloc_depth = max(0, _tracemalloc_depth - 1)
        if _tracemalloc_depth == 0 and tracemalloc.is_tracing():
            tracemalloc.stop()


@dataclass
class ProfileResult:
    """Result of a profiling operation."""
    function_name: str
    duration_ms: float
    memory_before_mb: float
    memory_after_mb: float
    memory_peak_mb: float
    memory_delta_mb: float
    cpu_percent: float
    success: bool
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryMonitor:
    """Continuous memory monitoring utility."""
    
    def __init__(self, interval_ms: int = 100):
        """
        Initialize memory monitor.
        
        Args:
            interval_ms: Monitoring interval in milliseconds
        """
        self.interval_ms = interval_ms
        self.process = psutil.Process()
        self._monitoring = False
        self._monitor_thread = None
        self._peak_memory = 0
        self._memory_samples = []
        self._sampling_errors = 0

    def start_monitoring(self):
        """Start continuous memory monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self._peak_memory = 0
        self._sampling_errors = 0
        # Seed with an immediate RSS read (#336/PERF-16): the monitor thread's
        # first sample can arrive after stop_monitoring() already ran for
        # sub-interval work, leaving _memory_samples empty and stop_monitoring
        # reporting a misleading peak_mb=0 instead of the RSS at start.
        self._memory_samples = [self.process.memory_info().rss / 1024 / 1024]

        self._monitor_thread = threading.Thread(target=self._monitor_loop)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
        
    def stop_monitoring(self) -> Dict[str, float]:
        """
        Stop monitoring and return statistics.
        
        Returns:
            Dictionary with memory statistics
        """
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)

        # _memory_samples always has at least the start_monitoring() seed
        # sample, so this is now defense-in-depth, not the common case.
        if not self._memory_samples:
            return {"peak_mb": 0, "average_mb": 0, "samples": 0}

        return {
            "peak_mb": max(self._memory_samples),
            "average_mb": sum(self._memory_samples) / len(self._memory_samples),
            "samples": len(self._memory_samples),
            "min_mb": min(self._memory_samples),
            "sampling_errors": self._sampling_errors
        }

    def _monitor_loop(self):
        """Memory monitoring loop."""
        while self._monitoring:
            try:
                memory_mb = self.process.memory_info().rss / 1024 / 1024
                self._memory_samples.append(memory_mb)
                self._peak_memory = max(self._peak_memory, memory_mb)
                time.sleep(self.interval_ms / 1000.0)
            except Exception:
                # Count instead of silently discarding (#336/PERF-16) --
                # KeyboardInterrupt/SystemExit still propagate since this
                # only catches Exception. A sampling error ends the loop
                # (self.process may no longer be readable), but the caller
                # can now tell a stat-collection failure happened instead of
                # reading a clean-looking (and possibly short) sample set.
                self._sampling_errors += 1
                break


class ProfilerRegistry:
    """Registry for managing profiler instances and results."""
    
    def __init__(self):
        self._profiles: Dict[str, ProfileResult] = {}
        self._active_monitors: Dict[str, MemoryMonitor] = {}
        
    def register_profile(self, result: ProfileResult):
        """Register a profile result."""
        self._profiles[f"{result.function_name}_{time.time()}"] = result
        
    def get_profiles(self) -> Dict[str, ProfileResult]:
        """Get all registered profiles."""
        return self._profiles.copy()
        
    def clear_profiles(self):
        """Clear all registered profiles."""
        self._profiles.clear()
        
    def export_profiles(self, output_path: str):
        """Export profiles to JSON file."""
        profiles_data = {}
        for key, profile in self._profiles.items():
            profiles_data[key] = {
                'function_name': profile.function_name,
                'duration_ms': profile.duration_ms,
                'memory_before_mb': profile.memory_before_mb,
                'memory_after_mb': profile.memory_after_mb,
                'memory_peak_mb': profile.memory_peak_mb,
                'memory_delta_mb': profile.memory_delta_mb,
                'cpu_percent': profile.cpu_percent,
                'success': profile.success,
                'error_message': profile.error_message,
                'metadata': profile.metadata
            }
        
        with open(output_path, 'w') as f:
            json.dump(profiles_data, f, indent=2)


# Global profiler registry
_profiler_registry = ProfilerRegistry()


def profile_memory_usage(
    include_peak: bool = True,
    include_cpu: bool = True,
    save_to_registry: bool = True,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Decorator for profiling memory usage and performance of functions.
    
    Args:
        include_peak: Whether to monitor peak memory usage
        include_cpu: Whether to monitor CPU usage
        save_to_registry: Whether to save results to global registry
        metadata: Additional metadata to include in results
    
    Example:
        @profile_memory_usage(metadata={"stage": "parsing"})
        def parse_midi_file(filename):
            return parse_midi_to_frames(filename)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            process = psutil.Process()
            monitor = MemoryMonitor() if include_peak else None
            
            # Start monitoring
            memory_before = process.memory_info().rss / 1024 / 1024  # MB
            # cpu_percent() with no interval= is a non-blocking, advisory-only
            # reading (returns 0.0 on the process's first call ever, per
            # psutil's docs) rather than a precise delta over this call — an
            # interval= would add real blocking latency to every profiled
            # call, which is worse than an advisory number here (#118).
            cpu_before = process.cpu_percent() if include_cpu else 0
            
            if monitor:
                monitor.start_monitoring()
            
            # Start tracemalloc for detailed memory tracking (nesting-safe, #118)
            _tracemalloc_acquire()
            start_time = time.perf_counter()
            
            success = True
            error_message = ""
            result = None
            
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                success = False
                error_message = str(e)
                raise
            finally:
                # Calculate metrics
                duration = (time.perf_counter() - start_time) * 1000  # ms
                memory_after = process.memory_info().rss / 1024 / 1024  # MB
                memory_delta = memory_after - memory_before
                cpu_after = process.cpu_percent() if include_cpu else 0
                
                # Get peak memory from tracemalloc
                try:
                    current_trace, peak_trace = tracemalloc.get_traced_memory()
                    peak_memory_traced = peak_trace / 1024 / 1024  # MB
                except RuntimeError:
                    # tracemalloc isn't tracing (shouldn't happen with the
                    # nesting-safe acquire/release below, but keep a fallback).
                    peak_memory_traced = memory_after
                finally:
                    # Nesting-safe release (#118): only actually stops
                    # tracemalloc once every acquirer has released it, so an
                    # outer profiler's own get_traced_memory() above is never
                    # blinded by this call.
                    _tracemalloc_release()
                
                # Get peak memory from continuous monitoring
                monitor_stats = monitor.stop_monitoring() if monitor else {"peak_mb": memory_after}
                peak_memory = max(peak_memory_traced, monitor_stats["peak_mb"])
                
                # Create profile result
                profile_result = ProfileResult(
                    function_name=func.__name__,
                    duration_ms=duration,
                    memory_before_mb=memory_before,
                    memory_after_mb=memory_after,
                    memory_peak_mb=peak_memory,
                    memory_delta_mb=memory_delta,
                    cpu_percent=cpu_after - cpu_before if include_cpu else 0,
                    success=success,
                    error_message=error_message,
                    metadata=metadata or {}
                )
                
                # Print summary if enabled
                if profile_result.success:
                    print(f"[PROFILE] {func.__name__}: {duration:.1f}ms, "
                          f"Memory: {memory_delta:+.1f}MB (peak: {peak_memory:.1f}MB)")
                else:
                    print(f"[PROFILE] {func.__name__}: FAILED after {duration:.1f}ms - {error_message}")
                
                # Save to registry if requested
                if save_to_registry:
                    _profiler_registry.register_profile(profile_result)
            
            return result
        
        return wrapper
    return decorator


def profile_memory_simple(func: Callable) -> Callable:
    """Simple memory profiling decorator with minimal overhead."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        start_time = time.perf_counter()
        
        try:
            result = func(*args, **kwargs)
            success = True
        except Exception as e:
            success = False
            raise
        finally:
            duration = (time.perf_counter() - start_time) * 1000  # ms
            memory_after = process.memory_info().rss / 1024 / 1024  # MB
            memory_delta = memory_after - memory_before
            
            status = "✓" if success else "✗"
            print(f"[PROFILE] {status} {func.__name__}: {duration:.1f}ms, "
                  f"{memory_delta:+.1f}MB")
        
        return result
    
    return wrapper


class PerformanceContext:
    """Context manager for detailed performance monitoring."""
    
    def __init__(self, name: str, print_results: bool = True):
        """
        Initialize performance context.
        
        Args:
            name: Name of the operation being monitored
            print_results: Whether to print results on exit
        """
        self.name = name
        self.print_results = print_results
        self.process = psutil.Process()
        self.monitor = MemoryMonitor()
        self.start_time = None
        self.start_memory = None
        
    def __enter__(self):
        """Enter the performance monitoring context."""
        self.start_time = time.perf_counter()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.monitor.start_monitoring()
        _tracemalloc_acquire()  # nesting-safe (#118)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the performance monitoring context and report results."""
        # Calculate metrics
        duration = (time.perf_counter() - self.start_time) * 1000  # ms
        end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = end_memory - self.start_memory

        # Get detailed memory info
        try:
            current_trace, peak_trace = tracemalloc.get_traced_memory()
            peak_memory_traced = peak_trace / 1024 / 1024  # MB
        except RuntimeError:
            peak_memory_traced = end_memory
        finally:
            _tracemalloc_release()  # nesting-safe (#118)
        
        # Get monitoring statistics
        monitor_stats = self.monitor.stop_monitoring()
        peak_memory = max(peak_memory_traced, monitor_stats["peak_mb"])
        
        # Store results as attributes for external access
        self.duration_ms = duration
        self.memory_delta_mb = memory_delta
        self.peak_memory_mb = peak_memory
        self.success = exc_type is None
        
        if self.print_results:
            status = "✓" if self.success else "✗"
            print(f"[CONTEXT] {status} {self.name}: {duration:.1f}ms, "
                  f"{memory_delta:+.1f}MB delta, {peak_memory:.1f}MB peak")


def get_memory_usage() -> Dict[str, float]:
    """
    Get current memory usage statistics.
    
    Returns:
        Dictionary with memory usage information
    """
    process = psutil.Process()
    memory_info = process.memory_info()
    
    return {
        "rss_mb": memory_info.rss / 1024 / 1024,
        "vms_mb": memory_info.vms / 1024 / 1024,
        "percent": process.memory_percent(),
        "available_mb": psutil.virtual_memory().available / 1024 / 1024
    }


def log_memory_usage(prefix: str = ""):
    """Log current memory usage."""
    usage = get_memory_usage()
    prefix_str = f"{prefix}: " if prefix else ""
    print(f"[MEMORY] {prefix_str}{usage['rss_mb']:.1f}MB RSS, "
          f"{usage['percent']:.1f}% of system")


def clear_profiler_registry():
    """Clear the global profiler registry."""
    _profiler_registry.clear_profiles()


def export_profiler_registry(output_path: str):
    """Export profiler registry to JSON file."""
    _profiler_registry.export_profiles(output_path)


def get_profiler_registry() -> Dict[str, ProfileResult]:
    """Get all profiles from the registry."""
    return _profiler_registry.get_profiles()


# Performance monitoring context manager for easy usage
def monitor_performance(name: str, print_results: bool = True):
    """
    Create a performance monitoring context manager.
    
    Args:
        name: Name of the operation
        print_results: Whether to print results
        
    Returns:
        PerformanceContext instance
    """
    return PerformanceContext(name, print_results)


if __name__ == "__main__":
    # Example usage and tests
    
    @profile_memory_usage(metadata={"test": "example"})
    def example_function():
        # Simulate some work
        data = [i for i in range(100000)]
        time.sleep(0.1)
        return len(data)
    
    # Test the decorator
    print("Testing memory profiling decorator:")
    result = example_function()
    print(f"Result: {result}")
    
    # Test the context manager
    print("\nTesting performance context manager:")
    with monitor_performance("example_context"):
        data = [i ** 2 for i in range(50000)]
        time.sleep(0.05)
    
    # Show registry contents
    profiles = get_profiler_registry()
    print(f"\nProfiler registry contains {len(profiles)} entries")
    
    # Export profiles
    if profiles:
        export_profiler_registry("test_profiles.json")
        print("Exported profiles to test_profiles.json")
