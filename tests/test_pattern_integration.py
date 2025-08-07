# tests/test_pattern_integration.py
import unittest
from tracker.pattern_detector import PatternDetector, EnhancedPatternDetector
from tracker.loop_manager import LoopManager, EnhancedLoopManager
from tracker.tempo_map import EnhancedTempoMap
from tracker.parser import parse_midi_to_frames
import tempfile
import os
import json

class TestPatternDetectorIntegration(unittest.TestCase):
    """Integration tests to ensure PatternDetector and EnhancedPatternDetector work together correctly"""
    
    def setUp(self):
        self.tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM
        self.base_detector = PatternDetector(min_pattern_length=3)
        self.enhanced_detector = EnhancedPatternDetector(self.tempo_map, min_pattern_length=3)
        
        # Common test events with clear patterns
        self.test_events = [
            # Pattern A - occurs 3 times
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
            
            {'frame': 3, 'note': 60, 'volume': 100},
            {'frame': 4, 'note': 64, 'volume': 100},
            {'frame': 5, 'note': 67, 'volume': 100},
            
            {'frame': 6, 'note': 60, 'volume': 100},
            {'frame': 7, 'note': 64, 'volume': 100},
            {'frame': 8, 'note': 67, 'volume': 100},
        ]

    def test_pattern_structure_compatibility(self):
        """Test that both detectors return compatible pattern structures"""
        base_patterns = self.base_detector.detect_patterns(self.test_events)
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        # Enhanced detector should return dict with patterns key
        self.assertIsInstance(enhanced_result, dict)
        self.assertIn('patterns', enhanced_result)
        enhanced_patterns = enhanced_result['patterns']
        
        # Both should return dictionaries
        self.assertIsInstance(base_patterns, dict)
        self.assertIsInstance(enhanced_patterns, dict)
        
        # If patterns found, both should have compatible structure
        if base_patterns and enhanced_patterns:
            base_pattern = list(base_patterns.values())[0]
            enhanced_pattern = list(enhanced_patterns.values())[0]
            
            # Both should have required keys
            required_keys = ['events', 'positions', 'length', 'exact_matches', 'variations']
            for key in required_keys:
                self.assertIn(key, base_pattern, f"Base pattern missing {key}")
                self.assertIn(key, enhanced_pattern, f"Enhanced pattern missing {key}")

    def test_loop_manager_integration(self):
        """Test that LoopManager can work with patterns from both detectors"""
        base_patterns = self.base_detector.detect_patterns(self.test_events)
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        # Test with base LoopManager
        loop_manager = LoopManager(simple_mode=True)
        
        if base_patterns:
            # Should work with base patterns
            base_loops = loop_manager.detect_loops(self.test_events, base_patterns)
            self.assertIsInstance(base_loops, dict)
            
        if enhanced_result['patterns']:
            # Should work with enhanced patterns
            enhanced_loops = loop_manager.detect_loops(self.test_events, enhanced_result['patterns'])
            self.assertIsInstance(enhanced_loops, dict)

    def test_enhanced_loop_manager_integration(self):
        """Test that EnhancedLoopManager can work with patterns from both detectors"""
        base_patterns = self.base_detector.detect_patterns(self.test_events)
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        # Test with enhanced LoopManager
        enhanced_loop_manager = EnhancedLoopManager(self.tempo_map)
        
        if base_patterns:
            # Should work with base patterns
            base_loops = enhanced_loop_manager.detect_loops(self.test_events, base_patterns)
            self.assertIsInstance(base_loops, dict)
            
        if enhanced_result['patterns']:
            # Should work with enhanced patterns
            enhanced_loops = enhanced_loop_manager.detect_loops(self.test_events, enhanced_result['patterns'])
            self.assertIsInstance(enhanced_loops, dict)

    def test_empty_input_consistency(self):
        """Test that both detectors handle empty input consistently"""
        base_result = self.base_detector.detect_patterns([])
        enhanced_result = self.enhanced_detector.detect_patterns([])
        
        # Both should return empty but valid structures
        self.assertEqual(len(base_result), 0)
        self.assertIsInstance(enhanced_result, dict)
        self.assertEqual(len(enhanced_result.get('patterns', {})), 0)

    def test_insufficient_data_consistency(self):
        """Test that both detectors handle insufficient data consistently"""
        short_events = [
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
        ]
        
        base_result = self.base_detector.detect_patterns(short_events)
        enhanced_result = self.enhanced_detector.detect_patterns(short_events)
        
        # Both should return empty results for insufficient data
        self.assertEqual(len(base_result), 0)
        self.assertEqual(len(enhanced_result.get('patterns', {})), 0)

    def test_pattern_positions_format(self):
        """Test that pattern positions are in the correct format for both detectors"""
        base_patterns = self.base_detector.detect_patterns(self.test_events)
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        if base_patterns:
            base_pattern = list(base_patterns.values())[0]
            self.assertIn('positions', base_pattern)
            self.assertIsInstance(base_pattern['positions'], list)
            for pos in base_pattern['positions']:
                self.assertIsInstance(pos, int)
                
        if enhanced_result.get('patterns'):
            enhanced_pattern = list(enhanced_result['patterns'].values())[0]
            self.assertIn('positions', enhanced_pattern)
            self.assertIsInstance(enhanced_pattern['positions'], list)
            for pos in enhanced_pattern['positions']:
                self.assertIsInstance(pos, int)

    def test_pattern_events_format(self):
        """Test that pattern events are in the correct format for both detectors"""
        base_patterns = self.base_detector.detect_patterns(self.test_events)
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        if base_patterns:
            base_pattern = list(base_patterns.values())[0]
            self.assertIn('events', base_pattern)
            self.assertIsInstance(base_pattern['events'], list)
            for event in base_pattern['events']:
                self.assertIn('frame', event)
                self.assertIn('note', event)
                self.assertIn('volume', event)
                
        if enhanced_result.get('patterns'):
            enhanced_pattern = list(enhanced_result['patterns'].values())[0]
            self.assertIn('events', enhanced_pattern)
            self.assertIsInstance(enhanced_pattern['events'], list)
            for event in enhanced_pattern['events']:
                self.assertIn('frame', event)
                self.assertIn('note', event)
                self.assertIn('volume', event)

    def test_parser_integration(self):
        """Test that the parser can work with both pattern detectors through the enhanced system"""
        # This test verifies the real-world usage in parser.py
        
        # Create a simple test MIDI file content simulation
        test_track_events = {
            'track_0': self.test_events
        }
        
        # Verify that the enhanced detector used in parser returns the expected structure
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        # Check the structure that parser.py expects
        self.assertIsInstance(enhanced_result, dict)
        self.assertIn('patterns', enhanced_result)
        self.assertIn('references', enhanced_result)
        self.assertIn('stats', enhanced_result)
        
        # If patterns are found, verify they have the structure expected by LoopManager
        if enhanced_result['patterns']:
            pattern = list(enhanced_result['patterns'].values())[0]
            self.assertIn('positions', pattern)
            
            # Test that LoopManager can use these patterns
            loop_manager = EnhancedLoopManager(self.tempo_map)
            loops = loop_manager.detect_loops(self.test_events, enhanced_result['patterns'])
            self.assertIsInstance(loops, dict)

    def test_variation_compatibility(self):
        """Test that pattern variations are handled consistently"""
        # Create events with variations
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
        
        base_patterns = self.base_detector.detect_patterns(variation_events)
        enhanced_result = self.enhanced_detector.detect_patterns(variation_events)
        
        # Both should handle variations and include them in the pattern structure
        if base_patterns:
            pattern = list(base_patterns.values())[0]
            self.assertIn('variations', pattern)
            
        if enhanced_result.get('patterns'):
            pattern = list(enhanced_result['patterns'].values())[0]
            self.assertIn('variations', pattern)

    def test_tempo_map_integration(self):
        """Test that tempo information is properly integrated where expected"""
        # Add tempo changes
        self.tempo_map.add_tempo_change(240, 400000)  # 150 BPM at tick 240
        
        # Enhanced detector should handle tempo information
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        # Should return valid structure even with tempo changes
        self.assertIsInstance(enhanced_result, dict)
        self.assertIn('patterns', enhanced_result)

    def test_cross_detector_pattern_compatibility(self):
        """Test that patterns detected by one detector can be processed by components expecting the other"""
        base_patterns = self.base_detector.detect_patterns(self.test_events)
        enhanced_result = self.enhanced_detector.detect_patterns(self.test_events)
        
        if base_patterns and enhanced_result.get('patterns'):
            # Both should be usable by loop detection
            loop_manager = LoopManager(simple_mode=True)
            
            try:
                base_loops = loop_manager.detect_loops(self.test_events, base_patterns)
                enhanced_loops = loop_manager.detect_loops(self.test_events, enhanced_result['patterns'])
                
                # Both should succeed
                self.assertIsInstance(base_loops, dict)
                self.assertIsInstance(enhanced_loops, dict)
                
            except KeyError as e:
                self.fail(f"Cross-compatibility failed with KeyError: {e}")
            except Exception as e:
                self.fail(f"Cross-compatibility failed with unexpected error: {e}")


