"""Comprehensive tests for DPCM Sample Manager.

Tests cover:
- Sample allocation and memory management
- Usage statistics and optimization
- Memory constraints and limits
- Sample bank optimization algorithms
- Edge cases and error conditions

The sample similarity/dedup machinery was removed (#71/D-08): the shipped index
only carries id/filename, so length/data/frequency always defaulted and every
pair scored 100% similar, making the dedup inert on real input.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add the parent directory to the path to import modules
sys.path.append(str(Path(__file__).parent.parent))

from dpcm_sampler.dpcm_sample_manager import DPCMSampleManager


class TestDPCMSampleManagerBasics:
    """Test basic functionality and initialization."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DPCMSampleManager(max_samples=4, memory_limit=2048)
        
        self.sample_data_kick = {
            'data': [0x80, 0x90, 0xA0, 0xB0] * 64,  # 256 bytes
            'length': 256,
            'frequency': 33144
        }
        
        self.sample_data_snare = {
            'data': [0xC0, 0xD0, 0xE0, 0xF0] * 32,  # 128 bytes
            'length': 128,
            'frequency': 33144
        }
        
        self.sample_data_hihat = {
            'data': [0x40, 0x50, 0x60, 0x70] * 16,  # 64 bytes
            'length': 64,
            'frequency': 33144
        }
    
    def test_initialization(self):
        """Test DPCM Sample Manager initialization."""
        manager = DPCMSampleManager()
        
        assert manager.max_samples == 16  # Default
        assert manager.memory_limit == 4096  # Default
        assert manager.active_samples == {}
        assert manager.usage_stats == {}
        # The similarity/dedup machinery (sample_cache / sample_similarities)
        # was removed as inert on real input (#71/D-08).
        assert not hasattr(manager, "sample_cache")
        assert not hasattr(manager, "sample_similarities")

    def test_custom_initialization(self):
        """Test initialization with custom parameters."""
        manager = DPCMSampleManager(max_samples=8, memory_limit=1024)
        
        assert manager.max_samples == 8
        assert manager.memory_limit == 1024
        assert manager.active_samples == {}
    
    def test_basic_sample_allocation(self):
        """Test basic sample allocation."""
        result = self.manager.allocate_sample("kick", self.sample_data_kick)
        
        assert result['id'] == 0
        assert result['name'] == "kick"
        assert result['data'] == self.sample_data_kick['data']
        assert result['metadata']['size'] == 256
        assert result['metadata']['frequency'] == 33144
        assert result['metadata']['original_name'] == "kick"
        
        # Check that sample is stored in active samples
        assert "kick" in self.manager.active_samples
        assert self.manager.usage_stats["kick"] == 1
    
    def test_duplicate_sample_allocation(self):
        """Test allocating the same sample multiple times."""
        result1 = self.manager.allocate_sample("kick", self.sample_data_kick)
        result2 = self.manager.allocate_sample("kick", self.sample_data_kick)
        
        # Should return the same sample info
        assert result1 == result2
        assert result1 is result2  # Same object reference
        assert self.manager.usage_stats["kick"] == 2  # Usage count increased


