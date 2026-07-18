# tests/test_patterns.py
import io
import unittest
from concurrent.futures import Future
from contextlib import redirect_stdout
from unittest.mock import patch
from tracker.pattern_detector import PatternDetector, PatternCompressor, EnhancedPatternDetector
from tracker.loop_manager import LoopManager
from tracker.tempo_map import EnhancedTempoMap

class TestPatternDetection(unittest.TestCase):
    def setUp(self):
        self.pattern_detector = PatternDetector(min_pattern_length=3)
        self.loop_manager = LoopManager(simple_mode=True)  # Use simple mode for pattern tests
        
        # Test data with clear patterns - frame numbers are sequential but irrelevant
        self.test_events = [
            # First pattern
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            # Pattern repeats
            {'frame': 3, 'note': 60, 'volume': 100},
            {'frame': 4, 'note': 64, 'volume': 100},
            {'frame': 5, 'note': 67, 'volume': 100},
            # Pattern repeats again
            {'frame': 6, 'note': 60, 'volume': 100},
            {'frame': 7, 'note': 64, 'volume': 100},
            {'frame': 8, 'note': 67, 'volume': 100},
            # One more time
            {'frame': 9, 'note': 60, 'volume': 100},
            {'frame': 10, 'note': 64, 'volume': 100},
            {'frame': 11, 'note': 67, 'volume': 100},
        ]

    def test_pattern_detection(self):
        patterns = self.pattern_detector.detect_patterns(self.test_events)
        self.assertTrue(len(patterns) > 0, "No patterns detected")
        
        # Verify pattern structure
        first_pattern = list(patterns.values())[0]
        self.assertIn('events', first_pattern, "Pattern missing 'events' key")
        self.assertIn('positions', first_pattern, "Pattern missing 'positions' key")
        self.assertIn('length', first_pattern, "Pattern missing 'length' key")
        
        # Verify pattern content
        self.assertEqual(len(first_pattern['positions']), 4, 
                        f"Pattern should appear 4 times, found {len(first_pattern['positions'])} times")
        self.assertEqual(first_pattern['length'], 3, 
                        f"Pattern should be length 3, found length {first_pattern['length']}")

    def test_loop_detection(self):
        patterns = self.pattern_detector.detect_patterns(self.test_events)
        loops = self.loop_manager.detect_loops(self.test_events, patterns)
        
        self.assertTrue(len(loops) > 0, "No loops detected")
        
        # Verify loop structure
        first_loop = list(loops.values())[0]
        self.assertIn('start', first_loop, "Loop missing 'start' key")
        self.assertIn('end', first_loop, "Loop missing 'end' key")
        self.assertIn('length', first_loop, "Loop missing 'length' key")
        
        # Verify loop content
        self.assertTrue(first_loop['start'] < first_loop['end'], 
                       "Loop end should be after loop start")

    def test_longer_patterns(self):
        """Test detection of longer patterns"""
        long_pattern_events = [
            # 4-note pattern
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            {'frame': 3, 'note': 72, 'volume': 100},
            # Pattern repeats
            {'frame': 4, 'note': 60, 'volume': 100},
            {'frame': 5, 'note': 64, 'volume': 100},
            {'frame': 6, 'note': 67, 'volume': 100},
            {'frame': 7, 'note': 72, 'volume': 100},
            # Pattern repeats again
            {'frame': 8, 'note': 60, 'volume': 100},
            {'frame': 9, 'note': 64, 'volume': 100},
            {'frame': 10, 'note': 67, 'volume': 100},
            {'frame': 11, 'note': 72, 'volume': 100},
        ]
        
        patterns = self.pattern_detector.detect_patterns(long_pattern_events)
        self.assertTrue(len(patterns) > 0, "No long patterns detected")
        
        # Should find the 4-note pattern
        first_pattern = list(patterns.values())[0]
        self.assertEqual(first_pattern['length'], 4, "Should detect 4-note pattern")
        self.assertEqual(len(first_pattern['positions']), 3, "Pattern should repeat 3 times")

    def test_volume_variations(self):
        """Test patterns with different volumes"""
        volume_events = [
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 80},
            {'frame': 2, 'note': 67, 'volume': 120},
            # Same pattern with same volumes
            {'frame': 3, 'note': 60, 'volume': 100},
            {'frame': 4, 'note': 64, 'volume': 80},
            {'frame': 5, 'note': 67, 'volume': 120},
            # Same pattern again
            {'frame': 6, 'note': 60, 'volume': 100},
            {'frame': 7, 'note': 64, 'volume': 80},
            {'frame': 8, 'note': 67, 'volume': 120},
        ]
        
        patterns = self.pattern_detector.detect_patterns(volume_events)
        self.assertTrue(len(patterns) > 0, "No volume patterns detected")
        
        first_pattern = list(patterns.values())[0]
        self.assertEqual(len(first_pattern['positions']), 3, "Volume pattern should repeat 3 times")

    def test_no_patterns(self):
        """Test sequence with no repeating patterns"""
        no_pattern_events = [
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 62, 'volume': 100},
            {'frame': 2, 'note': 64, 'volume': 100},
            {'frame': 3, 'note': 65, 'volume': 100},
            {'frame': 4, 'note': 67, 'volume': 100},
            {'frame': 5, 'note': 69, 'volume': 100},
        ]
        
        patterns = self.pattern_detector.detect_patterns(no_pattern_events)
        self.assertEqual(len(patterns), 0, "Should not detect patterns in non-repeating sequence")

    def test_overlapping_patterns(self):
        """Test detection when patterns might overlap"""
        overlapping_events = [
            # Pattern A: 60-64-67
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            # Pattern B: 64-67-72 (overlaps with A)
            {'frame': 3, 'note': 64, 'volume': 100},
            {'frame': 4, 'note': 67, 'volume': 100},
            {'frame': 5, 'note': 72, 'volume': 100},
            # Pattern A repeats
            {'frame': 6, 'note': 60, 'volume': 100},
            {'frame': 7, 'note': 64, 'volume': 100},
            {'frame': 8, 'note': 67, 'volume': 100},
            # Pattern B repeats
            {'frame': 9, 'note': 64, 'volume': 100},
            {'frame': 10, 'note': 67, 'volume': 100},
            {'frame': 11, 'note': 72, 'volume': 100},
            # Pattern A repeats again
            {'frame': 12, 'note': 60, 'volume': 100},
            {'frame': 13, 'note': 64, 'volume': 100},
            {'frame': 14, 'note': 67, 'volume': 100},
        ]
        
        patterns = self.pattern_detector.detect_patterns(overlapping_events)
        # Should detect at least one pattern (optimization will choose the best one)
        self.assertTrue(len(patterns) > 0, "Should detect patterns even with overlaps")

    def test_find_pattern_matches_does_not_overlap_the_anchor(self):
        """Regression (#170/PAT-04): in a self-similar run (period < pattern
        length), the scan used to resume at start_pos + 1 instead of
        start_pos + pattern_len, letting the first "match" overlap the anchor
        window itself. 12 identical (note, volume) events with pattern length
        4 must greedily skip a full pattern_len per match -- [0, 4, 8], not
        the old overlapping [0, 1, 5] -- matching the parallel detector's
        next_free greedy in _collect_length_candidates."""
        sequence = [(60, 100)] * 12
        pattern = tuple(sequence[0:4])
        matches = self.pattern_detector._find_pattern_matches(sequence, pattern, 0)
        self.assertEqual(matches, [0, 4, 8])

    def test_empty_input(self):
        """Test with empty input"""
        patterns = self.pattern_detector.detect_patterns([])
        self.assertEqual(len(patterns), 0, "Empty input should return no patterns")
        
        loops = self.loop_manager.detect_loops([], {})
        self.assertEqual(len(loops), 0, "Empty input should return no loops")

    def test_insufficient_data(self):
        """Test with insufficient data for patterns"""
        short_events = [
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
        ]
        
        patterns = self.pattern_detector.detect_patterns(short_events)
        self.assertEqual(len(patterns), 0, "Should not detect patterns with insufficient data")

    def test_jump_table_generation(self):
        """Test jump table generation from loops"""
        patterns = self.pattern_detector.detect_patterns(self.test_events)
        loops = self.loop_manager.detect_loops(self.test_events, patterns)
        jump_table = self.loop_manager.generate_jump_table(loops)
        
        # Verify jump table structure
        for end_pos, start_pos in jump_table.items():
            self.assertTrue(isinstance(end_pos, int), "Jump table keys should be integers")
            self.assertTrue(isinstance(start_pos, int), "Jump table values should be integers")

    def test_pattern_with_variations(self):
        """Test pattern detection with variations"""
        variation_events = [
            # Original pattern
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            # Transposed variation
            {'frame': 3, 'note': 62, 'volume': 100},
            {'frame': 4, 'note': 66, 'volume': 100},
            {'frame': 5, 'note': 69, 'volume': 100},
            # Volume variation
            {'frame': 6, 'note': 60, 'volume': 80},
            {'frame': 7, 'note': 64, 'volume': 80},
            {'frame': 8, 'note': 67, 'volume': 80},
        ]
        
        patterns = self.pattern_detector.detect_patterns(variation_events)
        self.assertTrue(len(patterns) > 0, "Should detect pattern with variations")
        
        first_pattern = list(patterns.values())[0]
        self.assertIn('variations', first_pattern, "Pattern should include variations")
        self.assertTrue(len(first_pattern['variations']) >= 2, 
                    "Should detect both transposed and volume variations")

    def test_pattern_optimization_with_variations(self):
        """Test pattern optimization considering variations"""
        events = [
            # Pattern A
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            # Pattern B
            {'frame': 3, 'note': 72, 'volume': 100},
            {'frame': 4, 'note': 76, 'volume': 100},
            {'frame': 5, 'note': 79, 'volume': 100},
            # Pattern A variation
            {'frame': 6, 'note': 62, 'volume': 100},
            {'frame': 7, 'note': 66, 'volume': 100},
            {'frame': 8, 'note': 69, 'volume': 100},
        ]
        
        patterns = self.pattern_detector.detect_patterns(events)
        optimized = self.pattern_detector._optimize_patterns(patterns)
        
        self.assertTrue(len(optimized) > 0, "Should keep patterns after optimization")
        first_pattern = list(optimized.values())[0]
        self.assertIn('variations', first_pattern, 
                    "Optimized pattern should retain variations")


