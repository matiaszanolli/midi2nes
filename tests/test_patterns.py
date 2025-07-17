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