class TestSampleAllocationAndMemoryManagement:
    """Test sample allocation with memory constraints."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DPCMSampleManager(max_samples=4, memory_limit=512)  # Small memory limit
        
        self.sample_data_large = {
            'data': [0xFF] * 400,  # 400 bytes - exceeds memory limit alone
            'length': 400,
            'frequency': 33144
        }
        
        self.sample_data_medium = {
            'data': [0xAA] * 200,  # 200 bytes
            'length': 200,
            'frequency': 33144
        }
        
        self.sample_data_small = {
            'data': [0x55] * 100,  # 100 bytes
            'length': 100,
            'frequency': 33144
        }
    
    def test_memory_limit_enforcement(self):
        """Test that memory limits are enforced."""
        # Allocate samples that exceed memory limit
        self.manager.allocate_sample("medium1", self.sample_data_medium)  # 200 bytes
        self.manager.allocate_sample("medium2", self.sample_data_medium)  # 200 bytes
        
        # This should trigger optimization since 200 + 200 + 200 > 512
        with patch.object(self.manager, '_optimize_sample_bank') as mock_optimize:
            self.manager.allocate_sample("medium3", self.sample_data_medium)
            mock_optimize.assert_called_once()
    
    def test_sample_count_limit(self):
        """Test that sample count limits are enforced."""
        # Fill up to max samples
        for i in range(4):
            self.manager.allocate_sample(f"sample{i}", self.sample_data_small)
        
        assert len(self.manager.active_samples) == 4
        
        # Adding one more (at capacity) must force-evict to make room.
        with patch.object(self.manager, '_optimize_sample_bank') as mock_optimize:
            self.manager.allocate_sample("sample5", self.sample_data_small)
            mock_optimize.assert_called_with(force=True)
    
    def test_default_sample_values(self):
        """Test allocation with missing data fields."""
        minimal_sample = {}  # No data fields
        
        result = self.manager.allocate_sample("minimal", minimal_sample)
        
        assert result['data'] == []  # Default empty list
        assert result['metadata']['size'] == 1024  # Default size
        assert result['metadata']['frequency'] == 33144  # Default frequency
        assert result['metadata']['original_name'] == "minimal"


class TestSampleBankOptimization:
    """Test sample bank optimization algorithms."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DPCMSampleManager(max_samples=3, memory_limit=1000)
        
        # Create samples with different usage patterns
        self.frequently_used = {
            'data': [0x11] * 100,
            'length': 100,
            'frequency': 33144
        }
        
        self.rarely_used = {
            'data': [0x22] * 200,  # Larger size
            'length': 200,
            'frequency': 33144
        }
        
        self.medium_used = {
            'data': [0x33] * 50,  # Smaller size
            'length': 50,
            'frequency': 33144
        }
    
    def test_optimization_scoring(self):
        """Test that optimization uses correct scoring algorithm."""
        # Allocate samples with different usage patterns
        self.manager.allocate_sample("frequent", self.frequently_used)
        for _ in range(10):  # Use frequently
            self.manager.allocate_sample("frequent", self.frequently_used)
        
        self.manager.allocate_sample("rare", self.rarely_used)  # Use once
        
        self.manager.allocate_sample("medium", self.medium_used)
        for _ in range(3):  # Use moderately
            self.manager.allocate_sample("medium", self.medium_used)
        
        # Force optimization
        self.manager._optimize_sample_bank(force=True)
        
        # Frequently used sample should still be active
        assert "frequent" in self.manager.active_samples
        
        # Check that optimization considers usage statistics
        assert self.manager.usage_stats["frequent"] == 11
        assert self.manager.usage_stats["rare"] == 1
        assert self.manager.usage_stats["medium"] == 4
    
    def test_optimization_memory_pressure(self):
        """Test optimization under memory pressure."""
        # Fill memory close to limit
        self.manager.allocate_sample("sample1", self.rarely_used)    # 200 bytes
        self.manager.allocate_sample("sample2", self.rarely_used)    # 200 bytes
        self.manager.allocate_sample("sample3", self.rarely_used)    # 200 bytes
        # Total: 600 bytes
        
        # This should trigger memory-based optimization
        large_sample = {
            'data': [0x44] * 500,  # 500 bytes - would exceed memory limit
            'length': 500,
            'frequency': 33144
        }
        
        with patch.object(self.manager, '_optimize_sample_bank') as mock_optimize:
            self.manager.allocate_sample("large", large_sample)
            mock_optimize.assert_called()
    
    def test_no_optimization_when_under_limits(self):
        """Test that optimization doesn't run when under limits."""
        # Add a small sample
        self.manager.allocate_sample("small", self.medium_used)
        
        # Should not trigger optimization
        with patch.object(self.manager, '_optimize_sample_bank') as mock_optimize:
            # Call optimization directly with force=False
            self.manager._optimize_sample_bank(force=False)
            # The method should return early without doing anything
            pass  # Method doesn't do anything when under limits
    
    def test_sample_removal_during_optimization(self):
        """Test that samples are properly removed during optimization."""
        # Fill to capacity
        for i in range(3):
            self.manager.allocate_sample(f"sample{i}", self.medium_used)
        
        assert len(self.manager.active_samples) == 3
        
        # Manually test sample removal
        self.manager._remove_sample("sample0")
        
        assert "sample0" not in self.manager.active_samples
        assert len(self.manager.active_samples) == 2


