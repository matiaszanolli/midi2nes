"""Performance benchmarking suite for MIDI2NES pipeline."""

import time
import psutil
import json
import tracemalloc
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager
import tempfile
import os

# Import pipeline components
import sys
sys.path.append(str(Path(__file__).parent.parent))

from tracker.parser import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore
from tracker.pattern_detector import EnhancedPatternDetector
from tracker.tempo_map import EnhancedTempoMap
from exporter.exporter_ca65 import CA65Exporter
from exporter.exporter_nsf import NSFExporter


@dataclass
class BenchmarkResult:
    """Individual benchmark result."""
    stage: str
    duration_ms: float
    memory_peak_mb: float
    memory_delta_mb: float
    cpu_percent: float
    success: bool
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineBenchmark:
    """Complete pipeline benchmark result."""
    file_path: str
    file_size_kb: float
    total_duration_ms: float
    total_memory_mb: float
    stages: List[BenchmarkResult] = field(default_factory=list)
    timestamp: str = ""
    midi_info: Dict[str, Any] = field(default_factory=dict)


class PerformanceProfiler:
    """Performance profiler for individual operations."""
    
    def __init__(self):
        self.process = psutil.Process()
        self._start_time = None
        self._start_memory = None
        self._start_cpu = None
        self._peak_memory = 0
    
    @contextmanager
    def profile(self, stage_name: str):
        """Context manager for profiling a code block."""
        try:
            # Start profiling
            self._start_profiling()
            
            yield
            
            # End profiling and get results
            result = self._end_profiling(stage_name, True)
            
        except Exception as e:
            # Handle errors gracefully
            result = self._end_profiling(stage_name, False, str(e))
            raise
    
    def _start_profiling(self):
        """Start performance monitoring."""
        # Start memory tracing
        tracemalloc.start()
        
        # Record initial state
        self._start_time = time.perf_counter()
        self._start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self._start_cpu = self.process.cpu_percent()
        self._peak_memory = self._start_memory
    
    def _end_profiling(self, stage_name: str, success: bool, error_msg: str = "") -> BenchmarkResult:
        """End profiling and create result."""
        # Calculate metrics
        duration = (time.perf_counter() - self._start_time) * 1000  # ms
        current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = current_memory - self._start_memory
        cpu_percent = self.process.cpu_percent()
        
        # Get memory tracing info
        try:
            current_trace, peak_trace = tracemalloc.get_traced_memory()
            peak_memory_traced = peak_trace / 1024 / 1024  # MB
            tracemalloc.stop()
        except:
            peak_memory_traced = current_memory
        
        # Update peak memory
        self._peak_memory = max(self._peak_memory, current_memory, peak_memory_traced)
        
        return BenchmarkResult(
            stage=stage_name,
            duration_ms=duration,
            memory_peak_mb=self._peak_memory,
            memory_delta_mb=memory_delta,
            cpu_percent=cpu_percent,
            success=success,
            error_message=error_msg
        )