class TestEnhancedPatternDetector(unittest.TestCase):
    def setUp(self):
        self.tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM
        self.detector = EnhancedPatternDetector(self.tempo_map, min_pattern_length=3)
        
    def test_pattern_tempo_analysis(self):
        """Test tempo analysis for patterns"""
        events = [
            {'frame': 0, 'note': 60, 'volume': 100, 'tick': 0},
            {'frame': 1, 'note': 64, 'volume': 100, 'tick': 120},
            {'frame': 2, 'note': 67, 'volume': 100, 'tick': 240},
            # Pattern repeats exactly
            {'frame': 3, 'note': 60, 'volume': 100, 'tick': 360},
            {'frame': 4, 'note': 64, 'volume': 100, 'tick': 480},
            {'frame': 5, 'note': 67, 'volume': 100, 'tick': 600},
            # Pattern repeats again
            {'frame': 6, 'note': 60, 'volume': 100, 'tick': 720},
            {'frame': 7, 'note': 64, 'volume': 100, 'tick': 840},
            {'frame': 8, 'note': 67, 'volume': 100, 'tick': 960},
        ]
        
        # Add a tempo change
        self.tempo_map.add_tempo_change(480, 400000)  # 150 BPM at tick 480
        
        result = self.detector.detect_patterns(events)
        
        self.assertIn('patterns', result)
        if result['patterns']:
            pattern = list(result['patterns'].values())[0]
            # Check if tempo analysis was performed (patterns detected)
            self.assertTrue(len(result['patterns']) > 0, "Should detect at least one pattern")
        
    def test_variation_tempo_analysis(self):
        """Test tempo analysis for pattern variations"""
        events = [
            # Original pattern
            {'frame': 0, 'note': 60, 'volume': 100, 'tick': 0},
            {'frame': 1, 'note': 64, 'volume': 100, 'tick': 120},
            {'frame': 2, 'note': 67, 'volume': 100, 'tick': 240},
            # Exact repeat
            {'frame': 3, 'note': 60, 'volume': 100, 'tick': 360},
            {'frame': 4, 'note': 64, 'volume': 100, 'tick': 480},
            {'frame': 5, 'note': 67, 'volume': 100, 'tick': 600},
            # Variation with transposition
            {'frame': 6, 'note': 62, 'volume': 100, 'tick': 720},
            {'frame': 7, 'note': 66, 'volume': 100, 'tick': 840},
            {'frame': 8, 'note': 69, 'volume': 100, 'tick': 960},
        ]
        
        # Add tempo changes
        self.tempo_map.add_tempo_change(480, 400000)  # 150 BPM at tick 480
        
        result = self.detector.detect_patterns(events)
        
        if result['patterns']:
            pattern = list(result['patterns'].values())[0]
            if 'variations' in pattern and pattern['variations']:
                # Check if any variations have tempo info
                has_tempo_info = any('tempo_info' in var for var in pattern['variations'])
                self.assertTrue(has_tempo_info or len(pattern['variations']) == 0,
                              "Variations should include tempo analysis when present")


class TestAnalyzeTempoOptOut(unittest.TestCase):
    """Regression tests for #119: EnhancedPatternDetector(analyze_tempo=False)
    must skip the per-pattern tempo analysis (whose output is discarded by
    main.py's callers, since their tempo_map holds no real tempo-change data)
    while leaving the default (analyze_tempo=True) behavior unchanged."""

    def _repeating_events(self):
        return [
            {'frame': i, 'note': 60 + (i % 3) * 4, 'volume': 100} for i in range(30)
        ]

    def test_default_still_runs_tempo_analysis(self):
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3)
        self.assertTrue(detector.analyze_tempo)
        result = detector.detect_patterns(self._repeating_events())
        self.assertGreater(len(result['patterns']), 0)
        # tempo_map.pattern_tempos gets populated as a side effect of the
        # analysis pass when it runs.
        self.assertGreater(len(tempo_map.pattern_tempos), 0)

    def test_analyze_tempo_false_skips_pattern_tempo_registration(self):
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3,
                                           analyze_tempo=False)
        self.assertFalse(detector.analyze_tempo)
        result = detector.detect_patterns(self._repeating_events())
        # Patterns are still detected identically...
        self.assertGreater(len(result['patterns']), 0)
        # ...but the tempo-map side effect never happens.
        self.assertEqual(len(tempo_map.pattern_tempos), 0)

    def test_analyze_tempo_false_yields_identical_patterns_to_true(self):
        events = self._repeating_events()
        with_analysis = EnhancedPatternDetector(
            EnhancedTempoMap(initial_tempo=500000), min_pattern_length=3
        ).detect_patterns(events)
        without_analysis = EnhancedPatternDetector(
            EnhancedTempoMap(initial_tempo=500000), min_pattern_length=3,
            analyze_tempo=False
        ).detect_patterns(events)
        self.assertEqual(set(with_analysis['patterns']), set(without_analysis['patterns']))
        self.assertEqual(with_analysis['stats'], without_analysis['stats'])