class TestPatternDetectorEdgeCases(unittest.TestCase):
    """Test edge cases that might cause integration issues"""
    
    def setUp(self):
        self.tempo_map = EnhancedTempoMap(initial_tempo=500000)
        self.base_detector = PatternDetector(min_pattern_length=2)
        self.enhanced_detector = EnhancedPatternDetector(self.tempo_map, min_pattern_length=2)

    def test_malformed_input_handling(self):
        """Test handling of malformed input data"""
        malformed_events = [
            {'frame': 0, 'note': 60},  # Missing volume
            {'frame': 1, 'volume': 100},  # Missing note
            {'note': 62, 'volume': 100},  # Missing frame
        ]
        
        # Both detectors should handle malformed input gracefully
        try:
            base_result = self.base_detector.detect_patterns(malformed_events)
            self.assertIsInstance(base_result, dict)
        except Exception as e:
            self.fail(f"Base detector failed with malformed input: {e}")
            
        try:
            enhanced_result = self.enhanced_detector.detect_patterns(malformed_events)
            self.assertIsInstance(enhanced_result, dict)
        except Exception as e:
            self.fail(f"Enhanced detector failed with malformed input: {e}")

    def test_extreme_values_handling(self):
        """Test handling of extreme values"""
        extreme_events = [
            {'frame': -1, 'note': 0, 'volume': 0},
            {'frame': 999999, 'note': 127, 'volume': 127},
            {'frame': 0, 'note': -1, 'volume': 128},
        ]
        
        # Both detectors should handle extreme values without crashing
        try:
            base_result = self.base_detector.detect_patterns(extreme_events)
            enhanced_result = self.enhanced_detector.detect_patterns(extreme_events)
            
            self.assertIsInstance(base_result, dict)
            self.assertIsInstance(enhanced_result, dict)
        except Exception as e:
            self.fail(f"Detectors failed with extreme values: {e}")

    def test_large_dataset_consistency(self):
        """Test consistency with large datasets"""
        # Create a large dataset with repeating patterns
        large_events = []
        pattern = [
            {'frame': 0, 'note': 60, 'volume': 100},
            {'frame': 1, 'note': 64, 'volume': 100},
            {'frame': 2, 'note': 67, 'volume': 100},
        ]
        
        # Repeat pattern 100 times
        for i in range(100):
            for event in pattern:
                large_events.append({
                    'frame': i * 3 + event['frame'],
                    'note': event['note'],
                    'volume': event['volume']
                })
        
        # Both detectors should handle large datasets
        base_result = self.base_detector.detect_patterns(large_events)
        enhanced_result = self.enhanced_detector.detect_patterns(large_events)
        
        self.assertIsInstance(base_result, dict)
        self.assertIsInstance(enhanced_result, dict)
        
        # Should detect the repeating pattern
        self.assertGreater(len(base_result), 0, "Base detector should find patterns in large dataset")
        self.assertGreater(len(enhanced_result.get('patterns', {})), 0, 
                         "Enhanced detector should find patterns in large dataset")


if __name__ == '__main__':
    unittest.main()