class PerformanceBenchmark:
    """Comprehensive performance benchmarking system."""
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize benchmark suite.
        
        Args:
            output_dir: Directory to save benchmark results
        """
        self.output_dir = Path(output_dir) if output_dir else Path("benchmark_results")
        self.output_dir.mkdir(exist_ok=True)
        self.profiler = PerformanceProfiler()
        self.results: List[PipelineBenchmark] = []
    
    def benchmark_pipeline_stage(self, stage_func: Callable, stage_name: str, *args, **kwargs):
        """
        Benchmark a single pipeline stage.
        
        Args:
            stage_func: Function to benchmark
            stage_name: Name of the stage for reporting
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Tuple of (result, benchmark_data)
        """
        with self.profiler.profile(stage_name):
            result = stage_func(*args, **kwargs)
        
        return result
    
    def benchmark_parse_stage(self, midi_file: str) -> tuple:
        """Benchmark MIDI parsing performance."""
        def parse_wrapper():
            return parse_midi_to_frames(midi_file)
        
        with self.profiler.profile("parse"):
            result = parse_wrapper()
        
        return result, self.profiler._end_profiling("parse", True)
    
    def benchmark_map_stage(self, parsed_data: Dict[str, Any]) -> tuple:
        """Benchmark track mapping performance."""
        def map_wrapper():
            # Create a temporary DPCM index for testing
            temp_dpcm = {"samples": {}, "mappings": {}}
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(temp_dpcm, f)
                temp_path = f.name
            
            try:
                result = assign_tracks_to_nes_channels(parsed_data["events"], temp_path)
                return result
            finally:
                os.unlink(temp_path)
        
        with self.profiler.profile("map"):
            result = map_wrapper()
        
        return result, self.profiler._end_profiling("map", True)
    
    def benchmark_frames_stage(self, mapped_data: Dict[str, Any]) -> tuple:
        """Benchmark frame generation performance."""
        def frames_wrapper():
            emulator = NESEmulatorCore()
            return emulator.process_all_tracks(mapped_data)
        
        with self.profiler.profile("frames"):
            result = frames_wrapper()
        
        return result, self.profiler._end_profiling("frames", True)
    
    def benchmark_pattern_detection(self, frames_data: Dict[str, Any]) -> tuple:
        """Benchmark pattern detection performance."""
        def pattern_wrapper():
            # Create tempo map and pattern detector
            tempo_map = EnhancedTempoMap(initial_tempo=500000)
            detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3)
            
            # Extract events from frames structure
            events = []
            for channel_name, channel_frames in frames_data.items():
                for frame_num, frame_data in channel_frames.items():
                    event = {
                        'frame': int(frame_num),
                        'note': frame_data.get('note', 0),
                        'volume': frame_data.get('volume', 0)
                    }
                    events.append(event)
            
            # Sort events by frame number
            events.sort(key=lambda x: x['frame'])
            
            # Detect patterns
            return detector.detect_patterns(events)
        
        with self.profiler.profile("pattern_detection"):
            result = pattern_wrapper()
        
        return result, self.profiler._end_profiling("pattern_detection", True)
    
    def benchmark_export_stage(self, frames_data: Dict[str, Any], patterns: Dict[str, Any] = None) -> tuple:
        """Benchmark export performance."""
        def export_wrapper():
            with tempfile.NamedTemporaryFile(suffix='.s', delete=False) as f:
                temp_path = f.name
            
            try:
                exporter = CA65Exporter()
                patterns_dict = patterns.get('patterns', {}) if patterns else {}
                references_dict = patterns.get('references', {}) if patterns else {}
                
                exporter.export_tables_with_patterns(
                    frames_data,
                    patterns_dict,
                    references_dict,
                    temp_path
                )
                return temp_path
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        with self.profiler.profile("export"):
            result = export_wrapper()
        
        return result, self.profiler._end_profiling("export", True)
    
    def run_full_pipeline(self, midi_file: str) -> PipelineBenchmark:
        """
        Run complete pipeline benchmark on a MIDI file.
        
        Args:
            midi_file: Path to MIDI file to benchmark
            
        Returns:
            Complete pipeline benchmark result
        """
        midi_path = Path(midi_file)
        if not midi_path.exists():
            raise FileNotFoundError(f"MIDI file not found: {midi_file}")
        
        # Initialize benchmark result
        benchmark = PipelineBenchmark(
            file_path=str(midi_path),
            file_size_kb=midi_path.stat().st_size / 1024,
            total_duration_ms=0,
            total_memory_mb=0,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        pipeline_start = time.perf_counter()
        memory_start = self.profiler.process.memory_info().rss / 1024 / 1024
        
        try:
            # Stage 1: Parse MIDI
            print(f"  Benchmarking parse stage...")
            parsed_data, parse_result = self.benchmark_parse_stage(midi_file)
            benchmark.stages.append(parse_result)
            benchmark.midi_info = {
                "tracks": len(parsed_data.get("events", [])),
                "total_events": sum(len(track) for track in parsed_data.get("events", [])),
            }
            
            # Stage 2: Map tracks
            print(f"  Benchmarking map stage...")
            mapped_data, map_result = self.benchmark_map_stage(parsed_data)
            benchmark.stages.append(map_result)
            
            # Stage 3: Generate frames
            print(f"  Benchmarking frames stage...")
            frames_data, frames_result = self.benchmark_frames_stage(mapped_data)
            benchmark.stages.append(frames_result)
            
            # Stage 4: Pattern detection
            print(f"  Benchmarking pattern detection...")
            patterns_data, patterns_result = self.benchmark_pattern_detection(frames_data)
            benchmark.stages.append(patterns_result)
            
            # Stage 5: Export
            print(f"  Benchmarking export stage...")
            export_result_path, export_result = self.benchmark_export_stage(frames_data, patterns_data)
            benchmark.stages.append(export_result)
            
        except Exception as e:
            print(f"  Pipeline failed: {str(e)}")
            # Add failed stage to results
            failed_result = BenchmarkResult(
                stage="pipeline_error",
                duration_ms=0,
                memory_peak_mb=0,
                memory_delta_mb=0,
                cpu_percent=0,
                success=False,
                error_message=str(e)
            )
            benchmark.stages.append(failed_result)
        
        # Calculate totals
        benchmark.total_duration_ms = (time.perf_counter() - pipeline_start) * 1000
        benchmark.total_memory_mb = self.profiler.process.memory_info().rss / 1024 / 1024 - memory_start
        
        self.results.append(benchmark)
        return benchmark
    
    def run_batch_benchmarks(self, midi_files: List[str]) -> List[PipelineBenchmark]:
        """
        Run benchmarks on multiple MIDI files.
        
        Args:
            midi_files: List of MIDI file paths
            
        Returns:
            List of benchmark results
        """
        results = []
        
        for i, midi_file in enumerate(midi_files):
            print(f"Benchmarking {i+1}/{len(midi_files)}: {midi_file}")
            try:
                result = self.run_full_pipeline(midi_file)
                results.append(result)
                print(f"  Completed in {result.total_duration_ms:.1f}ms")
            except Exception as e:
                print(f"  Failed: {str(e)}")
        
        return results
    
    def generate_report(self, output_path: str):
        """
        Generate comprehensive performance report.
        
        Args:
            output_path: Path to save the JSON report
        """
        if not self.results:
            print("No benchmark results to report")
            return
        
        # Calculate summary statistics
        total_files = len(self.results)
        successful_runs = len([r for r in self.results if all(s.success for s in r.stages)])
        
        # Stage-wise statistics
        stage_stats = {}
        for result in self.results:
            for stage in result.stages:
                if stage.stage not in stage_stats:
                    stage_stats[stage.stage] = {
                        'durations': [],
                        'memory_usage': [],
                        'success_count': 0,
                        'failure_count': 0
                    }
                
                stage_stats[stage.stage]['durations'].append(stage.duration_ms)
                stage_stats[stage.stage]['memory_usage'].append(stage.memory_peak_mb)
                
                if stage.success:
                    stage_stats[stage.stage]['success_count'] += 1
                else:
                    stage_stats[stage.stage]['failure_count'] += 1
        
        # Calculate averages and percentiles
        summary_stats = {}
        for stage, stats in stage_stats.items():
            if stats['durations']:
                durations = sorted(stats['durations'])
                memory_usage = sorted(stats['memory_usage'])
                
                summary_stats[stage] = {
                    'average_duration_ms': sum(durations) / len(durations),
                    'median_duration_ms': durations[len(durations) // 2],
                    'p95_duration_ms': durations[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0],
                    'average_memory_mb': sum(memory_usage) / len(memory_usage),
                    'peak_memory_mb': max(memory_usage),
                    'success_rate': stats['success_count'] / (stats['success_count'] + stats['failure_count']),
                    'total_runs': stats['success_count'] + stats['failure_count']
                }
        
        # Create comprehensive report
        report = {
            'benchmark_info': {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'total_files_tested': total_files,
                'successful_runs': successful_runs,
                'success_rate': successful_runs / total_files if total_files > 0 else 0,
            },
            'summary_statistics': summary_stats,
            'detailed_results': [
                {
                    'file_path': r.file_path,
                    'file_size_kb': r.file_size_kb,
                    'total_duration_ms': r.total_duration_ms,
                    'total_memory_mb': r.total_memory_mb,
                    'midi_info': r.midi_info,
                    'stages': [
                        {
                            'stage': s.stage,
                            'duration_ms': s.duration_ms,
                            'memory_peak_mb': s.memory_peak_mb,
                            'memory_delta_mb': s.memory_delta_mb,
                            'cpu_percent': s.cpu_percent,
                            'success': s.success,
                            'error_message': s.error_message,
                            'metadata': s.metadata
                        } for s in r.stages
                    ]
                } for r in self.results
            ]
        }
        
        # Save report
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Performance report saved to: {output_path}")
        
        # Print summary to console
        print("\n=== PERFORMANCE BENCHMARK SUMMARY ===")
        print(f"Files tested: {total_files}")
        print(f"Success rate: {successful_runs}/{total_files} ({successful_runs/total_files*100:.1f}%)")
        print("\nStage Performance:")
        
        for stage, stats in summary_stats.items():
            print(f"  {stage:20} {stats['average_duration_ms']:8.1f}ms avg  "
                  f"{stats['peak_memory_mb']:6.1f}MB peak  "
                  f"{stats['success_rate']*100:5.1f}% success")
        
        return report


if __name__ == "__main__":
    # Example usage
    benchmark = PerformanceBenchmark()
    
    # Test with a simple synthetic MIDI file (if available)
    import tempfile
    
    print("MIDI2NES Performance Benchmark Suite")
    print("Note: This requires MIDI files to benchmark against.")
    print("Add MIDI files to test_data/ directory to run benchmarks.")
