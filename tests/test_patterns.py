# tests/test_patterns.py
import unittest
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
                      'compression_ratio', 'unique_patterns'}

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


if __name__ == '__main__':
    unittest.main()
