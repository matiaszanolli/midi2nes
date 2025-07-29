import unittest

from tracker.tempo_map import (TempoValidationConfig, EnhancedTempoMap, TempoOptimizationStrategy,
                               TempoChangeType)
from tracker.loop_manager import EnhancedLoopManager
from tracker.pattern_detector import EnhancedPatternDetector
from constants import FRAME_RATE_HZ

class TestEnhancedLoopManager(unittest.TestCase):
    def setUp(self):
        # Create tempo map with validation config
        config = TempoValidationConfig(
            min_tempo_bpm=40.0,
            max_tempo_bpm=250.0,
            min_duration_frames=2,
            max_duration_frames=FRAME_RATE_HZ * 30  # 30 seconds
        )
        self.tempo_map = EnhancedTempoMap(
            initial_tempo=500000,  # 120 BPM
            validation_config=config,
            optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
        )
        
        # Create enhanced loop manager with tempo map
        self.loop_manager = EnhancedLoopManager(self.tempo_map)
        
        # Create pattern detector
        self.pattern_detector = EnhancedPatternDetector(
            min_pattern_length=3,
            tempo_map=self.tempo_map
        )
        
        # Test data with patterns and tempo changes
        self.note_events = [
            # First pattern at 120 BPM
            {'frame': 0, 'note': 60, 'volume': 100, 'tick': 0},
            {'frame': 1, 'note': 64, 'volume': 100, 'tick': 240},
            {'frame': 2, 'note': 67, 'volume': 100, 'tick': 480},
            
            # Pattern repeats at new tempo
            {'frame': 4, 'note': 60, 'volume': 100, 'tick': 960},
            {'frame': 5, 'note': 64, 'volume': 100, 'tick': 1200},
            {'frame': 6, 'note': 67, 'volume': 100, 'tick': 1440},
            
            # Pattern repeats again
            {'frame': 7, 'note': 60, 'volume': 100, 'tick': 1680},
            {'frame': 8, 'note': 64, 'volume': 100, 'tick': 1920},
            {'frame': 9, 'note': 67, 'volume': 100, 'tick': 2160}
        ]
        
        # Tempo changes are handled separately
        self.tempo_changes = [
            {'frame': 3, 'type': 'tempo', 'value': 400000, 'tick': 720}
        ]
        
        # Add tempo changes to tempo map
        for change in self.tempo_changes:
            try:
                self.tempo_map.add_tempo_change(
                    change['tick'],
                    change['value'],
                    TempoChangeType.IMMEDIATE,
                    0
                )
            except ValueError as e:
                print(f"Warning: {e}")

    def test_tempo_aware_loop_detection(self):
        """Test that loops are detected with tempo changes"""
        # First detect patterns (using only note events)
        pattern_result = self.pattern_detector.detect_patterns(self.note_events)
        
        # Convert pattern format to what loop manager expects
        pattern_info = {}
        for pattern_id, pattern in pattern_result['patterns'].items():
            pattern_info[pattern_id] = {
                'positions': pattern_result['references'][pattern_id],
                'length': len(pattern['events'])
            }
        
        # Then detect loops
        loops = self.loop_manager.detect_loops(self.note_events, pattern_info)
        self.assertTrue(len(loops) > 0, "No loops detected")
        
        # Verify loop structure
        first_loop = list(loops.values())[0]
        self.assertIn('start', first_loop)
        self.assertIn('end', first_loop)
        self.assertIn('length', first_loop)
        
        # Verify tempo is registered for the loop (check any loop ID in tempo map)
        self.assertTrue(len(self.tempo_map.loop_points) > 0, "No loop points registered")
        
        # Get tempo info for any loop
        first_tempo_state = list(self.tempo_map.loop_points.values())[0]
        self.assertIsNotNone(first_tempo_state)
        self.assertIn('start', first_tempo_state)
        self.assertIn('end', first_tempo_state)

    def test_enhanced_jump_table(self):
        """Test that jump table includes tempo information"""
        # First detect patterns (using only note events)
        pattern_result = self.pattern_detector.detect_patterns(self.note_events)
        
        # Convert pattern format
        pattern_info = {}
        for pattern_id, pattern in pattern_result['patterns'].items():
            pattern_info[pattern_id] = {
                'positions': pattern_result['references'][pattern_id],
                'length': len(pattern['events'])
            }
        
        # Then detect loops
        loops = self.loop_manager.detect_loops(self.note_events, pattern_info)
        
        # Generate jump table
        jump_table = self.loop_manager.generate_jump_table(loops)
        
        # Verify jump table structure
        self.assertTrue(len(jump_table) > 0, "Jump table is empty")
        
        # Check first entry
        first_entry = list(jump_table.values())[0]
        self.assertIn('start_pos', first_entry)
        self.assertIn('tempo_state', first_entry)
        
        # Verify tempo state is present and has correct format
        tempo_state = first_entry['tempo_state']
        self.assertIsNotNone(tempo_state)
        self.assertIn('start', tempo_state)
        self.assertIn('end', tempo_state)
        
        # Verify tempo info structure
        self.assertIn('tick', tempo_state['start'])
        self.assertIn('tempo', tempo_state['start'])
        self.assertIn('tick', tempo_state['end'])
        self.assertIn('tempo', tempo_state['end'])

    def test_loop_with_multiple_tempo_changes(self):
        """Test handling of loops with multiple tempo changes"""
        # Create events with multiple tempo changes
        note_events = [
            # First pattern at 120 BPM
            {'frame': 0, 'note': 60, 'volume': 100, 'tick': 0},
            {'frame': 1, 'note': 64, 'volume': 100, 'tick': 240},
            {'frame': 2, 'note': 67, 'volume': 100, 'tick': 480},
            
            # Pattern at 150 BPM
            {'frame': 4, 'note': 60, 'volume': 100, 'tick': 960},
            {'frame': 5, 'note': 64, 'volume': 100, 'tick': 1200},
            {'frame': 6, 'note': 67, 'volume': 100, 'tick': 1440},
            
            # Pattern at 100 BPM (using valid BPM within range)
            {'frame': 8, 'note': 60, 'volume': 100, 'tick': 1920},
            {'frame': 9, 'note': 64, 'volume': 100, 'tick': 2160},
            {'frame': 10, 'note': 67, 'volume': 100, 'tick': 2400}
        ]
        
        # Add tempo changes to tempo map (use valid BPM values)
        tempo_changes = [
            {'frame': 3, 'type': 'tempo', 'value': 400000, 'tick': 720},  # 150 BPM
            {'frame': 7, 'type': 'tempo', 'value': 500000, 'tick': 1680}  # 120 BPM (within range)
        ]
        
        for change in tempo_changes:
            try:
                self.tempo_map.add_tempo_change(
                    change['tick'],
                    change['value'],
                    TempoChangeType.IMMEDIATE,
                    0
                )
            except ValueError as e:
                print(f"Warning: {e}")
        
        # Detect patterns
        pattern_result = self.pattern_detector.detect_patterns(note_events)
        
        # Convert pattern format
        pattern_info = {}
        for pattern_id, pattern in pattern_result['patterns'].items():
            pattern_info[pattern_id] = {
                'positions': pattern_result['references'][pattern_id],
                'length': len(pattern['events'])
            }
        
        # Detect loops
        loops = self.loop_manager.detect_loops(note_events, pattern_info)
        
        # Generate jump table
        jump_table = self.loop_manager.generate_jump_table(loops)
        
        # Verify tempo changes are tracked
        for entry in jump_table.values():
            tempo_state = entry['tempo_state']
            self.assertIsNotNone(tempo_state)
            
            # Check actual format returned by tempo map
            self.assertIn('start', tempo_state)
            self.assertIn('end', tempo_state)
            
            # Verify tempo info structure
            start_info = tempo_state['start']
            end_info = tempo_state['end']
            
            self.assertIn('tick', start_info)
            self.assertIn('tempo', start_info)
            self.assertIn('tick', end_info)
            self.assertIn('tempo', end_info)
            
            # Verify tempo values are reasonable
            self.assertGreater(start_info['tempo'], 0)
            self.assertGreater(end_info['tempo'], 0)

    def test_invalid_loop_points(self):
        """Test handling of invalid loop points"""
        # Create events with invalid loop points
        note_events = [
            {'frame': 0, 'note': 60, 'volume': 100, 'tick': 0},
            {'frame': 1, 'note': 64, 'volume': 100, 'tick': 240},
            {'frame': 2, 'note': 67, 'volume': 100, 'tick': 480}
        ]
        
        # Add invalid loop points
        loop_events = [
            {'frame': 3, 'type': 'loop_end', 'tick': 720},
            {'frame': 4, 'type': 'loop_start', 'tick': 960}
        ]
        
        # Should not raise exception but should ignore invalid loop
        patterns = self.pattern_detector.detect_patterns(note_events)
        loops = self.loop_manager.detect_loops(note_events + loop_events, patterns['patterns'])
        
        # No loops should be detected
        self.assertEqual(len(loops), 0, "Invalid loop should be ignored")

    def test_nested_loops(self):
        """Test handling of nested loops"""
        note_events = [
            # First occurrence of pattern A (60-64-67)
            {'frame': 0, 'note': 60, 'volume': 100, 'tick': 0},
            {'frame': 1, 'note': 64, 'volume': 100, 'tick': 240},
            {'frame': 2, 'note': 67, 'volume': 100, 'tick': 480},
            
            # First occurrence of pattern B (72-76-79)
            {'frame': 3, 'note': 72, 'volume': 100, 'tick': 720},
            {'frame': 4, 'note': 76, 'volume': 100, 'tick': 960},
            {'frame': 5, 'note': 79, 'volume': 100, 'tick': 1200},
            
            # Second occurrence of pattern A
            {'frame': 6, 'note': 60, 'volume': 100, 'tick': 1440},
            {'frame': 7, 'note': 64, 'volume': 100, 'tick': 1680},
            {'frame': 8, 'note': 67, 'volume': 100, 'tick': 1920},
            
            # Second occurrence of pattern B
            {'frame': 9, 'note': 72, 'volume': 100, 'tick': 2160},
            {'frame': 10, 'note': 76, 'volume': 100, 'tick': 2400},
            {'frame': 11, 'note': 79, 'volume': 100, 'tick': 2640},
            
            # Third occurrence of pattern A
            {'frame': 12, 'note': 60, 'volume': 100, 'tick': 2880},
            {'frame': 13, 'note': 64, 'volume': 100, 'tick': 3120},
            {'frame': 14, 'note': 67, 'volume': 100, 'tick': 3360},
        ]
        
        # Detect patterns
        pattern_result = self.pattern_detector.detect_patterns(note_events)
        
        # Convert pattern format
        pattern_info = {}
        for pattern_id, pattern in pattern_result['patterns'].items():
            pattern_info[pattern_id] = {
                'positions': pattern_result['references'][pattern_id],
                'length': len(pattern['events'])
            }
        
        # Detect loops
        loops = self.loop_manager.detect_loops(note_events, pattern_info)
        
        # Should optimize and choose the most efficient loop structure
        self.assertTrue(len(loops) > 0, "Should detect at least one loop")
        
        # Verify no overlapping loops
        used_frames = set()
        for loop_info in loops.values():
            loop_range = set(range(loop_info['start'], loop_info['end']))
            self.assertFalse(loop_range.intersection(used_frames), 
                            "Loops should not overlap")
            used_frames.update(loop_range)