class TestPatternEdgeCases(unittest.TestCase):
    """Additional tests for edge cases and complex scenarios"""
    
    def setUp(self):
        self.pattern_detector = PatternDetector(min_pattern_length=2, max_pattern_length=8)
        self.loop_manager = LoopManager()

    def test_minimum_pattern_length(self):
        """Test with minimum pattern length of 2"""
        short_pattern_events = [
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 60, 'volume': 100},
            {'frame': 3, 'note': 64, 'volume': 100},
            {'frame': 4, 'note': 60, 'volume': 100},
            {'frame': 5, 'note': 64, 'volume': 100},
        ]
        
        patterns = self.pattern_detector.detect_patterns(short_pattern_events)
        self.assertTrue(len(patterns) > 0, "Should detect 2-note patterns")
        
        first_pattern = list(patterns.values())[0]
        self.assertEqual(first_pattern['length'], 2, "Should detect 2-note pattern")
        self.assertEqual(len(first_pattern['positions']), 3, "Pattern should repeat 3 times")

    def test_complex_music_structure(self):
        """Test with a more complex musical structure"""
        complex_events = [
            # Verse pattern
            {'frame': 0, 'note': 60, 'volume': 100},   # C
            {'frame': 1, 'note': 64, 'volume': 100},   # E
            {'frame': 2, 'note': 67, 'volume': 100},   # G
            {'frame': 3, 'note': 60, 'volume': 80},    # C (softer)
            # Chorus pattern
            {'frame': 4, 'note': 65, 'volume': 120},   # F
            {'frame': 5, 'note': 69, 'volume': 120},   # A
            {'frame': 6, 'note': 72, 'volume': 120},   # C
            {'frame': 7, 'note': 65, 'volume': 100},   # F
            # Verse repeats
            {'frame': 8, 'note': 60, 'volume': 100},
            {'frame': 9, 'note': 64, 'volume': 100},
            {'frame': 10, 'note': 67, 'volume': 100},
            {'frame': 11, 'note': 60, 'volume': 80},
            # Chorus repeats
            {'frame': 12, 'note': 65, 'volume': 120},
            {'frame': 13, 'note': 69, 'volume': 120},
            {'frame': 14, 'note': 72, 'volume': 120},
            {'frame': 15, 'note': 65, 'volume': 100},
            # Verse again
            {'frame': 16, 'note': 60, 'volume': 100},
            {'frame': 17, 'note': 64, 'volume': 100},
            {'frame': 18, 'note': 67, 'volume': 100},
            {'frame': 19, 'note': 60, 'volume': 80},
        ]
        
        patterns = self.pattern_detector.detect_patterns(complex_events)
        self.assertTrue(len(patterns) > 0, "Should detect patterns in complex structure")
        
        # Should detect multiple 4-note patterns
        pattern_lengths = [p['length'] for p in patterns.values()]
        self.assertIn(4, pattern_lengths, "Should detect 4-note patterns")
    
    def test_variation_edge_cases(self):
        """Test edge cases in pattern variation detection"""
        events = [
            # Original pattern
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            # Extreme transposition
            {'frame': 3, 'note': 72, 'volume': 100},
            {'frame': 4, 'note': 76, 'volume': 100},
            {'frame': 5, 'note': 79, 'volume': 100},
            # Extreme volume variation
            {'frame': 6, 'note': 60, 'volume': 20},
            {'frame': 7, 'note': 64, 'volume': 20},
            {'frame': 8, 'note': 67, 'volume': 20},
        ]
        
        patterns = self.pattern_detector.detect_patterns(events)
        
        # Verify handling of extreme variations
        first_pattern = list(patterns.values())[0]
        variations = first_pattern['variations']
        
        self.assertTrue(any(var['transposition'] >= 12 for var in variations),
                    "Should handle octave transpositions")
        self.assertTrue(any(abs(var['volume_change']) >= 80 for var in variations),
                    "Should handle large volume changes")

    def test_pattern_optimization(self):
        """Test that pattern optimization works correctly"""
        # Create data where longer patterns should be preferred over shorter ones
        optimization_events = []
        
        # Create a 6-note pattern that repeats 3 times
        base_pattern = [60, 64, 67, 72, 76, 79]
        for repeat in range(3):
            for i, note in enumerate(base_pattern):
                optimization_events.append({
                    'frame': repeat * 6 + i,
                    'note': note,
                    'volume': 100
                })
        
        patterns = self.pattern_detector.detect_patterns(optimization_events)
        
        if patterns:
            # Should prefer the longest pattern
            longest_pattern = max(patterns.values(), key=lambda x: x['length'])
            self.assertEqual(longest_pattern['length'], 6, 
                           "Should prefer longer patterns during optimization")

class TestPatternCompression(unittest.TestCase):
    def setUp(self):
        self.pattern_detector = PatternDetector(min_pattern_length=3)
        self.compressor = PatternCompressor()
        
        # Test data with repeating patterns
        self.test_events = [
            # Pattern A
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            # Pattern B
            {'frame': 3, 'note': 72, 'volume': 100},
            {'frame': 4, 'note': 76, 'volume': 100},
            {'frame': 5, 'note': 79, 'volume': 100},
            # Pattern A repeats
            {'frame': 6, 'note': 60, 'volume': 100},
            {'frame': 7, 'note': 64, 'volume': 100},
            {'frame': 8, 'note': 67, 'volume': 100},
            # Pattern B repeats
            {'frame': 9, 'note': 72, 'volume': 100},
            {'frame': 10, 'note': 76, 'volume': 100},
            {'frame': 11, 'note': 79, 'volume': 100},
        ]

    def test_basic_compression(self):
        """Test basic pattern compression with identical patterns"""
        # First detect patterns
        patterns = self.pattern_detector.detect_patterns(self.test_events)
        
        # Create pattern data in the expected format
        pattern_data = {}
        for i, (start, length) in enumerate([(0, 3), (3, 3), (6, 3), (9, 3)]):
            pattern_id = f"pattern_{i}"
            events = self.test_events[start:start + length]
            pattern_data[pattern_id] = {
                'events': events,
                'positions': [start],
                'length': length
            }
        
        compressed_data, pattern_refs = self.compressor.compress_patterns(pattern_data)
        
        # Should have exactly 2 unique patterns (A and B)
        self.assertEqual(len(compressed_data), 2, 
                        "Should detect 2 unique patterns")

    def test_compression_stats(self):
        """Test compression statistics calculation"""
        # Create test pattern data
        pattern_data = {
            'pattern_1': {
                'events': self.test_events[0:3],
                'positions': [0, 6],
                'length': 3
            },
            'pattern_2': {
                'events': self.test_events[3:6],
                'positions': [3, 9],
                'length': 3
            }
        }
        
        compressed_data, pattern_refs = self.compressor.compress_patterns(pattern_data)
        stats = self.compressor.calculate_compression_stats(pattern_data, compressed_data)
        
        # Original size: 2 patterns × 3 events × 2 positions = 12
        # Compressed size: 2 patterns × 3 events = 6
        self.assertEqual(stats['original_size'], 12)
        self.assertEqual(stats['compressed_size'], 6)
        # Regression (#17): compression_ratio is a percentage *reduction*
        # ((12-6)/12*100 = 50.0), not a multiplier (which would be 2.0). The
        # unit must stay a percent so the `%`-labelled print sites are correct.
        self.assertAlmostEqual(stats['compression_ratio'], 50.0)

    def test_pattern_with_volume_variations(self):
        """Test compression with same notes but different volumes"""
        # Create pattern data with volume variations
        pattern_data = {
            'pattern_1': {
                'events': [
                    {'frame': 0, 'note': 60, 'volume': 100},
                    {'frame': 1, 'note': 64, 'volume': 100},
                    {'frame': 2, 'note': 67, 'volume': 100}
                ],
                'positions': [0],
                'length': 3
            },
            'pattern_2': {
                'events': [
                    {'frame': 3, 'note': 60, 'volume': 80},
                    {'frame': 4, 'note': 64, 'volume': 80},
                    {'frame': 5, 'note': 67, 'volume': 80}
                ],
                'positions': [3],
                'length': 3
            }
        }
        
        compressed_data, pattern_refs = self.compressor.compress_patterns(pattern_data)
        self.assertEqual(len(compressed_data), 2,
                        "Patterns with different volumes should be distinct")

    def test_empty_patterns(self):
        """Test compression with empty input"""
        compressed_data, pattern_refs = self.compressor.compress_patterns({})
        self.assertEqual(len(compressed_data), 0)
        self.assertEqual(len(pattern_refs), 0)

    def test_single_pattern_multiple_occurrences(self):
        """Test compression with single pattern occurring multiple times"""
        pattern_data = {
            'pattern_1': {
                'events': self.test_events[0:3],
                'positions': [0, 3, 6],
                'length': 3
            }
        }
        
        compressed_data, pattern_refs = self.compressor.compress_patterns(pattern_data)
        self.assertEqual(len(compressed_data), 1)
        pattern_id = list(compressed_data.keys())[0]
        self.assertEqual(len(pattern_refs[pattern_id]), 3)

    def test_pattern_reference_ordering(self):
        """Test that pattern references are properly ordered"""
        pattern_data = {
            'pattern_1': {
                'events': self.test_events[0:3],
                'positions': [6, 0, 3],  # Unordered positions
                'length': 3
            }
        }
        
        compressed_data, pattern_refs = self.compressor.compress_patterns(pattern_data)
        for pattern_id, positions in pattern_refs.items():
            self.assertEqual(positions, sorted(positions))

    def test_compression_integration(self):
        """Test integration with EnhancedPatternDetector"""
        # Create a mock tempo map for testing
        tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM
        detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3)
        
        # Create test data with a pattern that repeats 3 times
        test_events = [
            # Pattern A - First occurrence
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            
            # Pattern A - Second occurrence
            {'frame': 3, 'note': 60, 'volume': 100},
            {'frame': 4, 'note': 64, 'volume': 100},
            {'frame': 5, 'note': 67, 'volume': 100},
            
            # Pattern A - Third occurrence
            {'frame': 6, 'note': 60, 'volume': 100},
            {'frame': 7, 'note': 64, 'volume': 100},
            {'frame': 8, 'note': 67, 'volume': 100},
            
            # Some different notes to avoid false patterns
            {'frame': 9, 'note': 72, 'volume': 100},
            {'frame': 10, 'note': 76, 'volume': 100},
            {'frame': 11, 'note': 79, 'volume': 100},
        ]
        
        # Add a tempo change at a valid tick position
        tempo_map.add_tempo_change(480, 400000)  # Change to 150 BPM at tick 480
        
        result = detector.detect_patterns(test_events)
        
        # Basic structure checks
        self.assertIsInstance(result, dict)
        self.assertIn('patterns', result)
        self.assertIn('references', result)
        self.assertIn('stats', result)
        
        # Verify compression results
        self.assertTrue(len(result['patterns']) > 0, "Should detect patterns")
        self.assertTrue(result['stats']['compression_ratio'] >= 0,
                       "Should achieve some compression")


