"""Tests for memory and performance profiling utilities."""

import pytest
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys
import threading

# Add the parent directory to the path to import modules
sys.path.append(str(Path(__file__).parent.parent))

from utils.profiling import (
    ProfileResult,
    MemoryMonitor,
    ProfilerRegistry,
    profile_memory_usage,
    profile_memory_simple,
    PerformanceContext,
    get_memory_usage,
    log_memory_usage,
    clear_profiler_registry,
    export_profiler_registry,
    get_profiler_registry,
    monitor_performance
)


class TestProfileResult:
    """Test ProfileResult dataclass."""
    
    def test_profile_result_creation(self):
        """Test creating a profile result."""
        result = ProfileResult(
            function_name="test_function",
            duration_ms=100.5,
            memory_before_mb=50.0,
            memory_after_mb=60.0,
            memory_peak_mb=65.0,
            memory_delta_mb=10.0,
            cpu_percent=15.5,
            success=True,
            error_message="",
            metadata={"test": "data"}
        )
        
        assert result.function_name == "test_function"
        assert result.duration_ms == 100.5
        assert result.memory_before_mb == 50.0
        assert result.memory_after_mb == 60.0
        assert result.memory_peak_mb == 65.0
        assert result.memory_delta_mb == 10.0
        assert result.cpu_percent == 15.5
        assert result.success is True
        assert result.error_message == ""
        assert result.metadata == {"test": "data"}
    
    def test_profile_result_defaults(self):
        """Test profile result with default values."""
        result = ProfileResult(
            function_name="test",
            duration_ms=100,
            memory_before_mb=50,
            memory_after_mb=60,
            memory_peak_mb=65,
            memory_delta_mb=10,
            cpu_percent=15,
            success=True
        )
        
        assert result.error_message == ""
        assert result.metadata == {}


class TestMemoryMonitor:
    """Test MemoryMonitor class."""
    
    def test_memory_monitor_initialization(self):
        """Test memory monitor initialization."""
        monitor = MemoryMonitor(interval_ms=200)
        assert monitor.interval_ms == 200
        assert monitor.process is not None
        assert monitor._monitoring is False
        assert monitor._monitor_thread is None
        assert monitor._peak_memory == 0
        assert monitor._memory_samples == []
    
    def test_memory_monitor_default_interval(self):
        """Test memory monitor with default interval."""
        monitor = MemoryMonitor()
        assert monitor.interval_ms == 100
    
    @patch('utils.profiling.psutil.Process')
    def test_start_monitoring(self, mock_process_class):
        """Test starting memory monitoring."""
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 50 * 1024 * 1024  # 50MB
        mock_process_class.return_value = mock_process
        
        monitor = MemoryMonitor(interval_ms=10)  # Very short interval for testing
        
        assert not monitor._monitoring
        monitor.start_monitoring()
        assert monitor._monitoring
        assert monitor._monitor_thread is not None
        assert monitor._monitor_thread.daemon is True
        
        # Clean up
        monitor.stop_monitoring()
    
    @patch('utils.profiling.psutil.Process')
    def test_stop_monitoring_no_samples(self, mock_process_class):
        """Test stopping monitoring with no samples."""
        mock_process = Mock()
        mock_process_class.return_value = mock_process
        
        monitor = MemoryMonitor()
        stats = monitor.stop_monitoring()
        
        expected = {"peak_mb": 0, "average_mb": 0, "samples": 0}
        assert stats == expected
    
    @patch('utils.profiling.psutil.Process')
    def test_stop_monitoring_with_samples(self, mock_process_class):
        """Test stopping monitoring with samples."""
        monitor = MemoryMonitor()
        monitor._memory_samples = [10.0, 15.0, 20.0, 12.0]
        
        stats = monitor.stop_monitoring()
        
        assert stats["peak_mb"] == 20.0
        assert stats["average_mb"] == 14.25  # (10+15+20+12)/4
        assert stats["samples"] == 4
        assert stats["min_mb"] == 10.0
    
    def test_start_monitoring_already_started(self):
        """Test starting monitoring when already started."""
        monitor = MemoryMonitor()
        monitor._monitoring = True
        
        # Should not create a new thread if already monitoring
        monitor.start_monitoring()
        assert monitor._monitor_thread is None


