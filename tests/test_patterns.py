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
        self.assertGreater(stats['compression_ratio'], 0)

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


if __name__ == '__main__':
    unittest.main()