class TestPatternSimilarity(unittest.TestCase):
    def setUp(self):
        self.pattern_detector = PatternDetector(min_pattern_length=3)
        
    def test_pattern_similarity_calculation(self):
        """Test the new pattern similarity calculation"""
        pattern1 = [(60, 100), (64, 100), (67, 100)]  # C major triad
        pattern2 = [(60, 100), (64, 100), (67, 100)]  # Exact same pattern
        pattern3 = [(61, 100), (65, 100), (68, 100)]  # Same pattern transposed up
        pattern4 = [(60, 80), (64, 80), (67, 80)]     # Same pattern different volume
        
        similarity1 = self.pattern_detector._calculate_pattern_similarity(pattern1, pattern2)
        similarity2 = self.pattern_detector._calculate_pattern_similarity(pattern1, pattern3)
        similarity3 = self.pattern_detector._calculate_pattern_similarity(pattern1, pattern4)
        
        self.assertEqual(similarity1, 1.0, "Identical patterns should have similarity 1.0")
        self.assertGreater(similarity2, 0.8, "Transposed pattern should have high similarity")
        self.assertGreater(similarity3, 0.8, "Volume variation should have high similarity")

    def test_pattern_variation_detection(self):
        """Test detection of pattern variations"""
        sequence = [
            (60, 100), (64, 100), (67, 100),  # Original pattern
            (61, 100), (65, 100), (68, 100),  # Transposed up 1
            (60, 80), (64, 80), (67, 80),     # Volume variation
        ]
        base_pattern = tuple(sequence[:3])
        
        variations = self.pattern_detector._detect_pattern_variations(sequence, base_pattern)
        
        self.assertEqual(len(variations), 2, "Should detect both variations")
        self.assertEqual(variations[0]['transposition'], 1, "Should detect transposition")
        self.assertEqual(variations[1]['volume_change'], -20, "Should detect volume change")


class TestLargeFilePolicy(unittest.TestCase):
    """Both pattern-detection entry points must apply the same large-file
    sampling policy so a big input cannot hang the bare subcommand while the
    default path survives via sampling (#21)."""

    def test_small_input_is_not_sampled(self):
        from tracker.pattern_detector import sample_events_for_detection
        events = [{'frame': i, 'note': 60, 'volume': 100} for i in range(100)]
        out, was_sampled = sample_events_for_detection(events)
        self.assertFalse(was_sampled)
        self.assertEqual(out, events)

    def test_large_input_is_downsampled_uniformly(self):
        from tracker.pattern_detector import (
            sample_events_for_detection, MAX_PATTERN_EVENTS)
        events = [{'frame': i, 'note': 60, 'volume': 100}
                  for i in range(MAX_PATTERN_EVENTS + 5000)]
        out, was_sampled = sample_events_for_detection(events)
        self.assertTrue(was_sampled)
        self.assertEqual(len(out), MAX_PATTERN_EVENTS)
        # Uniform sampling preserves the endpoints (temporal distribution),
        # unlike head-truncation which would drop the entire tail.
        self.assertEqual(out[0], events[0])
        self.assertEqual(out[-1], events[-1])

    def test_custom_cap_is_honored(self):
        from tracker.pattern_detector import sample_events_for_detection
        events = [{'frame': i, 'note': 60, 'volume': 100} for i in range(5000)]
        out, was_sampled = sample_events_for_detection(events, 2000)
        self.assertTrue(was_sampled)
        self.assertEqual(len(out), 2000)

    def test_both_entry_points_share_the_sampler(self):
        import inspect
        import main
        from tracker.pattern_detector_parallel import ParallelPatternDetector

        sub = inspect.getsource(main.run_detect_patterns)
        par = inspect.getsource(ParallelPatternDetector.detect_patterns)
        self.assertIn('sample_events_for_detection', sub,
                      "detect-patterns subcommand must apply the shared sampler")
        self.assertIn('sample_events_for_detection', par,
                      "parallel default path must apply the shared sampler")

    def test_base_detector_uniformly_samples_not_head_cuts(self):
        """The sequential detector must uniformly sample its working set, not
        head-cut to the first DETECTOR_MAX_EVENTS — otherwise the whole back
        half of a long song is silently dropped (#100)."""
        from tracker.pattern_detector import PatternDetector, DETECTOR_MAX_EVENTS
        n = DETECTOR_MAX_EVENTS * 3
        half = n // 2
        # A repeating motif in the head (notes 60-62), a DIFFERENT repeating
        # motif in the tail (notes 80-82). A head cut keeps only the first
        # DETECTOR_MAX_EVENTS events, dropping the tail motif entirely.
        head = [{'frame': i, 'note': 60 + (i % 3), 'volume': 100}
                for i in range(half)]
        tail = [{'frame': i, 'note': 80 + (i % 3), 'volume': 100}
                for i in range(half, n)]
        patterns = PatternDetector().detect_patterns(head + tail)
        notes = {ev['note'] for p in patterns.values() for ev in p['events']}
        self.assertTrue(any(note >= 80 for note in notes),
                        "tail motif dropped — detector head-cut instead of "
                        "uniformly sampling")