class TestProfilerRegistry:
    """Test ProfilerRegistry class."""
    
    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = ProfilerRegistry()
        assert registry._profiles == {}
        assert registry._active_monitors == {}
    
    def test_register_profile(self):
        """Test registering a profile."""
        registry = ProfilerRegistry()
        result = ProfileResult(
            function_name="test_func",
            duration_ms=100,
            memory_before_mb=50,
            memory_after_mb=60,
            memory_peak_mb=65,
            memory_delta_mb=10,
            cpu_percent=15,
            success=True
        )
        
        with patch('utils.profiling.time.time', return_value=1234567890):
            registry.register_profile(result)
            
            profiles = registry.get_profiles()
            assert len(profiles) == 1
            assert "test_func_1234567890" in profiles
            assert profiles["test_func_1234567890"] == result
    
    def test_clear_profiles(self):
        """Test clearing profiles."""
        registry = ProfilerRegistry()
        result = ProfileResult("test", 100, 50, 60, 65, 10, 15, True)
        
        registry.register_profile(result)
        assert len(registry.get_profiles()) == 1
        
        registry.clear_profiles()
        assert len(registry.get_profiles()) == 0
    
    def test_export_profiles(self):
        """Test exporting profiles to JSON."""
        registry = ProfilerRegistry()
        result = ProfileResult(
            function_name="test_func",
            duration_ms=100.5,
            memory_before_mb=50.0,
            memory_after_mb=60.0,
            memory_peak_mb=65.0,
            memory_delta_mb=10.0,
            cpu_percent=15.5,
            success=True,
            error_message="test_error",
            metadata={"key": "value"}
        )
        
        with patch('utils.profiling.time.time', return_value=1234567890):
            registry.register_profile(result)
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            registry.export_profiles(temp_path)
            
            with open(temp_path) as f:
                exported_data = json.load(f)
            
            assert "test_func_1234567890" in exported_data
            profile_data = exported_data["test_func_1234567890"]
            assert profile_data["function_name"] == "test_func"
            assert profile_data["duration_ms"] == 100.5
            assert profile_data["success"] is True
            assert profile_data["metadata"] == {"key": "value"}
            
        finally:
            Path(temp_path).unlink()


class TestProfileMemoryUsage:
    """Test profile_memory_usage decorator."""
    
    @patch('utils.profiling.psutil.Process')
    @patch('utils.profiling.tracemalloc')
    @patch('utils.profiling.time.perf_counter')
    def test_profile_memory_usage_success(self, mock_time, mock_tracemalloc, mock_process_class):
        """Test profiling decorator with successful function."""
        # Setup mocks
        mock_time.side_effect = [0.0, 0.1]  # 100ms duration
        mock_tracemalloc.get_traced_memory.return_value = (1024*1024, 2*1024*1024)  # 1MB current, 2MB peak
        
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 50 * 1024 * 1024  # 50MB
        mock_process.cpu_percent.return_value = 10.0
        mock_process_class.return_value = mock_process
        
        @profile_memory_usage(save_to_registry=False)
        def test_function():
            return "success"
        
        with patch('builtins.print') as mock_print:
            result = test_function()
            
            assert result == "success"
            mock_tracemalloc.start.assert_called_once()
            mock_tracemalloc.stop.assert_called_once()
            mock_print.assert_called()  # Should print profiling info
    
    @patch('utils.profiling.psutil.Process')
    @patch('utils.profiling.tracemalloc')
    @patch('utils.profiling.time.perf_counter')
    def test_profile_memory_usage_exception(self, mock_time, mock_tracemalloc, mock_process_class):
        """Test profiling decorator with function that raises exception."""
        mock_time.side_effect = [0.0, 0.1]
        mock_tracemalloc.get_traced_memory.return_value = (1024*1024, 2*1024*1024)
        
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 50 * 1024 * 1024
        mock_process.cpu_percent.return_value = 10.0
        mock_process_class.return_value = mock_process
        
        @profile_memory_usage(save_to_registry=False)
        def failing_function():
            raise ValueError("Test error")
        
        with patch('builtins.print') as mock_print:
            with pytest.raises(ValueError, match="Test error"):
                failing_function()
            
            mock_print.assert_called()  # Should still print profiling info
    
    def test_profile_memory_usage_with_registry(self):
        """Test profiling decorator saving to registry."""
        @profile_memory_usage(save_to_registry=True)
        def test_function():
            return "test"
        
        with patch('utils.profiling._profiler_registry.register_profile') as mock_register:
            result = test_function()
            assert result == "test"
            mock_register.assert_called_once()
    
    def test_profile_memory_usage_with_metadata(self):
        """Test profiling decorator with metadata."""
        metadata = {"stage": "parsing", "file": "test.mid"}
        
        @profile_memory_usage(metadata=metadata, save_to_registry=False)
        def test_function():
            return "test"
        
        with patch('builtins.print'):
            result = test_function()
            assert result == "test"


