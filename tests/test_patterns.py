# tests/test_patterns.py
import unittest
from tracker.pattern_detector import PatternDetector
from tracker.loop_manager import LoopManager

class TestPatternDetection(unittest.TestCase):
    def setUp(self):
        self.pattern_detector = PatternDetector(min_pattern_length=3)
        self.loop_manager = LoopManager()
        
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
        
        self.assertIsInstance(jump_table, dict, "Jump table should be a dictionary")
        if loops:  # Only test if loops were detected
            self.assertTrue(len(jump_table) > 0, "Jump table should contain entries")
            
            # Verify jump table structure
            for end_pos, start_pos in jump_table.items():
                self.assertTrue(isinstance(end_pos, int), "Jump table keys should be integers")
                self.assertTrue(isinstance(start_pos, int), "Jump table values should be integers")
                self.assertTrue(start_pos < end_pos, "Jump should go backwards")

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

if __name__ == '__main__':
    unittest.main()
