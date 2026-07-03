"""
Comprehensive tests for Enhanced TempoMap implementation
Tests both backward compatibility and new features
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os
import numpy as np

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker.tempo_map import (
    TempoMap, EnhancedTempoMap, TempoValidationConfig,
    TempoChangeType, TempoValidationError,
    TempoChange, TempoOptimizationStrategy
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
        
    def test_non_positive_ticks_per_beat_rejected(self):
        # Regression (TEMPO-01 / #93 and TEMPO-03 / #95): ticks_per_beat is the
        # denominator of every tick->time conversion. A NEGATIVE value (mido
        # reports it for SMPTE-division MIDI) yields negative frame indices (#93),
        # and ZERO divides to inf and collapses every frame (#95). Both the 0 and
        # negative cases must be rejected at construction.
        for bad in (-3200, 0, -1):
            with self.assertRaises(ValueError):
                TempoMap(ticks_per_beat=bad)
            with self.assertRaises(ValueError):
                EnhancedTempoMap(initial_tempo=500000, ticks_per_beat=bad,
                                 optimization_strategy=None)
        # A valid resolution still constructs fine.
        self.assertEqual(TempoMap(ticks_per_beat=96).ticks_per_beat, 96)

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

    def test_duplicate_tick_resolves_by_insertion_order(self):
        # Regression (TEMPO-10 / #210): a bare .sort() on (tick, tempo) tuples
        # tie-breaks equal ticks by numeric tempo value, not insertion order.
        # MIDI semantics require "last event wins" for tied ticks.
        self.tempo_map.add_tempo_change(1000, 600000)  # added first
        self.tempo_map.add_tempo_change(1000, 400000)  # added second, must win
        self.assertEqual(
            self.tempo_map.tempo_changes,
            [(0, 500000), (1000, 600000), (1000, 400000)],
            "insertion order among tied ticks must be preserved, not "
            "re-ordered by tempo value")
        self.assertEqual(self.tempo_map.get_tempo_at_tick(1000), 400000)

        # The reverse insertion order must produce the reverse winner —
        # confirms the tie-break tracks insertion order, not e.g. "smaller
        # tempo always wins".
        tm2 = TempoMap()
        tm2.add_tempo_change(1000, 400000)
        tm2.add_tempo_change(1000, 600000)
        self.assertEqual(tm2.get_tempo_at_tick(1000), 600000)

    def test_align_to_frames_preserves_tie_break_order(self):
        # Sibling site (#210): _align_to_frames() re-sorts tempo_changes with
        # its own sorted() call, which had the same full-tuple tie-break bug.
        tm = EnhancedTempoMap(
            initial_tempo=500000, ticks_per_beat=480,
            optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED)
        # Two changes at the same tick via the base class (bypasses the
        # EnhancedTempoMap frame-alignment search) so _align_to_frames has a
        # real tie to resolve.
        tm.tempo_changes.append((960, 600000))
        tm.tempo_changes.append((960, 300000))
        tm.tempo_changes.sort(key=lambda c: c[0])
        tm._align_to_frames()
        # Both entries share the same source tick, so alignment maps them to
        # the same aligned tick too — insertion order (300000 last) must win.
        self.assertEqual(tm.get_tempo_at_tick(960), 300000)
        
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
        
    def get_frame_for_tick(self, tick: int) -> int:
        """Get the frame number for a specific tick"""
        time_ms = self.calculate_time_ms(0, tick)
        # Always truncate to ensure consistent frame boundaries
        return int(time_ms // FRAME_MS)  # Use floor division
        
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

    def test_zero_or_negative_tempo_raises_validation_error(self):
        # Regression (TEMPO-09 / #209): tempo <= 0 at tick > 0 used to divide
        # by zero inside _validate_basic_tempo before the BPM-range check
        # could reject it, raising a raw ZeroDivisionError instead of the
        # TempoValidationError callers (parser_fast.py) actually catch.
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000, validation_config=self.default_config)

        for bad_tempo in (0, -1, -500000):
            with self.assertRaises(TempoValidationError) as context:
                tempo_map.add_tempo_change(480, bad_tempo)
            self.assertNotIsInstance(context.exception, ZeroDivisionError)
            self.assertIn("positive", str(context.exception))

    def test_zero_or_negative_tempo_at_tick_zero_raises_validation_error(self):
        # Regression (TEMPO-08 / #208): add_tempo_change's tick==0 branch used
        # to replace the initial tempo directly and return before
        # _validate_basic_tempo ever ran, so a MIDI file whose first
        # set_tempo carried 0/negative microseconds at tick 0 was accepted
        # silently -- tempo=0 collapses every event before the next real
        # change onto frame 0; negative tempo produces negative frame indices
        # for the whole song (the same symptom as #93, via tick 0 instead).
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000, validation_config=self.default_config)

        for bad_tempo in (0, -1, -500000):
            with self.assertRaises(TempoValidationError) as context:
                tempo_map.add_tempo_change(0, bad_tempo)
            self.assertIn("positive", str(context.exception))

        # Out-of-range (but positive) tempo at tick 0 must also be rejected.
        with self.assertRaises(TempoValidationError) as context:
            tempo_map.add_tempo_change(0, 3000000)  # 20 BPM, below min_tempo_bpm
        self.assertIn("outside valid range", str(context.exception))

        # A rejected tick-0 change must not have mutated the initial tempo.
        self.assertEqual(tempo_map.tempo_changes[0], (0, 500000))

        # A valid replacement at tick 0 still works.
        tempo_map.add_tempo_change(0, 400000)  # 150 BPM
        self.assertEqual(tempo_map.tempo_changes[0], (0, 400000))

    def test_validate_tempo_change_sibling_also_guards_zero_tempo(self):
        # Sibling validator (#209): _validate_tempo_change has the same
        # unguarded division as _validate_basic_tempo, even though nothing
        # currently calls it — guard it too so a future caller doesn't
        # reintroduce the crash.
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000, validation_config=self.default_config)
        change = TempoChange(480, 0)
        with self.assertRaises(TempoValidationError):
            tempo_map._validate_tempo_change(change)

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

        # Test tempo change at tick 0 (now allowed to replace initial tempo,
        # but still subject to the same BPM-range validation as any other
        # tick -- #208/TEMPO-08)
        tempo_map.add_tempo_change(0, 400000)  # 150 BPM, within [60, 200]
        self.assertEqual(tempo_map.get_tempo_at_tick(0), 400000)

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
        
        # Check the actual tempo (it might have been aligned to a different tick)
        actual_tempo = tempo_map.get_tempo_at_tick(960)
        self.assertIn(actual_tempo, [min_tempo, 850000], 
                     f"Expected {min_tempo} or 850000 but got {actual_tempo}")
    
    def test_frame_boundary_validation(self):
        """Test that tempo changes align with frame boundaries"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            ticks_per_beat=480,
            validation_config=self.default_config
        )
        
        # This should raise an error because it's not frame-aligned
        # Directly call the validation method to test it
        with self.assertRaises(TempoValidationError):
            tempo_map._validate_frame_boundaries(17, 400000)  # Not aligned

    def test_frame_alignment_detailed(self):
        """Test frame alignment with detailed checks at each step"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            ticks_per_beat=480,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
        )

        # Add a tempo change and check alignment immediately
        tempo_map.add_tempo_change(16, 400000)  # 150 BPM
        
        # Check the actual time of the tempo change
        time_ms = tempo_map.calculate_time_ms(0, 16)
        frame_number = time_ms / FRAME_MS
        print(f"\nDebug info for tick 16:")
        print(f"Time: {time_ms} ms")
        print(f"Frame number: {frame_number}")
        print(f"Remainder: {time_ms % FRAME_MS} ms")
        
        # Add another change and check its alignment
        tempo_map.add_tempo_change(32, 450000)  # 133.33 BPM
        time_ms = tempo_map.calculate_time_ms(0, 32)
        frame_number = time_ms / FRAME_MS
        print(f"\nDebug info for tick 32:")
        print(f"Time: {time_ms} ms")
        print(f"Frame number: {frame_number}")
        print(f"Remainder: {time_ms % FRAME_MS} ms")
        
        # Get all tempo changes and their timings
        for tick, tempo in tempo_map.tempo_changes:
            time_ms = tempo_map.calculate_time_ms(0, tick)
            frame_number = time_ms / FRAME_MS
            print(f"\nTempo change at tick {tick}:")
            print(f"Tempo: {tempo} microseconds ({60_000_000/tempo:.2f} BPM)")
            print(f"Time: {time_ms} ms")
            print(f"Frame number: {frame_number}")
            print(f"Remainder: {time_ms % FRAME_MS} ms")
            
            # Verify frame alignment (allow some tolerance due to frame boundary adjustments)
            remainder = time_ms % FRAME_MS
            self.assertTrue(remainder < 2.0 or remainder > (FRAME_MS - 2.0),
                msg=f"Tempo change at tick {tick} not reasonably aligned to frame boundary (remainder: {remainder:.3f}ms)")

    def test_frame_alignment_optimization(self):
        """Test frame alignment optimization strategy"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            ticks_per_beat=480,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
        )

        # Add tempo changes that will need alignment
        tempo_map.add_tempo_change(15, 400000)  # Slightly before frame boundary
        tempo_map.add_tempo_change(33, 450000)  # Slightly after frame boundary
        
        # After optimization, verify that each tempo change is reasonably aligned
        for tick, tempo in tempo_map.tempo_changes:
            time_ms = tempo_map.calculate_time_ms(0, tick)
            remainder = time_ms % FRAME_MS
            self.assertTrue(remainder < 2.0 or remainder > (FRAME_MS - 2.0),
                msg=f"Tempo change at tick {tick} not reasonably aligned (remainder: {remainder:.3f}ms)")

    def test_curved_tempo_optimization(self):
        """Test NES-optimized curve calculations"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        start_tempo = 500000
        end_tempo = 400000
        
        # Test different curve factors
        for curve_factor in [0.5, 1.0, 2.0]:
            result = tempo_map._calculate_curved_tempo(
                start_tempo, end_tempo, 0.5, curve_factor
            )
            
            # Quantize result to 16 microsecond steps before testing
            quantized_result = (result // 16) * 16
            self.assertEqual(quantized_result, result)
            
            # Check that result is within bounds
            self.assertTrue(min(start_tempo, end_tempo) <= result <= max(start_tempo, end_tempo))

    def test_pattern_tempo_optimization(self):
        """Test pattern-specific tempo optimization"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        pattern_id = "test_pattern"
        base_tempo = 500000
        
        # Calculate frame-aligned ticks
        frame_time = 16.67  # One frame at 60fps
        aligned_tick = tempo_map._find_tick_at_time(frame_time)
        
        # Add pattern with frame-aligned variations
        variations = [
            TempoChange(aligned_tick, 450000, TempoChangeType.LINEAR, 240),
            TempoChange(aligned_tick * 2, 520000, TempoChangeType.CURVE, 240, 1.5),
            TempoChange(aligned_tick * 3, 510000, TempoChangeType.IMMEDIATE)
        ]
        
        tempo_map.add_pattern_tempo(pattern_id, base_tempo, variations)
        
        # Optimize pattern tempos
        tempo_map.optimize_pattern_tempos()
        
        # Check that variations are optimized
        pattern_info = tempo_map.pattern_tempos[pattern_id]
        for var in pattern_info.variations:
            # Check frame alignment
            frame_time = tempo_map.calculate_time_ms(0, var.tick)
            self.assertAlmostEqual(frame_time % FRAME_MS, 0, places=1)
            
            # Check significant difference threshold
            tempo_diff_ratio = abs(var.tempo - base_tempo) / base_tempo
            self.assertGreater(tempo_diff_ratio, 0.05)

    def test_memory_optimization(self):
        """Test memory usage optimization"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        # Add several similar tempo changes
        tempo_map.add_tempo_change(480, 500000)
        tempo_map.add_tempo_change(720, 502000)  # Small difference
        tempo_map.add_tempo_change(960, 498000)  # Small difference
        
        # Test optimization reduces similar changes
        original_count = len(tempo_map.tempo_changes)
        tempo_map.optimize_tempo_changes()
        optimized_count = len(tempo_map.tempo_changes)
        
        # May reduce number of changes if they're too similar
        self.assertLessEqual(optimized_count, original_count)
        
    def test_gradual_tempo_changes(self):
        """Test gradual tempo changes (linear, curve, pattern sync)"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        # Test linear gradual change
        tempo_map.add_tempo_change(
            480, 400000, 
            change_type=TempoChangeType.LINEAR,
            duration_ticks=240
        )
        
        # Verify intermediate tempos were created
        initial_count = len(tempo_map.tempo_changes)
        self.assertGreater(initial_count, 2)  # Should have intermediate steps
        
        # Test curve gradual change
        tempo_map.add_tempo_change(
            960, 450000,
            change_type=TempoChangeType.CURVE,
            duration_ticks=240
        )
        
        # Test that curved tempo calculation works
        curved_tempo = tempo_map._calculate_curved_tempo(500000, 400000, 0.5, 2.0)
        self.assertTrue(400000 <= curved_tempo <= 500000)
        self.assertEqual(curved_tempo % 16, 0)  # Should be quantized to 16μs steps
        
        # Test pattern sync calculation
        pattern_tempo = tempo_map._calculate_pattern_sync_tempo(500000, 400000, 0.5)
        self.assertTrue(400000 <= pattern_tempo <= 500000)
        
    def test_pattern_tempo_management(self):
        """Test pattern-specific tempo management"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        pattern_id = "test_pattern"
        base_tempo = 500000
        
        # Create pattern variations with different change types
        variations = [
            TempoChange(100, 450000, TempoChangeType.IMMEDIATE),
            TempoChange(200, 480000, TempoChangeType.LINEAR, 120),
            TempoChange(400, 520000, TempoChangeType.CURVE, 120, 1.5)
        ]
        
        # Add pattern tempo
        tempo_map.add_pattern_tempo(pattern_id, base_tempo, variations)
        
        # Verify pattern was added
        self.assertIn(pattern_id, tempo_map.pattern_tempos)
        pattern_info = tempo_map.pattern_tempos[pattern_id]
        self.assertEqual(pattern_info.base_tempo, base_tempo)
        self.assertEqual(len(pattern_info.variations), 3)
        
        # Test enhanced tempo lookup with pattern context
        tempo = tempo_map.get_enhanced_tempo_at_tick(150, pattern_id)
        self.assertIsInstance(tempo, int)
        
        # Test pattern analysis
        analysis = tempo_map.analyze_pattern_tempo_characteristics(pattern_id)
        self.assertIn('base_tempo_bpm', analysis)
        self.assertIn('variation_count', analysis)
        self.assertIn('tempo_range', analysis)
        self.assertIn('timing_stability', analysis)
        self.assertIn('complexity_score', analysis)
        
        # Check that we can analyze non-existent pattern
        empty_analysis = tempo_map.analyze_pattern_tempo_characteristics("nonexistent")
        self.assertEqual(empty_analysis, {})
        
    def test_loop_point_management(self):
        """Test loop point registration and management"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        # Add some tempo changes
        tempo_map.add_tempo_change(480, 400000)
        tempo_map.add_tempo_change(960, 450000)
        
        # Register loop points
        loop_id = "main_loop"
        tempo_map.register_loop_point(loop_id, 240, 1200)
        
        # Verify loop point was registered
        self.assertIn(loop_id, tempo_map.loop_points)
        loop_info = tempo_map.loop_points[loop_id]
        self.assertEqual(loop_info['start']['tick'], 240)
        self.assertEqual(loop_info['end']['tick'], 1200)
        self.assertIsInstance(loop_info['start']['tempo'], int)
        self.assertIsInstance(loop_info['end']['tempo'], int)
        
    def test_optimization_strategies(self):
        """Test different optimization strategies"""
        # Test MINIMIZE_CHANGES strategy
        tempo_map1 = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.MINIMIZE_CHANGES
        )
        
        tempo_map1.add_tempo_change(480, 501000)  # Very similar to initial
        tempo_map1.add_tempo_change(960, 499000)  # Very similar to initial
        tempo_map1.optimize_tempo_changes()
        
        # Test SMOOTH_TRANSITIONS strategy
        tempo_map2 = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.SMOOTH_TRANSITIONS
        )
        
        tempo_map2.add_tempo_change(480, 300000)  # Large change
        tempo_map2.optimize_tempo_changes()
        
        # Should have added intermediate steps
        self.assertGreater(len(tempo_map2.tempo_changes), 2)
        
        # Test PATTERN_ALIGNED strategy
        tempo_map3 = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.PATTERN_ALIGNED
        )
        
        tempo_map3.add_tempo_change(480, 400000)
        tempo_map3.optimize_tempo_changes()
        
    def test_frame_alignment_utilities(self):
        """Test frame alignment utility functions"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
        )
        
        # Test frame alignment check
        result = tempo_map.is_frame_aligned(0)
        self.assertTrue(isinstance(result, (bool, np.bool_)))
        
        # Test find nearest frame aligned tick
        aligned_tick = tempo_map.find_nearest_frame_aligned_tick(100)
        self.assertIsInstance(aligned_tick, int)
        self.assertGreaterEqual(aligned_tick, 0)
        
        # Test find tick at specific time
        tick_at_time = tempo_map._find_tick_at_time(50.0)  # 50ms
        self.assertIsInstance(tick_at_time, int)
        self.assertGreaterEqual(tick_at_time, 0)
        
        # Test frame aligned tick finding
        frame_aligned_tick = tempo_map._find_frame_aligned_tick(50.0)
        self.assertIsInstance(frame_aligned_tick, int)
        self.assertGreaterEqual(frame_aligned_tick, 0)

    def test_alignment_predicates_share_one_tolerance(self):
        """Every alignment-validity check must agree on the same tolerance
        constant, so a tick cannot be judged aligned by one method and
        misaligned by another (#99)."""
        from tracker.tempo_map import FRAME_ALIGNMENT_TOLERANCE_MS
        from constants import FRAME_MS
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            ticks_per_beat=480,
            validation_config=self.default_config,
        )
        # A tick whose time sits just OUTSIDE the tolerance must be rejected by
        # every validity check in lockstep. Tick 17 is ~1.04ms off a boundary.
        off_tick = 17
        remainder = tempo_map.calculate_time_ms(0, off_tick) % FRAME_MS
        self.assertGreater(remainder, FRAME_ALIGNMENT_TOLERANCE_MS)
        self.assertFalse(tempo_map.is_frame_aligned(off_tick))
        with self.assertRaises(TempoValidationError):
            tempo_map._validate_frame_boundaries(off_tick, 400000)
        with self.assertRaises(TempoValidationError):
            tempo_map._check_frame_alignment(TempoChange(off_tick, 400000))
        # Tick 0 is exactly on a boundary — accepted by the same tolerance.
        self.assertTrue(tempo_map.is_frame_aligned(0))
        tempo_map._validate_frame_boundaries(0, 500000)  # must not raise

    def test_validation_edge_cases(self):
        """Test validation edge cases and error conditions"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        # Test validation of basic tempo properties
        valid_change = TempoChange(480, 400000)
        tempo_map._validate_basic_tempo(valid_change)  # Should not raise
        
        # Test invalid tempo range
        invalid_change = TempoChange(480, 100000)  # Too fast
        with self.assertRaises(TempoValidationError):
            tempo_map._validate_basic_tempo(invalid_change)
            
        # Test frame boundary validation
        with self.assertRaises(TempoValidationError):
            tempo_map._validate_frame_boundaries(123, 400000)  # Not aligned
            
        # Test check frame alignment method
        frame_change = TempoChange(100, 400000)
        with self.assertRaises(TempoValidationError):
            tempo_map._check_frame_alignment(frame_change)
            
    def test_optimization_stats_and_debug(self):
        """Test optimization statistics and debug information"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
        )
        
        # Add some changes and optimize
        tempo_map.add_tempo_change(480, 400000)
        tempo_map.add_tempo_change(960, 450000)
        tempo_map.optimize_tempo_changes()
        
        # Get optimization stats
        stats = tempo_map.get_optimization_stats()
        self.assertIsInstance(stats, dict)
        
        # Get enhanced debug info
        debug_info = tempo_map.get_debug_info()
        self.assertIn('validation_config', debug_info)
        self.assertIn('optimization_strategy', debug_info)
        self.assertIn('optimization_stats', debug_info)
        self.assertIn('pattern_count', debug_info)
        self.assertIn('loop_points_count', debug_info)
        
        # Check validation config in debug info
        val_config = debug_info['validation_config']
        self.assertEqual(val_config['min_tempo_bpm'], self.default_config.min_tempo_bpm)
        self.assertEqual(val_config['max_tempo_bpm'], self.default_config.max_tempo_bpm)
        
    def test_error_handling_and_edge_cases(self):
        """Test error handling and various edge cases"""
        # Test with no optimization strategy
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config,
            optimization_strategy=None
        )
        
        tempo_map.add_tempo_change(480, 400000)
        tempo_map.optimize_tempo_changes()  # Should not crash
        
        # Test caching behavior
        time1 = tempo_map.calculate_time_ms(0, 480)
        time2 = tempo_map.calculate_time_ms(0, 480)  # Should use cache
        self.assertEqual(time1, time2)
        
        # Test with same start and end tick
        zero_time = tempo_map.calculate_time_ms(100, 100)
        self.assertEqual(zero_time, 0.0)
        
        # Test _ticks_to_ms helper
        ms = tempo_map._ticks_to_ms(480, 500000)
        self.assertAlmostEqual(ms, 500.0, places=1)
        
        # Test get_frame_for_tick
        frame = tempo_map.get_frame_for_tick(480)
        self.assertIsInstance(frame, int)
        self.assertGreaterEqual(frame, 0)
        
    def test_numpy_precision_calculations(self):
        """Test numpy-based precision calculations"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        # Add tempo changes to test complex calculations
        tempo_map.add_tempo_change(240, 450000)
        tempo_map.add_tempo_change(480, 400000)
        tempo_map.add_tempo_change(720, 550000)
        
        # Test time calculation with multiple tempo changes
        total_time = tempo_map.calculate_time_ms(0, 1000)
        self.assertGreater(total_time, 0)
        
        # Test frame alignment calculations
        frame_aligned_tick = tempo_map.find_nearest_frame_aligned_tick(500)
        self.assertIsInstance(frame_aligned_tick, int)
        tempo_map.add_tempo_change(960, 550000)  # Significant difference
        
        initial_count = len(tempo_map.tempo_changes)
        
        # Optimize
        tempo_map.optimization_strategy = TempoOptimizationStrategy.MINIMIZE_CHANGES
        tempo_map.optimize_tempo_changes()
        
        # Check that similar changes were combined
        optimized_count = len(tempo_map.tempo_changes)
        self.assertLess(optimized_count, initial_count)
        
        # Check that significant changes were preserved
        found_significant = False
        for tick, tempo in tempo_map.tempo_changes:
            if tempo == 550000:
                found_significant = True
                break
        self.assertTrue(found_significant)

    def test_optimization_statistics(self):
        """Test optimization statistics tracking"""
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config
        )
        
        # Test frame alignment statistics (default strategy)
        tempo_map.add_tempo_change(480, 500000)
        tempo_map.add_tempo_change(960, 502000)
        tempo_map.add_tempo_change(1440, 550000)
        
        # Optimize with frame alignment (default)
        tempo_map.optimize_tempo_changes()
        
        # Check frame alignment statistics
        stats = tempo_map.get_optimization_stats()
        self.assertIn('frame_alignments', stats)
        
        # Test pattern tempo optimization statistics
        pattern_id = "test_pattern"
        tempo_map.add_pattern_tempo(
            pattern_id, 500000,
            [TempoChange(480, 450000, TempoChangeType.LINEAR, 240)]  # significant difference
        )
        
        # Optimize pattern tempos
        tempo_map.optimize_pattern_tempos()
        
        # Check pattern optimization statistics
        stats = tempo_map.get_optimization_stats()
        self.assertIn('pattern_tempo_optimizations', stats)
        
        # Test minimize changes strategy
        tempo_map2 = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=self.default_config,
            optimization_strategy=TempoOptimizationStrategy.MINIMIZE_CHANGES
        )
        
        # Add similar tempo changes that should be combined
        tempo_map2.add_tempo_change(480, 500000)
        tempo_map2.add_tempo_change(960, 502000)  # Small difference - should be combined
        tempo_map2.add_tempo_change(1440, 550000)  # Significant difference - preserved
        
        tempo_map2.optimize_tempo_changes()
        
        # Check combination statistics
        stats2 = tempo_map2.get_optimization_stats()
        self.assertIn('changes_combined', stats2)


class TestTempoValidationConfig(unittest.TestCase):
    """Test TempoValidationConfig functionality"""
    
    def test_default_config(self):
        """Test default validation configuration"""
        config = TempoValidationConfig()
        self.assertEqual(config.min_tempo_bpm, 20.0)
        self.assertEqual(config.max_tempo_bpm, 600.0)  # Updated default
        self.assertEqual(config.min_duration_frames, 1)
        self.assertEqual(config.max_duration_frames, FRAME_RATE_HZ * 60)
        self.assertEqual(config.max_tempo_change_ratio, 3.0)  # Updated default
        
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

class TestFrameAlignment(unittest.TestCase):
    """Test cases specifically for frame alignment behavior"""
    
    def setUp(self):
        self.config = TempoValidationConfig(
            min_tempo_bpm=60.0,
            max_tempo_bpm=200.0,
            min_duration_frames=1,
            max_duration_frames=3600,
            max_tempo_change_ratio=2.0
        )
        self.tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            validation_config=self.config,
            optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
        )
        
    def test_frame_aligned_ticks(self):
        """Test which ticks naturally align with frame boundaries"""
        # At 120 BPM (500000 microseconds per beat)
        # 1 beat = 480 ticks = 500ms
        # 1 frame = 16.67ms (60 fps)
        
        # Test first few frame boundaries
        frame_times = []
        for frame in range(5):
            frame_time = frame * FRAME_MS
            print(f"\nFrame {frame}:")
            print(f"Expected time: {frame_time}ms")
            
            # Try to find a tick that gives this time
            for tick in range(0, 480, 16):  # Test every 16th tick
                time = self.tempo_map.calculate_time_ms(0, tick)
                remainder = time % FRAME_MS
                print(f"Tick {tick}: time={time}ms, remainder={remainder}ms")
                
                if remainder < 0.001:
                    frame_times.append((frame, tick, time))
                    
        print("\nFound frame-aligned ticks:")
        for frame, tick, time in frame_times:
            print(f"Frame {frame}: tick={tick}, time={time}ms")
            
    def test_frame_alignment_with_tempo_change(self):
        """Test frame alignment before and after tempo changes"""
        # Add a tempo change and verify frame alignment still works
        self.tempo_map.add_tempo_change(480, 400000)  # 150 BPM
        
        print("\nChecking frame alignment after tempo change:")
        for tick in range(460, 500, 4):
            time = self.tempo_map.calculate_time_ms(0, tick)
            frame = time / FRAME_MS
            remainder = time % FRAME_MS
            print(f"Tick {tick}: time={time}ms, frame={frame}, remainder={remainder}ms")
            
    def test_frame_boundary_search(self):
        """Test the process of finding frame-aligned ticks"""
        test_ticks = [32, 480, 720, 960]  # Ticks that are failing in tests
        
        print("\nAnalyzing problematic ticks:")
        for tick in test_ticks:
            time = self.tempo_map.calculate_time_ms(0, tick)
            frame = time / FRAME_MS
            remainder = time % FRAME_MS
            print(f"\nTick {tick}:")
            print(f"Time: {time}ms")
            print(f"Frame: {frame}")
            print(f"Remainder: {remainder}ms")
            
            # Try to find nearest frame-aligned tick
            frame_number = round(frame)
            target_time = frame_number * FRAME_MS
            
            print(f"Target frame time: {target_time}ms")
            
            # Search nearby ticks
            search_range = 16
            for test_tick in range(tick - search_range, tick + search_range):
                if test_tick <= 0:
                    continue
                    
                test_time = self.tempo_map.calculate_time_ms(0, test_tick)
                test_remainder = test_time % FRAME_MS
                if test_remainder < 0.001:
                    print(f"Found aligned tick: {test_tick} (time={test_time}ms)")
                    break


class TestTempoLookupIndex(unittest.TestCase):
    """Regression tests for the bisect-based tempo/time index (#113).

    The per-note parse hot path calls get_tempo_at_tick / get_frame_for_tick once
    per event; these must stay correct on a tempo-DENSE map (hundreds of
    set_tempo) where the old linear/quadratic scans were the bottleneck."""

    @staticmethod
    def _ref_tempo(changes, tick):
        """Brute-force O(T) reference: tempo of the last change at/before tick."""
        active = changes[0][1]
        for ct, t in changes:
            if ct <= tick:
                active = t
            else:
                break
        return active

    @staticmethod
    def _ref_time_ms(changes, ticks_per_beat, end_tick):
        """Brute-force per-segment reference for calculate_time_ms(0, end)."""
        total = np.float64(0)
        cur = np.int64(0)
        end = np.int64(end_tick)
        while cur < end:
            tempo = TestTempoLookupIndex._ref_tempo(changes, int(cur))
            nxt = end
            for ct, _ in changes:
                if cur < ct < nxt:
                    nxt = ct
            upt = np.float64(tempo) / ticks_per_beat
            total += ((nxt - cur) * upt) / 1000.0
            cur = nxt
        return float(total)

    def _build_dense_map(self):
        tm = TempoMap(initial_tempo=500000, ticks_per_beat=480)
        changes = [(0, 500000)]
        for i in range(1, 300):  # tempo-dense: ~300 changes
            tick = i * 37
            tempo = 400000 + (i * 211 % 300000)
            tm.add_tempo_change(tick, tempo)
            changes.append((tick, tempo))
        changes.sort()
        return tm, changes

    def test_tempo_lookup_matches_bruteforce(self):
        tm, changes = self._build_dense_map()
        for tick in range(0, 300 * 37 + 500, 7):
            self.assertEqual(tm.get_tempo_at_tick(tick),
                             self._ref_tempo(changes, tick),
                             f"tempo mismatch at tick {tick}")

    def test_calculate_time_ms_matches_bruteforce(self):
        tm, changes = self._build_dense_map()
        for tick in range(0, 300 * 37 + 500, 13):
            self.assertAlmostEqual(tm.calculate_time_ms(0, tick),
                                   self._ref_time_ms(changes, 480, tick),
                                   places=6,
                                   msg=f"time mismatch at tick {tick}")

    def test_calculate_time_ms_is_additive(self):
        """time[a, c] == time[0, c] - time[0, a] (the index relies on this)."""
        tm, _ = self._build_dense_map()
        for a, c in [(100, 5000), (37, 11000), (0, 9999), (2500, 2501)]:
            self.assertAlmostEqual(
                tm.calculate_time_ms(a, c),
                tm.calculate_time_ms(0, c) - tm.calculate_time_ms(0, a),
                places=6)

    def test_index_invalidated_on_new_tempo_change(self):
        """A query builds the index; a later add_tempo_change must rebuild it."""
        tm = TempoMap(initial_tempo=500000, ticks_per_beat=480)
        self.assertEqual(tm.get_tempo_at_tick(1000), 500000)  # builds index
        tm.add_tempo_change(500, 300000)
        self.assertEqual(tm.get_tempo_at_tick(1000), 300000)
        self.assertEqual(tm.get_tempo_at_tick(100), 500000)

    def test_enhanced_dense_parse_correctness(self):
        """EnhancedTempoMap (the parser's class) stays correct when fed many
        IMMEDIATE tempo changes with optimization disabled, as parser_fast does."""
        config = TempoValidationConfig(min_tempo_bpm=40.0, max_tempo_bpm=250.0)
        tm = EnhancedTempoMap(initial_tempo=500000, ticks_per_beat=480,
                              validation_config=config,
                              optimization_strategy=None)
        ref = [(0, 500000)]
        tempo = 500000
        for i in range(1, 200):
            tick = i * 50
            # Keep within validation range and small step (ratio guard).
            tempo = 400000 if (i % 2) else 600000
            try:
                tm.add_tempo_change(tick, tempo, TempoChangeType.IMMEDIATE)
                ref.append((tick, tempo))
            except TempoValidationError:
                continue
        ref.sort()
        for tick in range(0, 200 * 50, 11):
            self.assertEqual(tm.get_tempo_at_tick(tick),
                             self._ref_tempo(ref, tick),
                             f"enhanced tempo mismatch at tick {tick}")


if __name__ == '__main__':
    unittest.main()