class TestProfileMemorySimple:
    """Test profile_memory_simple decorator."""
    
    @patch('utils.profiling.psutil.Process')
    @patch('utils.profiling.time.perf_counter')
    def test_profile_memory_simple_success(self, mock_time, mock_process_class):
        """Test simple profiling decorator with successful function."""
        mock_time.side_effect = [0.0, 0.05]  # 50ms duration
        
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 40 * 1024 * 1024  # 40MB
        mock_process_class.return_value = mock_process
        
        @profile_memory_simple
        def test_function():
            return "success"
        
        with patch('builtins.print') as mock_print:
            result = test_function()
            
            assert result == "success"
            mock_print.assert_called_once()
            # Check that the print call contains success indicator and timing
            call_args = str(mock_print.call_args)
            assert "✓" in call_args or "test_function" in call_args
    
    @patch('utils.profiling.psutil.Process')
    @patch('utils.profiling.time.perf_counter')
    def test_profile_memory_simple_exception(self, mock_time, mock_process_class):
        """Test simple profiling decorator with function that raises exception."""
        mock_time.side_effect = [0.0, 0.05]
        
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 40 * 1024 * 1024
        mock_process_class.return_value = mock_process
        
        @profile_memory_simple
        def failing_function():
            raise RuntimeError("Test failure")
        
        with patch('builtins.print') as mock_print:
            with pytest.raises(RuntimeError, match="Test failure"):
                failing_function()
            
            mock_print.assert_called_once()
            # Check that the print call contains failure indicator
            call_args = str(mock_print.call_args)
            assert "✗" in call_args or "failing_function" in call_args


class TestPerformanceContext:
    """Test PerformanceContext class."""
    
    @patch('utils.profiling.psutil.Process')
    def test_performance_context_initialization(self, mock_process_class):
        """Test performance context initialization."""
        mock_process = Mock()
        mock_process_class.return_value = mock_process
        
        context = PerformanceContext("test_operation", print_results=True)
        assert context.name == "test_operation"
        assert context.print_results is True
        assert context.process == mock_process
        assert isinstance(context.monitor, MemoryMonitor)
        assert context.start_time is None
        assert context.start_memory is None
    
    @patch('utils.profiling.psutil.Process')
    @patch('utils.profiling.tracemalloc')
    @patch('utils.profiling.time.perf_counter')
    def test_performance_context_success(self, mock_time, mock_tracemalloc, mock_process_class):
        """Test performance context with successful operation."""
        mock_time.side_effect = [0.0, 0.2]  # 200ms duration
        mock_tracemalloc.get_traced_memory.return_value = (1024*1024, 3*1024*1024)
        
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 60 * 1024 * 1024
        mock_process_class.return_value = mock_process
        
        with patch('builtins.print') as mock_print:
            with PerformanceContext("test_operation") as context:
                pass  # Simulate work
            
            assert context.success is True
            assert context.duration_ms == 200.0
            mock_print.assert_called_once()
            
            # Check output format
            call_args = str(mock_print.call_args)
            assert "✓" in call_args
            assert "test_operation" in call_args
    
    @patch('utils.profiling.psutil.Process')
    @patch('utils.profiling.tracemalloc')
    @patch('utils.profiling.time.perf_counter')
    def test_performance_context_exception(self, mock_time, mock_tracemalloc, mock_process_class):
        """Test performance context with exception."""
        mock_time.side_effect = [0.0, 0.1]
        mock_tracemalloc.get_traced_memory.return_value = (1024*1024, 2*1024*1024)
        
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 50 * 1024 * 1024
        mock_process_class.return_value = mock_process
        
        with patch('builtins.print') as mock_print:
            with pytest.raises(ValueError):
                with PerformanceContext("test_operation") as context:
                    raise ValueError("Test error")
            
            assert context.success is False
            mock_print.assert_called_once()
            
            call_args = str(mock_print.call_args)
            assert "✗" in call_args
    
    def test_performance_context_no_print(self):
        """Test performance context with printing disabled."""
        with patch('builtins.print') as mock_print:
            with PerformanceContext("test_operation", print_results=False):
                pass
            
            mock_print.assert_not_called()