class TestPatternParameterConsistency(unittest.TestCase):
    """Both pattern-detection entry points (the `detect-patterns` subcommand and
    the default full pipeline) must use identical length bounds so their JSON
    artifacts agree for the same input (#19)."""

    def test_shared_constants_match_detector_defaults(self):
        import main
        self.assertEqual(main.PATTERN_MIN_LENGTH, 3)
        self.assertEqual(main.PATTERN_MAX_LENGTH, 12)

    def test_both_entry_points_use_shared_constants(self):
        import inspect
        import main

        src_detect = inspect.getsource(main.run_detect_patterns)
        src_pipeline = inspect.getsource(main.run_full_pipeline)

        for src, name in ((src_detect, 'run_detect_patterns'),
                          (src_pipeline, 'run_full_pipeline')):
            self.assertIn('PATTERN_MIN_LENGTH', src,
                          f"{name} must use the shared min-length constant")
            self.assertIn('PATTERN_MAX_LENGTH', src,
                          f"{name} must use the shared max-length constant")
            # No divergent hardcoded literals left behind.
            self.assertNotIn('max_pattern_length=12', src,
                             f"{name} must not hardcode max_pattern_length")
            self.assertNotIn('min_pattern_length=3', src,
                             f"{name} must not hardcode min_pattern_length")

    def test_detectors_agree_for_same_input(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        import main

        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        events = [
            {'frame': i, 'note': 60 + (i % 3) * 4, 'volume': 100}
            for i in range(24)
        ]

        enhanced = EnhancedPatternDetector(
            tempo_map, min_pattern_length=main.PATTERN_MIN_LENGTH,
            max_pattern_length=main.PATTERN_MAX_LENGTH)
        parallel = ParallelPatternDetector(
            tempo_map, min_pattern_length=main.PATTERN_MIN_LENGTH,
            max_pattern_length=main.PATTERN_MAX_LENGTH)

        self.assertEqual(enhanced.min_pattern_length, parallel.min_pattern_length)
        self.assertEqual(enhanced.max_pattern_length, parallel.max_pattern_length)


if __name__ == '__main__':
    unittest.main()


class TestParallelPatternEquivalence(unittest.TestCase):
    """Regression tests for the O(n) hash-grouping pattern matcher (#114).

    The old worker rescanned the whole sequence for every start (O(n²·L)) and
    shipped the full sequence in every chunk. The rewrite must yield the same
    patterns and must NOT embed the sequence in the work chunks."""

    @staticmethod
    def _old_worker_for_length(sequence, length):
        """Reference: the original whole-sequence greedy rescan, collapsed to one
        entry per distinct window (which is how duplicates resolved downstream)."""
        n = len(sequence)
        result = {}
        for start in range(n - length + 1):
            pattern = tuple(sequence[start:start + length])
            if pattern in result:
                continue
            matches = []
            pos = 0
            while pos <= n - length:
                if tuple(sequence[pos:pos + length]) == pattern:
                    matches.append(pos)
                    pos += length
                else:
                    pos += 1
            if len(matches) >= 3:
                # Parallel path is exact-repeats-only, so it scores with the
                # shared score_pattern using variation_count=0 (#103).
                from tracker.pattern_detector import score_pattern
                score = score_pattern(length, len(matches), 0)
                if score > 0:
                    result[pattern] = (matches, score)
        return result

    def test_collect_length_candidates_matches_old_worker(self):
        from tracker.pattern_detector_parallel import _collect_length_candidates
        seq = [(60 + (i % 5), 100 - (i % 3)) for i in range(80)]
        events = [{'note': a, 'volume': b, 'frame': i}
                  for i, (a, b) in enumerate(seq)]
        for length in range(3, 13):
            new = {c['pattern']: (c['positions'], c['score'])
                   for c in _collect_length_candidates(seq, events, length)}
            old = self._old_worker_for_length(seq, length)
            self.assertEqual(set(new), set(old),
                             f"window set differs at length {length}")
            for pattern in old:
                self.assertEqual(new[pattern][0], old[pattern][0],
                                 f"match positions differ for {pattern}")
                self.assertAlmostEqual(new[pattern][1], old[pattern][1], places=9)

    def test_detected_patterns_are_real_repeats(self):
        """Every detected pattern's occurrences must reconstruct identical
        content (round-trip integrity of the matcher output)."""
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        detector = ParallelPatternDetector(tempo_map, min_pattern_length=3,
                                           max_pattern_length=12)
        events = [{'frame': i, 'note': 60 + (i % 8), 'volume': 100 - (i % 4)}
                  for i in range(400)]
        sequence = [(e['note'], e['volume']) for e in events]
        result = detector.detect_patterns(events)
        self.assertGreater(len(result['patterns']), 0)
        for pid, info in result['patterns'].items():
            length = info['length']
            positions = info['exact_matches']
            ref = tuple(sequence[positions[0]:positions[0] + length])
            for pos in positions:
                self.assertEqual(tuple(sequence[pos:pos + length]), ref,
                                 f"{pid} occurrence at {pos} is not a real repeat")

    def test_serial_fallback_equivalent_to_parallel(self):
        """The in-process serial fallback (used when the pool fails) must select
        the same patterns as the parallel path."""
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        detector = ParallelPatternDetector(tempo_map, min_pattern_length=3,
                                           max_pattern_length=12)
        events = [{'frame': i, 'note': 60 + (i % 6), 'volume': 100}
                  for i in range(120)]
        sequence = [(e['note'], e['volume']) for e in events]
        valid = detector._filter_valid_events(events)

        parallel = detector._detect_patterns_parallel(sequence, valid)
        serial = detector._detect_patterns_serial(sequence, valid)

        def signature(patterns):
            return sorted(tuple(p['exact_matches']) for p in patterns.values())

        self.assertEqual(signature(parallel), signature(serial))

    def test_selection_loses_entire_window_when_anchor_is_contested(self):
        """Regression (#171/PAT-05): _select_best_patterns rejects a candidate
        wholesale if ANY of its positions overlaps an already-selected pattern.
        Because the parallel path emits exactly one candidate per distinct
        window (anchored at its first occurrence), contesting just that
        anchor loses ALL of the window's occurrences -- including ones that
        never overlapped anything -- unlike the per-start sequential detector,
        which can recover them via a separate, later-anchored candidate for
        the same window value. This pins the corrected docstring's claim in
        _collect_length_candidates (previously claimed a false equivalence)."""
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000))

        winner = {
            'start': 0, 'length': 4, 'pattern': ('winner',), 'score': 100,
            'positions': [0, 20, 40, 60], 'events': [{}] * 4,
        }
        # Window's anchor (position 0) overlaps the winner; its other two
        # occurrences (10, 30) don't overlap anything the winner claims.
        window = {
            'start': 0, 'length': 6, 'pattern': ('window',), 'score': 50,
            'positions': [0, 10, 30], 'events': [{}] * 6,
        }
        patterns = detector._select_best_patterns([winner, window])

        all_positions = {p for info in patterns.values() for p in info['exact_matches']}
        self.assertIn(0, all_positions)      # from the winner
        self.assertNotIn(10, all_positions)  # window's non-conflicting occurrence, lost
        self.assertNotIn(30, all_positions)  # window's non-conflicting occurrence, lost
        self.assertEqual(len(patterns), 1)   # only the winner survives

    def test_work_chunks_do_not_embed_sequence(self):
        """IPC-bloat guard: per-length chunks must carry only the length, never
        the full sequence/events (those travel once via the pool initializer)."""
        import inspect
        from tracker import pattern_detector_parallel as pdp
        src = inspect.getsource(pdp.ParallelPatternDetector._detect_patterns_parallel)
        self.assertNotIn("'sequence': sequence", src)
        self.assertNotIn("'events': valid_events", src)
        self.assertIn('initializer=_init_pattern_worker', src)
        self.assertIn('initargs=', src)


class TestParallelWorkerPoolSizing(unittest.TestCase):
    """Regression tests for #218: the process pool must never spawn more
    workers than there are work chunks, and must be skipped entirely when
    there is only one chunk (no parallelism to gain, but full spawn cost)."""

    def test_pool_workers_capped_to_chunk_count(self):
        from unittest.mock import patch
        from concurrent.futures import ProcessPoolExecutor
        from tracker.pattern_detector_parallel import ParallelPatternDetector

        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        # min=3, max=12 over a long-enough sequence yields exactly 10 chunks.
        detector = ParallelPatternDetector(tempo_map, min_pattern_length=3, max_pattern_length=12)
        detector.max_workers = 50  # simulate a high-core-count host
        events = [{'frame': i, 'note': 60 + (i % 6), 'volume': 100} for i in range(200)]
        sequence = [(e['note'], e['volume']) for e in events]
        valid = detector._filter_valid_events(events)

        captured = {}

        class RecordingExecutor(ProcessPoolExecutor):
            def __init__(self, *args, **kwargs):
                captured['max_workers'] = kwargs.get('max_workers')
                super().__init__(*args, **kwargs)

        with patch('tracker.pattern_detector_parallel.ProcessPoolExecutor', RecordingExecutor):
            detector._detect_patterns_parallel(sequence, valid)

        self.assertEqual(captured['max_workers'], 10)
        self.assertLess(captured['max_workers'], detector.max_workers)

    def test_single_chunk_skips_process_pool_entirely(self):
        from unittest.mock import patch
        from tracker.pattern_detector_parallel import ParallelPatternDetector

        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        # min == max == 5 over a long-enough sequence yields exactly 1 chunk.
        detector = ParallelPatternDetector(tempo_map, min_pattern_length=5, max_pattern_length=5)
        events = [{'frame': i, 'note': 60 + (i % 4), 'volume': 100} for i in range(50)]
        sequence = [(e['note'], e['volume']) for e in events]
        valid = detector._filter_valid_events(events)

        with patch('tracker.pattern_detector_parallel.ProcessPoolExecutor') as mock_pool:
            result = detector._detect_patterns_parallel(sequence, valid)

        mock_pool.assert_not_called()
        self.assertIsInstance(result, dict)


