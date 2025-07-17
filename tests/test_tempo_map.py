"""
Comprehensive tests for Enhanced TempoMap implementation
Tests both backward compatibility and new features
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker.tempo_map import (
    TempoMap, EnhancedTempoMap, TempoValidationConfig,
    TempoChangeType, TempoValidationError,
    TempoChange
)
from constants import FRAME_MS, FRAME_RATE_HZ


class TestTempoMap(unittest.TestCase):
    """Test cases for base TempoMap class - ensure backward compatibility"""
    
    def setUp(self):
        self.tempo_map = TempoMap()
        
    def test_initialization(self):
        """Test basic initialization"""
        self.assertEqual(len(self.tempo_map.tempo_changes), 1)
        self.assertEqual(self.tempo_map.tempo_changes[0], (0, 500000))
        self.assertEqual(self.tempo_map.ticks_per_beat, 480)
        
    def test_add_tempo_change(self):
        """Test adding tempo changes"""
        self.tempo_map.add_tempo_change(480, 400000)
        self.assertEqual(len(self.tempo_map.tempo_changes), 2)
        self.assertEqual(self.tempo_map.tempo_changes[1], (480, 400000))
        
        # Test sorting
        self.tempo_map.add_tempo_change(240, 600000)
        self.assertEqual(self.tempo_map.tempo_changes[1], (240, 600000))
        self.assertEqual(self.tempo_map.tempo_changes[2], (480, 400000))
        
    def test_get_tempo_at_tick(self):
        """Test getting tempo at specific ticks"""
        self.tempo_map.add_tempo_change(480, 400000)
        self.tempo_map.add_tempo_change(960, 300000)
        
        self.assertEqual(self.tempo_map.get_tempo_at_tick(0), 500000)
        self.assertEqual(self.tempo_map.get_tempo_at_tick(240), 500000)
        self.assertEqual(self.tempo_map.get_tempo_at_tick(480), 400000)
        self.assertEqual(self.tempo_map.get_tempo_at_tick(720), 400000)
        self.assertEqual(self.tempo_map.get_tempo_at_tick(960), 300000)
        self.assertEqual(self.tempo_map.get_tempo_at_tick(1200), 300000)
        
    def test_calculate_time_ms(self):
        """Test time calculation between ticks"""
        # At 120 BPM (500000 microseconds), 480 ticks = 1 beat = 500ms
        time_ms = self.tempo_map.calculate_time_ms(0, 480)
        self.assertAlmostEqual(time_ms, 500.0, places=1)
        
        # Test with tempo change
        self.tempo_map.add_tempo_change(480, 250000)  # 240 BPM
        time_ms = self.tempo_map.calculate_time_ms(0, 960)
        # First 480 ticks at 120 BPM = 500ms
        # Next 480 ticks at 240 BPM = 250ms
        # Total = 750ms
        self.assertAlmostEqual(time_ms, 750.0, places=1)
        
    def test_get_frame_for_tick(self):
        """Test frame calculation for ticks"""
        frame = self.tempo_map.get_frame_for_tick(480)
        time_ms = self.tempo_map.calculate_time_ms(0, 480)
        expected_frame = int(time_ms / FRAME_MS)
        self.assertEqual(frame, expected_frame)
        
    def test_get_tempo_bpm_at_tick(self):
        """Test BPM calculation"""
        bpm = self.tempo_map.get_tempo_bpm_at_tick(0)
        self.assertAlmostEqual(bpm, 120.0, places=1)
        
        self.tempo_map.add_tempo_change(480, 400000)
        bpm = self.tempo_map.get_tempo_bpm_at_tick(480)
        self.assertAlmostEqual(bpm, 150.0, places=1)
        
    def test_get_debug_info(self):
        """Test debug information generation"""
        self.tempo_map.add_tempo_change(480, 400000)
        debug_info = self.tempo_map.get_debug_info()
        
        self.assertIn("ticks_per_beat", debug_info)
        self.assertIn("tempo_changes", debug_info)
        self.assertEqual(len(debug_info["tempo_changes"]), 2)
        
        # Check first change
        first_change = debug_info["tempo_changes"][0]
        self.assertEqual(first_change["tick"], 0)
        self.assertEqual(first_change["tempo_microseconds"], 500000)
        self.assertAlmostEqual(first_change["bpm"], 120.0, places=1)


class TestEnhancedTempoMap(unittest.TestCase):
    def setUp(self):
        self.default_config = TempoValidationConfig(
            min_tempo_bpm=60.0,
            max_tempo_bpm=200.0,
            min_duration_frames=1,
            max_duration_frames=3600,  # 1 minute at 60fps
            max_tempo_change_ratio=2.0
        )
        
    def test_basic_enhanced_tempo_map(self):
        """Test basic enhanced tempo map initialization"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            ticks_per_beat=480,
            validation_config=self.default_config
        )
        self.assertEqual(tempo_map.get_tempo_at_tick(0), 500000)
        self.assertAlmostEqual(tempo_map.get_tempo_bpm_at_tick(0), 120.0)

    def test_validation_initial_tempo(self):
        """Test validation of initial tempo"""
        # Test valid initial tempo
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            validation_config=self.default_config
        )
        self.assertEqual(tempo_map.get_tempo_at_tick(0), 500000)

        # Test invalid initial tempo (too fast)
        with self.assertRaises(TempoValidationError) as context:
            EnhancedTempoMap(
                initial_tempo=200000,  # 300 BPM
                validation_config=self.default_config
            )
        self.assertIn("outside valid range", str(context.exception))

        # Test invalid initial tempo (too slow)
        with self.assertRaises(TempoValidationError) as context:
            EnhancedTempoMap(
                initial_tempo=3000000,  # 20 BPM
                validation_config=self.default_config
            )
        self.assertIn("outside valid range", str(context.exception))

    def test_validation_tempo_out_of_range(self):
        """Test tempo validation - out of range"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            validation_config=self.default_config
        )
        
        # Try to add a tempo that's too fast
        with self.assertRaises(TempoValidationError) as context:
            tempo_map.add_tempo_change(480, 200000)  # 300 BPM
        self.assertIn("outside valid range", str(context.exception))

        # Try to add a tempo that's too slow
        with self.assertRaises(TempoValidationError) as context:
            tempo_map.add_tempo_change(480, 3000000)  # 20 BPM
        self.assertIn("outside valid range", str(context.exception))

    def test_validation_tempo_change_ratio(self):
        """Test tempo change ratio validation"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            validation_config=self.default_config
        )

        # Add a valid tempo change first (120 BPM -> 150 BPM)
        tempo_map.add_tempo_change(480, 400000)  # 150 BPM, ratio = 1.25

        # Try to add a tempo change that exceeds the ratio limit but is within BPM range
        # Going from 150 BPM to 90 BPM (ratio = 1.67)
        tempo_map.add_tempo_change(720, 666667)  # 90 BPM

        # Now try to add a change that violates the ratio limit
        # Going from 90 BPM to 180 BPM (ratio = 2.0)
        with self.assertRaises(TempoValidationError) as context:
            tempo_map.add_tempo_change(960, 333333)  # 180 BPM, ratio = 2.0
        self.assertIn("ratio", str(context.exception))

    def test_validation_duration(self):
        """Test duration validation for gradual changes"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )

        # Test duration that's too long
        with self.assertRaises(TempoValidationError) as context:
            tempo_map.add_tempo_change(
                480, 
                400000, 
                duration_ticks=self.default_config.max_duration_frames * 480 * 2
            )
        self.assertIn("duration", str(context.exception))

    def test_multiple_tempo_changes(self):
        """Test multiple sequential tempo changes"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            validation_config=self.default_config
        )

        # Add several valid tempo changes
        tempo_map.add_tempo_change(480, 400000)   # 150 BPM
        tempo_map.add_tempo_change(960, 450000)   # 133.33 BPM
        tempo_map.add_tempo_change(1440, 375000)  # 160 BPM

        # Verify the tempo at each point
        self.assertEqual(tempo_map.get_tempo_at_tick(0), 500000)
        # At tick 500, we should have the new tempo since the change happened at 480
        self.assertEqual(tempo_map.get_tempo_at_tick(500), 400000)  # Changed expectation
        self.assertEqual(tempo_map.get_tempo_at_tick(1000), 450000)
        self.assertEqual(tempo_map.get_tempo_at_tick(1500), 375000)

    def test_edge_cases(self):
        """Test edge cases and boundary conditions"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            validation_config=self.default_config
        )

        # Test tempo change at tick 0
        with self.assertRaises(TempoValidationError):
            tempo_map.add_tempo_change(0, 200000)  # Should fail, tick 0 reserved for initial tempo

        # Test tempo change at maximum valid BPM
        max_tempo = int(60_000_000 / self.default_config.max_tempo_bpm)  # 300000 (200 BPM)
        tempo_map.add_tempo_change(480, max_tempo)
        self.assertEqual(tempo_map.get_tempo_at_tick(480), max_tempo)

        # Test tempo change at minimum valid BPM - need multiple steps to avoid ratio violation
        min_tempo = int(60_000_000 / self.default_config.min_tempo_bpm)  # 1000000 (60 BPM)
        
        # Calculate intermediate steps to reach min_tempo
        # From max_tempo (300000) to min_tempo (1000000) using multiple steps
        # Step 1: 300000 -> 450000 (ratio = 1.5)
        tempo_map.add_tempo_change(600, 450000)
        # Step 2: 450000 -> 675000 (ratio = 1.5)
        tempo_map.add_tempo_change(720, 675000)
        # Step 3: 675000 -> 850000 (ratio ≈ 1.26)
        tempo_map.add_tempo_change(840, 850000)
        # Step 4: 850000 -> 1000000 (ratio ≈ 1.18)
        tempo_map.add_tempo_change(960, min_tempo)
        
        self.assertEqual(tempo_map.get_tempo_at_tick(960), min_tempo)

class TestTempoValidationConfig(unittest.TestCase):
    """Test TempoValidationConfig functionality"""
    
    def test_default_config(self):
        """Test default validation configuration"""
        config = TempoValidationConfig()
        self.assertEqual(config.min_tempo_bpm, 20.0)
        self.assertEqual(config.max_tempo_bpm, 300.0)
        self.assertEqual(config.min_duration_frames, 1)
        self.assertEqual(config.max_duration_frames, FRAME_RATE_HZ * 60)
        self.assertEqual(config.max_tempo_change_ratio, 2.0)
        
    def test_custom_config(self):
        """Test custom validation configuration"""
        config = TempoValidationConfig(
            min_tempo_bpm=40.0,
            max_tempo_bpm=180.0,
            max_tempo_change_ratio=1.5
        )
        self.assertEqual(config.min_tempo_bpm, 40.0)
        self.assertEqual(config.max_tempo_bpm, 180.0)
        self.assertEqual(config.max_tempo_change_ratio, 1.5)


class TestTempoChange(unittest.TestCase):
    """Test TempoChange class functionality"""
    
    def test_basic_tempo_change(self):
        """Test basic tempo change creation"""
        change = TempoChange(480, 400000)
        self.assertEqual(change.tick, 480)
        self.assertEqual(change.tempo, 400000)
        self.assertEqual(change.change_type, TempoChangeType.IMMEDIATE)
        self.assertEqual(change.duration_ticks, 0)
        self.assertEqual(change.end_tick, 480)
        
    def test_gradual_tempo_change(self):
        """Test gradual tempo change creation"""
        change = TempoChange(
            480, 400000,
            TempoChangeType.LINEAR,
            duration_ticks=240,
            curve_factor=1.5,
            pattern_id="pattern_0"
        )
        
        self.assertEqual(change.tick, 480)
        self.assertEqual(change.tempo, 400000)
        self.assertEqual(change.change_type, TempoChangeType.LINEAR)
        self.assertEqual(change.duration_ticks, 240)
        self.assertEqual(change.curve_factor, 1.5)
        self.assertEqual(change.pattern_id, "pattern_0")
        self.assertEqual(change.end_tick, 720)


if __name__ == '__main__':
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        TestTempoMap,
        TestEnhancedTempoMap,
        TestTempoValidationConfig,
        TestTempoChange
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print(f"\nTests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
            
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