class TestUtilityFunctions:
    """Test utility functions."""
    
    @patch('utils.profiling.psutil.Process')
    @patch('utils.profiling.psutil.virtual_memory')
    def test_get_memory_usage(self, mock_virtual_memory, mock_process_class):
        """Test get_memory_usage function."""
        # Mock process memory info
        mock_process = Mock()
        mock_memory_info = Mock()
        mock_memory_info.rss = 100 * 1024 * 1024  # 100MB
        mock_memory_info.vms = 200 * 1024 * 1024  # 200MB
        mock_process.memory_info.return_value = mock_memory_info
        mock_process.memory_percent.return_value = 5.5
        mock_process_class.return_value = mock_process
        
        # Mock system virtual memory
        mock_vm = Mock()
        mock_vm.available = 1024 * 1024 * 1024  # 1GB
        mock_virtual_memory.return_value = mock_vm
        
        usage = get_memory_usage()
        
        assert usage["rss_mb"] == 100.0
        assert usage["vms_mb"] == 200.0
        assert usage["percent"] == 5.5
        assert usage["available_mb"] == 1024.0
    
    @patch('utils.profiling.get_memory_usage')
    def test_log_memory_usage(self, mock_get_memory):
        """Test log_memory_usage function."""
        mock_get_memory.return_value = {
            "rss_mb": 75.5,
            "percent": 3.2
        }
        
        with patch('builtins.print') as mock_print:
            log_memory_usage("Test Prefix")
            
            mock_print.assert_called_once()
            call_args = str(mock_print.call_args)
            assert "Test Prefix" in call_args
            assert "75.5MB" in call_args
            assert "3.2%" in call_args
    
    def test_log_memory_usage_no_prefix(self):
        """Test log_memory_usage without prefix."""
        with patch('utils.profiling.get_memory_usage') as mock_get_memory:
            mock_get_memory.return_value = {"rss_mb": 50.0, "percent": 2.0}
            
            with patch('builtins.print') as mock_print:
                log_memory_usage()
                
                call_args = str(mock_print.call_args)
                assert "[MEMORY]" in call_args
                assert ": " not in call_args.split("[MEMORY]")[1].split("50.0MB")[0]


class TestGlobalRegistry:
    """Test global registry functions."""
    
    def test_clear_profiler_registry(self):
        """Test clearing global profiler registry."""
        # Add something to registry first
        with patch('utils.profiling._profiler_registry') as mock_registry:
            clear_profiler_registry()
            mock_registry.clear_profiles.assert_called_once()
    
    def test_export_profiler_registry(self):
        """Test exporting global profiler registry."""
        output_path = "test_profiles.json"
        
        with patch('utils.profiling._profiler_registry') as mock_registry:
            export_profiler_registry(output_path)
            mock_registry.export_profiles.assert_called_once_with(output_path)
    
    def test_get_profiler_registry(self):
        """Test getting global profiler registry."""
        expected_profiles = {"test": "data"}
        
        with patch('utils.profiling._profiler_registry') as mock_registry:
            mock_registry.get_profiles.return_value = expected_profiles
            
            profiles = get_profiler_registry()
            assert profiles == expected_profiles
            mock_registry.get_profiles.assert_called_once()
    
    def test_monitor_performance(self):
        """Test monitor_performance function."""
        context = monitor_performance("test_op", print_results=False)
        assert isinstance(context, PerformanceContext)
        assert context.name == "test_op"
        assert context.print_results is False


class TestIntegration:
    """Test integration scenarios."""
    
    def test_decorator_with_registry_integration(self):
        """Test that decorator properly integrates with registry."""
        clear_profiler_registry()  # Start clean
        
        @profile_memory_usage(save_to_registry=True)
        def test_function():
            return "test_result"
        
        result = test_function()
        assert result == "test_result"
        
        # Check that profile was saved to registry
        profiles = get_profiler_registry()
        assert len(profiles) >= 1
        
        # Clear for next test
        clear_profiler_registry()
    
    def test_multiple_profiles_in_registry(self):
        """Test multiple profiles in registry."""
        clear_profiler_registry()
        
        @profile_memory_usage(save_to_registry=True)
        def func1():
            return 1
        
        @profile_memory_usage(save_to_registry=True) 
        def func2():
            return 2
        
        func1()
        func2()
        
        profiles = get_profiler_registry()
        assert len(profiles) == 2
        
        clear_profiler_registry()


if __name__ == "__main__":
    pytest.main([__file__])
