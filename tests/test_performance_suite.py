"""Tests for performance benchmarking suite."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time
import sys
import os

# Add the parent directory to the path to import modules
sys.path.append(str(Path(__file__).parent.parent))

from benchmarks.performance_suite import (
    PerformanceBenchmark, 
    BenchmarkResult, 
    PipelineBenchmark,
    PerformanceProfiler
)


class TestBenchmarkResult:
    """Test BenchmarkResult dataclass."""
    
    def test_benchmark_result_creation(self):
        """Test creating a benchmark result."""
        result = BenchmarkResult(
            stage="test_stage",
            duration_ms=100.5,
            memory_peak_mb=50.2,
            memory_delta_mb=10.1,
            cpu_percent=15.3,
            success=True,
            error_message="",
            metadata={"test": "data"}
        )
        
        assert result.stage == "test_stage"
        assert result.duration_ms == 100.5
        assert result.memory_peak_mb == 50.2
        assert result.memory_delta_mb == 10.1
        assert result.cpu_percent == 15.3
        assert result.success is True
        assert result.error_message == ""
        assert result.metadata == {"test": "data"}
    
    def test_benchmark_result_default_values(self):
        """Test benchmark result with default values."""
        result = BenchmarkResult(
            stage="test",
            duration_ms=100,
            memory_peak_mb=50,
            memory_delta_mb=10,
            cpu_percent=15,
            success=True
        )
        
        assert result.error_message == ""
        assert result.metadata == {}


class TestPipelineBenchmark:
    """Test PipelineBenchmark dataclass."""
    
    def test_pipeline_benchmark_creation(self):
        """Test creating a pipeline benchmark."""
        benchmark = PipelineBenchmark(
            file_path="test.mid",
            file_size_kb=10.5,
            total_duration_ms=500.0,
            total_memory_mb=100.0,
            timestamp="2024-01-01 12:00:00"
        )
        
        assert benchmark.file_path == "test.mid"
        assert benchmark.file_size_kb == 10.5
        assert benchmark.total_duration_ms == 500.0
        assert benchmark.total_memory_mb == 100.0
        assert benchmark.timestamp == "2024-01-01 12:00:00"
        assert benchmark.stages == []
        assert benchmark.midi_info == {}


class TestPerformanceProfiler:
    """Test PerformanceProfiler class."""
    
    def test_profiler_initialization(self):
        """Test profiler initialization."""
        profiler = PerformanceProfiler()
        assert profiler.process is not None
        assert profiler._start_time is None
        assert profiler._start_memory is None
        assert profiler._start_cpu is None
        assert profiler._peak_memory == 0
    
    @patch('benchmarks.performance_suite.tracemalloc')
    @patch('benchmarks.performance_suite.time.perf_counter')
    def test_profiler_context_manager_success(self, mock_time, mock_tracemalloc):
        """Test profiler context manager with successful operation."""
        profiler = PerformanceProfiler()
        mock_time.side_effect = [0.0, 0.1]  # start, end times
        mock_tracemalloc.get_traced_memory.return_value = (1024*1024, 2*1024*1024)  # 1MB, 2MB
        
        # Mock process memory info
        profiler.process.memory_info = Mock(return_value=Mock(rss=50*1024*1024))  # 50MB
        profiler.process.cpu_percent = Mock(return_value=10.0)
        
        with profiler.profile("test_stage"):
            pass  # Simulate work
        
        mock_tracemalloc.start.assert_called_once()
        mock_tracemalloc.stop.assert_called_once()
    
    @patch('benchmarks.performance_suite.tracemalloc')
    @patch('benchmarks.performance_suite.time.perf_counter')
    def test_profiler_context_manager_exception(self, mock_time, mock_tracemalloc):
        """Test profiler context manager with exception."""
        profiler = PerformanceProfiler()
        mock_time.side_effect = [0.0, 0.1]
        mock_tracemalloc.get_traced_memory.return_value = (1024*1024, 2*1024*1024)
        
        profiler.process.memory_info = Mock(return_value=Mock(rss=50*1024*1024))
        profiler.process.cpu_percent = Mock(return_value=10.0)
        
        with pytest.raises(ValueError):
            with profiler.profile("test_stage"):
                raise ValueError("Test error")
        
        mock_tracemalloc.start.assert_called_once()
        mock_tracemalloc.stop.assert_called_once()


class TestPerformanceBenchmark:
    """Test PerformanceBenchmark class."""
    
    def test_benchmark_initialization_default(self):
        """Test benchmark initialization with default output directory."""
        benchmark = PerformanceBenchmark()
        assert benchmark.output_dir == Path("benchmark_results")
        assert isinstance(benchmark.profiler, PerformanceProfiler)
        assert benchmark.results == []
    
    def test_benchmark_initialization_custom_dir(self):
        """Test benchmark initialization with custom output directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            benchmark = PerformanceBenchmark(temp_dir)
            assert benchmark.output_dir == Path(temp_dir)
    
    @patch('benchmarks.performance_suite.parse_midi_to_frames')
    def test_benchmark_parse_stage(self, mock_parse):
        """Test benchmarking parse stage."""
        benchmark = PerformanceBenchmark()
        mock_parse.return_value = {"events": [], "meta": {}}
        
        with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as temp_file:
            temp_file.write(b"fake midi data")
            temp_path = temp_file.name
        
        try:
            # Mock the profiler methods that are called
            with patch.object(benchmark.profiler, '_start_profiling') as mock_start, \
                 patch.object(benchmark.profiler, '_end_profiling') as mock_end:
                
                mock_end.return_value = BenchmarkResult("parse", 100.0, 50.0, 10.0, 15.0, True)
                
                result, profile_result = benchmark.benchmark_parse_stage(temp_path)
                assert result == {"events": [], "meta": {}}
                mock_parse.assert_called_once_with(temp_path)
                assert profile_result.stage == "parse"
        finally:
            os.unlink(temp_path)
    
    @patch('benchmarks.performance_suite.assign_tracks_to_nes_channels')
    def test_benchmark_map_stage(self, mock_assign):
        """Test benchmarking map stage."""
        benchmark = PerformanceBenchmark()
        mock_assign.return_value = {"mapped": "data"}
        
        parsed_data = {"events": []}
        
        # Mock the profiler methods that are called
        with patch.object(benchmark.profiler, '_start_profiling') as mock_start, \
             patch.object(benchmark.profiler, '_end_profiling') as mock_end:
            
            mock_end.return_value = BenchmarkResult("map", 50.0, 30.0, 5.0, 12.0, True)
            
            result, profile_result = benchmark.benchmark_map_stage(parsed_data)
            assert result == {"mapped": "data"}
            assert profile_result.stage == "map"
    
    @patch('benchmarks.performance_suite.NESEmulatorCore')
    def test_benchmark_frames_stage(self, mock_emulator_class):
        """Test benchmarking frames stage."""
        benchmark = PerformanceBenchmark()
        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {"frames": "data"}
        mock_emulator_class.return_value = mock_emulator
        
        mapped_data = {"mapped": "data"}
        
        # Mock the profiler methods that are called
        with patch.object(benchmark.profiler, '_start_profiling') as mock_start, \
             patch.object(benchmark.profiler, '_end_profiling') as mock_end:
            
            mock_end.return_value = BenchmarkResult("frames", 80.0, 40.0, 8.0, 18.0, True)
            
            result, profile_result = benchmark.benchmark_frames_stage(mapped_data)
            assert result == {"frames": "data"}
            mock_emulator.process_all_tracks.assert_called_once_with(mapped_data)
            assert profile_result.stage == "frames"
    
    @patch('benchmarks.performance_suite.EnhancedPatternDetector')
    @patch('benchmarks.performance_suite.EnhancedTempoMap')
    def test_benchmark_pattern_detection(self, mock_tempo_map_class, mock_detector_class):
        """Test benchmarking pattern detection."""
        benchmark = PerformanceBenchmark()
        
        # Mock detector
        mock_detector = Mock()
        mock_detector.detect_patterns.return_value = {"patterns": {}, "references": {}, "stats": {}}
        mock_detector_class.return_value = mock_detector
        
        # Mock tempo map
        mock_tempo_map = Mock()
        mock_tempo_map_class.return_value = mock_tempo_map
        
        frames_data = {
            "channel1": {
                "0": {"note": 60, "volume": 100},
                "1": {"note": 62, "volume": 90}
            }
        }
        
        # Mock the profiler methods that are called
        with patch.object(benchmark.profiler, '_start_profiling') as mock_start, \
             patch.object(benchmark.profiler, '_end_profiling') as mock_end:
            
            mock_end.return_value = BenchmarkResult("pattern_detection", 120.0, 60.0, 12.0, 20.0, True)
            
            result, profile_result = benchmark.benchmark_pattern_detection(frames_data)
            assert result == {"patterns": {}, "references": {}, "stats": {}}
            mock_detector.detect_patterns.assert_called_once()
            assert profile_result.stage == "pattern_detection"
    
    @patch('benchmarks.performance_suite.CA65Exporter')
    def test_benchmark_export_stage(self, mock_exporter_class):
        """Test benchmarking export stage."""
        benchmark = PerformanceBenchmark()
        
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter
        
        frames_data = {"frames": "data"}
        patterns_data = {"patterns": {}, "references": {}}
        
        # Mock the profiler methods that are called
        with patch.object(benchmark.profiler, '_start_profiling') as mock_start, \
             patch.object(benchmark.profiler, '_end_profiling') as mock_end:
            
            mock_end.return_value = BenchmarkResult("export", 90.0, 45.0, 9.0, 16.0, True)
            
            with patch('tempfile.NamedTemporaryFile') as mock_temp:
                mock_file = Mock()
                mock_file.name = "temp_export.s"
                mock_temp.return_value.__enter__.return_value = mock_file
                
                with patch('os.path.exists', return_value=True), \
                     patch('os.unlink') as mock_unlink:
                    
                    result, profile_result = benchmark.benchmark_export_stage(frames_data, patterns_data)
                    mock_exporter.export_tables_with_patterns.assert_called_once()
                    assert profile_result.stage == "export"
    
    def test_benchmark_stage_function_wrapper(self):
        """Test the generic benchmark_pipeline_stage method."""
        benchmark = PerformanceBenchmark()
        
        def test_function(x, y=None):
            return x * 2 if y is None else x + y
        
        with patch.object(benchmark.profiler, 'profile') as mock_profile:
            mock_profile.return_value.__enter__ = Mock()
            mock_profile.return_value.__exit__ = Mock(return_value=None)
            
            result = benchmark.benchmark_pipeline_stage(test_function, "test_stage", 5)
            assert result == 10
            
            result = benchmark.benchmark_pipeline_stage(test_function, "test_stage", 5, y=3)
            assert result == 8