class TestSimilarityMachineryRemoved:
    """Regression (#71/D-08): the similarity/dedup machinery was removed because
    it was inert on real input. Pin that it is gone and that allocation at
    capacity still works (evict-and-allocate) without any dedup reuse."""

    def test_similarity_methods_and_state_are_gone(self):
        manager = DPCMSampleManager()
        for attr in ("sample_cache", "sample_similarities"):
            assert not hasattr(manager, attr), f"{attr} should be removed"
        for method in ("_find_similar_sample", "_update_similarities",
                       "_calculate_sample_similarity"):
            assert not hasattr(manager, method), f"{method} should be removed"

    def test_identical_samples_are_not_deduplicated(self):
        """Two identically-shaped samples must each allocate independently now —
        the old code could collapse them via the (inert) similarity path."""
        manager = DPCMSampleManager(max_samples=4, memory_limit=4096)
        data = {'data': [0x10, 0x20, 0x30, 0x40] * 25, 'length': 100, 'frequency': 33144}
        a = manager.allocate_sample("a", data)
        b = manager.allocate_sample("b", dict(data))
        assert a['name'] == "a"
        assert b['name'] == "b"
        assert a is not b
        assert set(manager.active_samples) == {"a", "b"}

    def test_allocation_at_capacity_evicts_and_allocates(self):
        """At capacity, a new sample forces optimization (eviction) then
        allocates — the removed similarity-reuse shortcut no longer intercepts."""
        manager = DPCMSampleManager(max_samples=2, memory_limit=4096)
        small = {'data': [0x55] * 40, 'length': 40, 'frequency': 33144}
        manager.allocate_sample("s0", small)
        manager.allocate_sample("s1", small)
        result = manager.allocate_sample("s2", small)
        assert result['name'] == "s2"
        assert "s2" in manager.active_samples
        assert len(manager.active_samples) <= manager.max_samples