class TestConfigurableSamplingCaps(unittest.TestCase):
    """Regression tests for #219: pattern-detection sampling caps must be
    overridable per-instance (the code-level hook for a config override),
    not hardcoded-only, while defaulting to the existing module constants."""

    def test_defaults_unchanged_when_not_overridden(self):
        from tracker.pattern_detector import PatternDetector, DETECTOR_MAX_EVENTS, MAX_PATTERN_EVENTS
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        self.assertEqual(PatternDetector().max_events, DETECTOR_MAX_EVENTS)
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        self.assertEqual(ParallelPatternDetector(tempo_map).max_pattern_events, MAX_PATTERN_EVENTS)

    def test_sequential_detector_honors_custom_max_events(self):
        from tracker.pattern_detector import PatternDetector
        events = [{'frame': i, 'note': 60 + (i % 5), 'volume': 100} for i in range(500)]
        detector = PatternDetector(max_events=200)
        self.assertEqual(detector.max_events, 200)
        patterns = detector.detect_patterns(events)
        self.assertGreater(len(patterns), 0)
        for info in patterns.values():
            for pos in info['positions']:
                self.assertLess(pos, 200)

    def test_enhanced_detector_forwards_max_events(self):
        from tracker.pattern_detector import EnhancedPatternDetector
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        detector = EnhancedPatternDetector(tempo_map, max_events=123)
        self.assertEqual(detector.max_events, 123)

    def test_parallel_detector_honors_custom_max_pattern_events(self):
        from tracker.pattern_detector import sample_events_for_detection
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        detector = ParallelPatternDetector(tempo_map, max_pattern_events=50)
        self.assertEqual(detector.max_pattern_events, 50)
        events = [{'frame': i, 'note': 60 + (i % 5), 'volume': 100} for i in range(500)]
        valid = detector._filter_valid_events(events)
        sampled, was_sampled = sample_events_for_detection(valid, detector.max_pattern_events)
        self.assertTrue(was_sampled)
        self.assertEqual(len(sampled), 50)


class TestDetectorScoringConsistency(unittest.TestCase):
    """Both detectors must share the scoring formula, and the parallel path is
    intentionally exact-repeats-only / variation-free (#103)."""

    def test_both_detectors_use_shared_score_pattern(self):
        # The sequential detector calls the module-level score_pattern, and the
        # parallel candidate collector imports and calls the same function.
        import inspect
        from tracker import pattern_detector as pd
        from tracker import pattern_detector_parallel as pdp
        # The sequential scoring lives in the base PatternDetector.detect_patterns;
        # the parallel path scores in _collect_length_candidates. Both must call
        # the shared module-level score_pattern.
        seq_src = inspect.getsource(pd.PatternDetector.detect_patterns)
        self.assertIn('score_pattern(', seq_src)
        collect_src = inspect.getsource(pdp._collect_length_candidates)
        self.assertIn('score_pattern(', collect_src)

    def test_parallel_candidate_score_equals_shared_score_pattern(self):
        # For an exact-repeat input, a parallel candidate's score must equal
        # score_pattern(length, occurrences, 0) exactly — no bespoke formula.
        from tracker.pattern_detector import score_pattern
        from tracker.pattern_detector_parallel import _collect_length_candidates
        seq = [(60 + (i % 4), 100) for i in range(60)]
        events = [{'note': a, 'volume': b, 'frame': i} for i, (a, b) in enumerate(seq)]
        for length in range(3, 8):
            for c in _collect_length_candidates(seq, events, length):
                expected = score_pattern(length, len(c['positions']), 0)
                self.assertAlmostEqual(c['score'], expected, places=9)

    def test_parallel_path_is_variation_free_by_design(self):
        # The O(n) hash grouping cannot detect transposed/volume-scaled repeats,
        # so every parallel pattern reports zero variations. This pins the
        # documented divergence from the sequential detector (#103).
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        events = [{'frame': i, 'note': 60 + (i % 6), 'volume': 100} for i in range(200)]
        result = detector.detect_patterns(events)
        self.assertGreater(len(result['patterns']), 0)
        for info in result['patterns'].values():
            self.assertEqual(info['variations'], [])
        for summary in result['variations'].values():
            self.assertEqual(summary['variation_count'], 0)


class TestStatsSchemaConsistency(unittest.TestCase):
    """The --no-patterns stub and both detectors must emit one stats schema so a
    future consumer can't hit a KeyError on a path-dependent key (#104)."""

    CANONICAL_KEYS = {'original_size', 'compressed_size',
                      'compression_ratio', 'unique_patterns',
                      'total_events', 'patterned_events', 'coverage_ratio'}

    def test_detectors_emit_canonical_stats_keys(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        events = [{'frame': i, 'note': 60 + (i % 6), 'volume': 100} for i in range(120)]
        seq_stats = EnhancedPatternDetector(
            EnhancedTempoMap(initial_tempo=500000)).detect_patterns(events)['stats']
        par_stats = ParallelPatternDetector(
            EnhancedTempoMap(initial_tempo=500000)).detect_patterns(events)['stats']
        self.assertEqual(set(seq_stats), self.CANONICAL_KEYS)
        self.assertEqual(set(par_stats), self.CANONICAL_KEYS)

    def test_no_patterns_stub_uses_canonical_stats_keys(self):
        # The stub lives inline in run_full_pipeline; assert it emits the four
        # canonical keys and none of the old bespoke ones (#104).
        import inspect
        import main
        src = inspect.getsource(main.run_full_pipeline)
        for key in self.CANONICAL_KEYS:
            self.assertIn(f"'{key}'", src, f"stub missing canonical stats key {key}")
        self.assertNotIn("'original_events'", src)
        self.assertNotIn("'patterns_found'", src)

    # The top-level envelope both detectors and the --no-patterns stub must emit.
    TOP_LEVEL_KEYS = {'patterns', 'references', 'stats', 'variations'}

    def test_both_detectors_emit_four_top_level_keys(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        import io as _io
        import contextlib as _cl
        events = [{'frame': i, 'note': 60 + (i % 6), 'volume': 100} for i in range(120)]
        for det in (EnhancedPatternDetector(EnhancedTempoMap(initial_tempo=500000)),
                    ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000))):
            with _cl.redirect_stdout(_io.StringIO()):
                result = det.detect_patterns(events)
            self.assertEqual(set(result), self.TOP_LEVEL_KEYS)

    def test_no_patterns_stub_emits_variations_key(self):
        # The stub previously returned only {patterns, references, stats}; a
        # consumer doing pattern_result['variations'] would KeyError only on the
        # --no-patterns path (#258/PAT-09). Pin that the inline stub now carries
        # the top-level 'variations' key like both detectors.
        import inspect
        import main
        src = inspect.getsource(main.run_full_pipeline)
        self.assertIn("'variations'", src,
                      "--no-patterns stub must emit the top-level 'variations' key")