class TestBenchmarkIntegration:
    """Test benchmark integration and complete workflows."""
    
    def test_empty_results_generate_report(self):
        """Test generating report with no results."""
        benchmark = PerformanceBenchmark()
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Should not crash with empty results
            benchmark.generate_report(temp_path)
            # File should not be created if no results
            assert not Path(temp_path).exists() or Path(temp_path).stat().st_size == 0
        finally:
            if Path(temp_path).exists():
                os.unlink(temp_path)
    
    @patch('benchmarks.performance_suite.time.strftime')
    def test_generate_report_with_results(self, mock_strftime):
        """Test generating report with actual results."""
        mock_strftime.return_value = "2024-01-01 12:00:00"
        
        benchmark = PerformanceBenchmark()
        
        # Add mock results
        result1 = PipelineBenchmark(
            file_path="test1.mid",
            file_size_kb=10.0,
            total_duration_ms=100.0,
            total_memory_mb=50.0,
            timestamp="2024-01-01 12:00:00"
        )
        result1.stages = [
            BenchmarkResult("parse", 50.0, 25.0, 5.0, 10.0, True),
            BenchmarkResult("map", 30.0, 20.0, 3.0, 8.0, True),
            BenchmarkResult("frames", 20.0, 15.0, 2.0, 5.0, True)
        ]
        
        result2 = PipelineBenchmark(
            file_path="test2.mid", 
            file_size_kb=20.0,
            total_duration_ms=200.0,
            total_memory_mb=75.0,
            timestamp="2024-01-01 12:01:00"
        )
        result2.stages = [
            BenchmarkResult("parse", 100.0, 40.0, 8.0, 15.0, True),
            BenchmarkResult("map", 60.0, 30.0, 5.0, 12.0, False, "Test error"),
            BenchmarkResult("frames", 40.0, 25.0, 4.0, 8.0, True)
        ]
        
        benchmark.results = [result1, result2]
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            with patch('builtins.print') as mock_print:
                report = benchmark.generate_report(temp_path)
                
                # Verify report structure
                assert report is not None
                assert "benchmark_info" in report
                assert "summary_statistics" in report
                assert "detailed_results" in report
                
                # Verify benchmark info
                benchmark_info = report["benchmark_info"]
                assert benchmark_info["total_files_tested"] == 2
                assert benchmark_info["successful_runs"] == 1  # Only result1 has all successful stages
                assert benchmark_info["success_rate"] == 0.5
                
                # Verify file was created and contains valid JSON
                assert Path(temp_path).exists()
                with open(temp_path) as f:
                    saved_report = json.load(f)
                    assert saved_report == report
                
                # Verify console output was generated
                mock_print.assert_called()
                
        finally:
            if Path(temp_path).exists():
                os.unlink(temp_path)


class TestBenchmarkErrorHandling:
    """Test error handling in benchmark operations."""
    
    def test_benchmark_with_missing_file(self):
        """Test benchmarking with non-existent file."""
        benchmark = PerformanceBenchmark()
        
        with pytest.raises(FileNotFoundError):
            benchmark.run_full_pipeline("nonexistent_file.mid")
    
    @patch('benchmarks.performance_suite.parse_midi_to_frames')
    def test_benchmark_parse_stage_exception(self, mock_parse):
        """Test handling exceptions in parse stage."""
        benchmark = PerformanceBenchmark()
        mock_parse.side_effect = Exception("Parse failed")
        
        with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as temp_file:
            temp_file.write(b"fake midi data")
            temp_path = temp_file.name
        
        try:
            with pytest.raises(Exception, match="Parse failed"):
                benchmark.benchmark_parse_stage(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_benchmark_directory_creation(self):
        """Test that benchmark creates output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as parent_dir:
            benchmark_dir = Path(parent_dir) / "new_benchmark_dir"
            benchmark = PerformanceBenchmark(str(benchmark_dir))
            
            # Directory should be created during initialization
            assert benchmark_dir.exists()


if __name__ == "__main__":
    pytest.main([__file__])