class TestMemoryCalculations:
    """Test memory usage calculations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DPCMSampleManager()
    
    def test_total_memory_calculation(self):
        """Test total memory usage calculation."""
        # Initially should be 0
        assert self.manager._get_total_memory() == 0
        
        # Add a sample with known data size
        sample_data = {
            'data': [0x11] * 80,  # 80 bytes -> 10 bytes after //8
            'length': 80
        }
        
        self.manager.allocate_sample("test", sample_data)
        
        # Should calculate memory based on data length divided by 8
        expected_memory = 80 // 8  # 10 bytes
        assert self.manager._get_total_memory() == expected_memory
    
    def test_memory_calculation_with_multiple_samples(self):
        """Test memory calculation with multiple samples."""
        sample1 = {'data': [0x11] * 40, 'length': 40}  # 5 bytes
        sample2 = {'data': [0x22] * 80, 'length': 80}  # 10 bytes
        sample3 = {'data': [0x33] * 120, 'length': 120}  # 15 bytes
        
        self.manager.allocate_sample("sample1", sample1)
        self.manager.allocate_sample("sample2", sample2)
        self.manager.allocate_sample("sample3", sample3)
        
        expected_total = (40 + 80 + 120) // 8  # 30 bytes
        assert self.manager._get_total_memory() == expected_total
    
    def test_memory_calculation_with_empty_data(self):
        """Test memory calculation with empty or missing data."""
        empty_sample = {}  # No data field
        
        self.manager.allocate_sample("empty", empty_sample)
        
        # Should handle missing data gracefully
        memory = self.manager._get_total_memory()
        assert memory >= 0  # Should not crash


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DPCMSampleManager(max_samples=2, memory_limit=500)
    
    def test_allocate_sample_with_none_data(self):
        """Test allocation with None or missing data."""
        result = self.manager.allocate_sample("none_data", {})
        
        # Should handle gracefully with defaults
        assert result['data'] == []
        assert result['metadata']['size'] == 1024  # Default
        assert result['name'] == "none_data"
    
    def test_allocate_sample_with_invalid_frequency(self):
        """Test allocation with missing or invalid frequency."""
        sample_no_freq = {
            'data': [0x11] * 50,
            'length': 50
            # No frequency field
        }
        
        result = self.manager.allocate_sample("no_freq", sample_no_freq)
        
        # Should use default frequency
        assert result['metadata']['frequency'] == 33144
    
    def test_remove_nonexistent_sample(self):
        """Test removing a sample that doesn't exist."""
        # Should not crash when removing non-existent sample
        self.manager._remove_sample("nonexistent")
        
        # State should remain consistent
        assert len(self.manager.active_samples) == 0

    def test_optimization_with_empty_sample_bank(self):
        """Test optimization when no samples are active."""
        # Should not crash when optimizing empty bank
        self.manager._optimize_sample_bank(force=True)
        
        # State should remain consistent
        assert len(self.manager.active_samples) == 0
    
    def test_usage_statistics_persistence(self):
        """Test that usage statistics persist across operations."""
        sample_data = {'data': [0x11] * 50, 'length': 50}
        
        # Use sample multiple times
        for i in range(5):
            self.manager.allocate_sample("persistent", sample_data)
        
        assert self.manager.usage_stats["persistent"] == 5
        
        # Usage should persist even after optimization
        self.manager._optimize_sample_bank(force=True)
        assert self.manager.usage_stats["persistent"] == 5


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DPCMSampleManager(max_samples=4, memory_limit=1000)
    
    def test_realistic_drum_sample_scenario(self):
        """Test realistic drum sample usage scenario."""
        # Create realistic drum samples
        kick_sample = {
            'data': [0x80, 0x90, 0xA0, 0xB0] * 60,  # 240 bytes
            'length': 240,
            'frequency': 33144
        }
        
        snare_sample = {
            'data': [0xC0, 0xD0, 0xE0, 0xF0] * 40,  # 160 bytes
            'length': 160,
            'frequency': 33144
        }
        
        hihat_sample = {
            'data': [0x40, 0x50, 0x60, 0x70] * 20,  # 80 bytes
            'length': 80,
            'frequency': 33144
        }
        
        # Simulate realistic usage pattern
        # Kick drum used frequently
        for _ in range(8):
            result_kick = self.manager.allocate_sample("kick", kick_sample)
            assert result_kick['name'] == "kick"
        
        # Snare used moderately
        for _ in range(4):
            result_snare = self.manager.allocate_sample("snare", snare_sample)
            assert result_snare['name'] == "snare"
        
        # Hi-hat used occasionally
        for _ in range(2):
            result_hihat = self.manager.allocate_sample("hihat", hihat_sample)
            assert result_hihat['name'] == "hihat"
        
        # Check final state
        assert len(self.manager.active_samples) == 3
        assert self.manager.usage_stats["kick"] == 8
        assert self.manager.usage_stats["snare"] == 4
        assert self.manager.usage_stats["hihat"] == 2
        
        # Total memory should be managed
        total_memory = self.manager._get_total_memory()
        assert total_memory <= self.manager.memory_limit
    
    def test_memory_pressure_recovery(self):
        """Test system recovery under memory pressure."""
        # Create large samples that will exceed memory
        large_samples = []
        for i in range(5):
            large_sample = {
                'data': [0x10 + i] * 300,  # 300 bytes each
                'length': 300,
                'frequency': 33144
            }
            large_samples.append(large_sample)
        
        # Allocate samples - should trigger optimization
        allocated_samples = []
        for i, sample_data in enumerate(large_samples):
            try:
                result = self.manager.allocate_sample(f"large_{i}", sample_data)
                allocated_samples.append(result)
            except Exception as e:
                pytest.fail(f"Sample allocation failed: {str(e)}")
        
        # System should have managed memory automatically
        assert len(self.manager.active_samples) <= self.manager.max_samples
        
        # Should still be able to allocate new samples
        new_sample = {
            'data': [0xFF] * 100,
            'length': 100,
            'frequency': 33144
        }
        
        result = self.manager.allocate_sample("recovery_test", new_sample)
        assert result['name'] == "recovery_test"
    
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