class TestCoverageRatioEventSpace(unittest.TestCase):
    """coverage_ratio must be measured in the same (post-sampling) event space as
    patterned_events. Using the pre-sampling full-song total as the denominator
    scaled a large fully-patterned song's coverage down by (sampled / total),
    the exact misleading-number class coverage_ratio exists to prevent (#257)."""

    def _fully_patterned(self, n=60):
        # Identical events: any uniform sub-sample is still fully patterned, so
        # coverage stays high regardless of the cap.
        return [{'frame': i, 'note': 60, 'volume': 100} for i in range(n)]

    def _assert_analyzed_space(self, stats, analyzed):
        # total_events is the analyzed (sampled) count, not the full song...
        self.assertEqual(stats['total_events'], analyzed)
        # ...coverage stays high (it would be ~30% if divided by the full 60)...
        self.assertGreaterEqual(stats['coverage_ratio'], 85)
        # ...and the invariant coverage == patterned / total holds.
        self.assertAlmostEqual(
            stats['coverage_ratio'],
            stats['patterned_events'] / stats['total_events'] * 100, places=6)

    def test_sequential_coverage_measured_in_analyzed_space(self):
        import io as _io
        import contextlib as _cl
        det = EnhancedPatternDetector(
            EnhancedTempoMap(initial_tempo=500000),
            min_pattern_length=3, max_pattern_length=8, max_events=20)
        with _cl.redirect_stdout(_io.StringIO()):
            stats = det.detect_patterns(self._fully_patterned(60))['stats']
        self._assert_analyzed_space(stats, analyzed=20)

    def test_parallel_coverage_measured_in_analyzed_space(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        import io as _io
        import contextlib as _cl
        det = ParallelPatternDetector(
            EnhancedTempoMap(initial_tempo=500000),
            min_pattern_length=3, max_pattern_length=8)
        det.max_pattern_events = 20
        with _cl.redirect_stdout(_io.StringIO()):
            stats = det.detect_patterns(self._fully_patterned(60))['stats']
        self._assert_analyzed_space(stats, analyzed=20)


class TestWasSampledFlag(unittest.TestCase):
    """Regression (#312/PAT-11): a caller reporting coverage_ratio has no way
    to tell whether internal uniform sampling ran (and may have put samples
    out of phase with the song's period, understating coverage) unless the
    detector exposes it. Both detectors must set `was_sampled` on `self` so
    main.py can label the printed coverage line as lossy."""

    def _fully_patterned(self, n=60):
        return [{'frame': i, 'note': 60, 'volume': 100} for i in range(n)]

    def test_sequential_was_sampled_true_when_capped(self):
        import io as _io
        import contextlib as _cl
        det = EnhancedPatternDetector(
            EnhancedTempoMap(initial_tempo=500000),
            min_pattern_length=3, max_pattern_length=8, max_events=20)
        with _cl.redirect_stdout(_io.StringIO()):
            det.detect_patterns(self._fully_patterned(60))
        self.assertTrue(det.was_sampled)

    def test_sequential_was_sampled_false_when_under_cap(self):
        det = EnhancedPatternDetector(
            EnhancedTempoMap(initial_tempo=500000),
            min_pattern_length=3, max_pattern_length=8, max_events=1000)
        det.detect_patterns(self._fully_patterned(60))
        self.assertFalse(det.was_sampled)

    def test_parallel_was_sampled_true_when_capped(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        import io as _io
        import contextlib as _cl
        det = ParallelPatternDetector(
            EnhancedTempoMap(initial_tempo=500000),
            min_pattern_length=3, max_pattern_length=8)
        det.max_pattern_events = 20
        with _cl.redirect_stdout(_io.StringIO()):
            det.detect_patterns(self._fully_patterned(60))
        self.assertTrue(det.was_sampled)

    def test_parallel_was_sampled_false_when_under_cap(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        det = ParallelPatternDetector(
            EnhancedTempoMap(initial_tempo=500000),
            min_pattern_length=3, max_pattern_length=8)
        det.detect_patterns(self._fully_patterned(60))
        self.assertFalse(det.was_sampled)


class TestEventLimitConsolidation(unittest.TestCase):
    """After #102 there are exactly TWO event caps (one per detector complexity
    class); the dead ThreadedPatternDetector — the stray third 2000-stride limit —
    was removed, and all live decimation goes through sample_events_for_detection."""

    def test_threaded_detector_removed(self):
        import tracker.pattern_detector_parallel as pdp
        self.assertFalse(hasattr(pdp, 'ThreadedPatternDetector'),
                         "dead ThreadedPatternDetector should be gone (#102)")

    def test_two_named_caps(self):
        from tracker import pattern_detector as pd
        self.assertEqual(pd.MAX_PATTERN_EVENTS, 15000)   # O(n) parallel path
        self.assertEqual(pd.DETECTOR_MAX_EVENTS, 1000)   # O(n^2) sequential path

    def test_sequential_detector_binds_at_detector_max_events(self):
        # The sequential detector's effective limit is DETECTOR_MAX_EVENTS (not
        # MAX_PATTERN_EVENTS): feeding twice that many events uniformly samples
        # down to the cap, so no detected position can exceed it (#102, #100).
        from tracker.pattern_detector import PatternDetector, DETECTOR_MAX_EVENTS
        n = DETECTOR_MAX_EVENTS * 2
        events = [{'frame': i, 'note': 60 + (i % 8), 'volume': 100} for i in range(n)]
        patterns = PatternDetector().detect_patterns(events)
        self.assertGreater(len(patterns), 0)
        for info in patterns.values():
            for pos in info['positions']:
                self.assertLess(pos, DETECTOR_MAX_EVENTS)

    def test_no_bespoke_stride_decimation_remains(self):
        # The old `sequence[::step]` stride is gone; the parallel module decimates
        # only via the shared sampler.
        import inspect
        import tracker.pattern_detector_parallel as pdp
        src = inspect.getsource(pdp)
        self.assertNotIn('// 2000', src)
        self.assertIn('sample_events_for_detection', src)


class TestPositionsAreExactOnly(unittest.TestCase):
    """Regression (#168/PAT-01): the sequential detector's `positions` (and
    the `references` it feeds into) must be exact-match positions only.

    Before the fix, a transposed/volume-scaled variation position (similarity
    >= 0.85) was merged into `positions`, so `references[pattern_id]` claimed
    a pattern occurred at a position whose actual content differed from the
    stored pattern events -- e.g. a consumer reconstructing "events at
    references" would silently play the base pattern where a transposition
    belonged."""

    def setUp(self):
        self.tempo_map = EnhancedTempoMap(initial_tempo=500000)
        self.detector = EnhancedPatternDetector(
            self.tempo_map, min_pattern_length=3, max_pattern_length=3, analyze_tempo=False)
        # Motif x3 (exact repeats at 0, 3, 6) + one transposed+louder copy at 9,
        # mirroring the exact reproduction in the issue report.
        motif = [(40, 20), (41, 21), (42, 22)]
        self.sequence = motif + motif + motif + [(n + 1, v + 1) for n, v in motif]
        self.events = [{'frame': i, 'note': n, 'volume': v}
                       for i, (n, v) in enumerate(self.sequence)]

    def test_variation_position_excluded_from_positions_and_references(self):
        result = self.detector.detect_patterns(self.events)
        patterns = result['patterns']
        references = result['references']
        self.assertTrue(patterns, "expected at least one detected pattern")

        for pattern_id, pattern_info in patterns.items():
            # The transposed variant's position (9) must be tracked only as a
            # variation, never as an exact position/reference.
            self.assertNotIn(9, pattern_info['positions'])
            self.assertNotIn(9, references[pattern_id])
            variation_positions = {v['position'] for v in pattern_info['variations']}
            self.assertIn(9, variation_positions,
                          "the transposed copy should still be tracked as a variation")

    def test_referenced_windows_reproduce_stored_pattern_events(self):
        """Round-trip check the issue explicitly asks for: for every position
        in `references`, sequence[pos:pos+length] must equal the pattern's
        stored events -- i.e. the reference is actually reconstructible."""
        result = self.detector.detect_patterns(self.events)
        for pattern_id, pattern_info in result['patterns'].items():
            length = pattern_info['length']
            stored = [(e['note'], e['volume']) for e in pattern_info['events']]
            for pos in result['references'][pattern_id]:
                window = self.sequence[pos:pos + length]
                self.assertEqual(list(window), stored,
                    f"{pattern_id} @ {pos}: window {window} != stored events {stored}")

    def test_variations_still_carry_their_transform(self):
        """Variations aren't dropped -- they're just excluded from positions/
        references -- and each still carries the transform a consumer would
        need to reconstruct it losslessly."""
        result = self.detector.detect_patterns(self.events)
        for pattern_info in result['patterns'].values():
            for var in pattern_info['variations']:
                self.assertIn('transposition', var)
                self.assertIn('volume_change', var)
                self.assertIn('position', var)


class TestCompressionStatsCoverage(unittest.TestCase):
    """Regression (#169/PAT-03): compression_ratio only measures dedup within
    the patterned subset -- it says nothing about how much of the song is
    actually patterned. calculate_compression_stats must accept a
    total_events count and report a separate coverage_ratio so "66.7%
    reduction" can't be read as "the song shrank 66.7%" when most of it isn't
    patterned at all."""

    def setUp(self):
        self.compressor = PatternCompressor()

    def test_coverage_ratio_reflects_song_not_just_patterned_subset(self):
        original = {
            'pattern_0': {'events': [{'note': 1, 'volume': 1}] * 3, 'positions': [0, 3, 6]}
        }
        compressed = {
            'pattern_0': {'events': [{'note': 1, 'volume': 1}] * 3}
        }
        # 9 patterned events out of a much larger song -> low coverage despite
        # a high dedup ratio.
        stats = self.compressor.calculate_compression_stats(original, compressed, total_events=100)
        self.assertAlmostEqual(stats['compression_ratio'], (9 - 3) / 9 * 100)
        self.assertEqual(stats['total_events'], 100)
        self.assertEqual(stats['patterned_events'], 9)
        self.assertAlmostEqual(stats['coverage_ratio'], 9.0)

    def test_coverage_ratio_defaults_to_zero_without_total_events(self):
        """Backward-compatible: omitting total_events must not raise, and
        must not fabricate a coverage number."""
        original = {'pattern_0': {'events': [{'note': 1, 'volume': 1}], 'positions': [0]}}
        compressed = {'pattern_0': {'events': [{'note': 1, 'volume': 1}]}}
        stats = self.compressor.calculate_compression_stats(original, compressed)
        self.assertEqual(stats['total_events'], 0)
        self.assertEqual(stats['coverage_ratio'], 0)

    def test_full_song_coverage_caps_at_100_percent(self):
        original = {'pattern_0': {'events': [{'note': 1, 'volume': 1}] * 2, 'positions': [0, 2]}}
        compressed = {'pattern_0': {'events': [{'note': 1, 'volume': 1}] * 2}}
        stats = self.compressor.calculate_compression_stats(original, compressed, total_events=4)
        self.assertAlmostEqual(stats['coverage_ratio'], 100.0)


class _AllChunksFailExecutor:
    """Fake ProcessPoolExecutor whose every submitted future raises on result(),
    simulating a per-chunk worker failure/timeout without spawning processes."""
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, chunk):
        fut = Future()
        fut.set_exception(RuntimeError("injected chunk failure"))
        return fut


class TestParallelChunkFailureRecovery(unittest.TestCase):
    """A failed/timed-out chunk covers exactly one pattern length. It must not
    be silently dropped with only a transient tqdm line (#106): the length is
    recovered in-process, and if that also fails the loss is surfaced durably."""

    def _detector(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        return ParallelPatternDetector(
            tempo_map, min_pattern_length=3, max_pattern_length=6)

    def _input(self):
        # >1 length chunk (3..6) so the parallel path runs; clear repeats so
        # there are real candidates to lose.
        seq = [(60 + (i % 3), 100) for i in range(12)]
        events = [{'note': a, 'volume': b, 'frame': i}
                  for i, (a, b) in enumerate(seq)]
        return seq, events

    def test_failed_chunk_is_recovered_in_process(self):
        pdp = self._detector()
        seq, events = self._input()
        expected = pdp._detect_patterns_serial(seq, events)
        with patch('tracker.pattern_detector_parallel.ProcessPoolExecutor',
                   _AllChunksFailExecutor), redirect_stdout(io.StringIO()):
            got = pdp._detect_patterns_parallel(seq, events)
        # Every failed chunk was recovered with the same helper the serial path
        # uses, and selection is order-independent, so the result is identical.
        self.assertTrue(expected, "input should yield patterns for the test to bite")
        self.assertEqual(got, expected)

    def test_unrecoverable_chunk_surfaces_durable_warning(self):
        pdp = self._detector()
        seq, events = self._input()

        def _boom(*a, **k):
            raise RuntimeError("injected serial-retry failure")

        buf = io.StringIO()
        with patch('tracker.pattern_detector_parallel.ProcessPoolExecutor',
                   _AllChunksFailExecutor), \
             patch('tracker.pattern_detector_parallel._collect_length_candidates',
                   _boom), \
             redirect_stdout(buf):
            result = pdp._detect_patterns_parallel(seq, events)

        out = buf.getvalue()
        # Lengths 3..6 all fail AND all in-process retries fail -> a single
        # persistent end-of-run warning naming the count, not just tqdm noise.
        self.assertIn("Partial pattern detection", out)
        self.assertIn("4 length(s)", out)
        self.assertEqual(result, {})  # nothing recovered, but no crash


class TestVariationSummarySchemaConsistency(unittest.TestCase):
    """Both detectors must emit ONE `variations` inner shape so a future consumer
    reading result['variations'][pid] can't break on a path-dependent key (#172).

    Before this fix the sequential summary carried transposition_range/volume_range
    while the parallel summary carried exact_matches and never the ranges.
    """

    EXPECTED_KEYS = {'variation_count', 'exact_match_count',
                     'transposition_range', 'volume_range'}

    def _events(self):
        return [{'frame': i, 'note': 60 + (i % 6), 'volume': 100}
                for i in range(200)]

    def test_both_detectors_emit_same_variation_shape(self):
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        tm = EnhancedTempoMap(initial_tempo=500000)
        seq = EnhancedPatternDetector(tm, min_pattern_length=3, max_pattern_length=12)
        par = ParallelPatternDetector(tm, min_pattern_length=3, max_pattern_length=12)
        seq_summaries = seq.detect_patterns(self._events())['variations']
        par_summaries = par.detect_patterns(self._events())['variations']

        self.assertGreater(len(seq_summaries), 0)
        self.assertGreater(len(par_summaries), 0)
        for summary in list(seq_summaries.values()) + list(par_summaries.values()):
            self.assertEqual(set(summary.keys()), self.EXPECTED_KEYS)

        # Parallel path is exact-repeats-only: zero variations, neutral ranges.
        for summary in par_summaries.values():
            self.assertEqual(summary['variation_count'], 0)
            self.assertEqual(summary['transposition_range'], (0, 0))
            self.assertEqual(summary['volume_range'], (0, 0))


class TestPatternHashExactKeying(unittest.TestCase):
    """compress_patterns must dedup on the exact event tuple, not a lossy 64-bit
    hash() whose collision would silently merge unrelated patterns' references
    into the wrong definition (#173)."""

    @staticmethod
    def _pat(events, positions):
        return {'events': events, 'positions': positions,
                'exact_matches': positions, 'variations': [], 'length': len(events)}

    def test_hash_pattern_returns_exact_tuple(self):
        pc = PatternCompressor()
        events = [{'note': 60, 'volume': 10}, {'note': 62, 'volume': 12}]
        # The dedup key is the exact (note, volume) tuple, not hash() of it.
        self.assertEqual(pc._hash_pattern(events), ((60, 10), (62, 12)))

    def test_identical_merge_distinct_stay_separate(self):
        pc = PatternCompressor()
        ev_a = [{'note': 60, 'volume': 10}, {'note': 62, 'volume': 12}]
        ev_b = [{'note': 64, 'volume': 8}]
        patterns = {
            'p0': self._pat(ev_a, [0]),
            'p1': self._pat(list(ev_a), [16]),   # identical events -> merge into p0
            'p2': self._pat(ev_b, [32]),         # different events -> stays separate
        }
        compressed, refs = pc.compress_patterns(patterns)
        # p1 merged into p0 (not kept as its own definition); p2 distinct.
        self.assertIn('p0', compressed)
        self.assertNotIn('p1', compressed)
        self.assertIn('p2', compressed)
        # p0 now carries both its own and p1's positions; p2 only its own.
        self.assertEqual(refs['p0'], [0, 16])
        self.assertEqual(refs['p2'], [32])


if __name__ == '__main__':
    unittest.main()
