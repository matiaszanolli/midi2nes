import unittest
from tracker.loop_manager import LoopManager, EnhancedLoopManager
from tracker.tempo_map import EnhancedTempoMap

class TestLoopManager(unittest.TestCase):
    def setUp(self):
        self.loop_manager = LoopManager()
        self.tempo_map = EnhancedTempoMap()
        self.enhanced_loop_manager = EnhancedLoopManager(self.tempo_map)

    def test_basic_loop_detection(self):
        # Test case with simple repeating pattern
        pattern_info = {
            'pattern1': {
                'positions': [0, 16, 32, 48],  # Regular pattern every 16 ticks
                'length': 16
            }
        }
        events = []  # Mock events, not needed for this test

        loops = self.loop_manager.detect_loops(events, pattern_info)
        
        # Should detect multiple possible loops
        self.assertGreater(len(loops), 0)
        # Check if at least one loop spans the full sequence
        full_sequence_loop = any(
            loop['start'] == 0 and loop['end'] == 64 
            for loop in loops.values()
        )
        self.assertTrue(full_sequence_loop)

    def test_loop_quality_calculation(self):
        # Test different loop scenarios and their quality scores
        quality1 = self.loop_manager._calculate_loop_quality(
            start=0,
            end=16,  # Perfect 16-beat loop
            pattern_length=16,
            repetitions=4
        )
        quality2 = self.loop_manager._calculate_loop_quality(
            start=0,
            end=7,  # Odd-length loop
            pattern_length=7,
            repetitions=2
        )
        
        # 16-beat loop should have higher quality
        self.assertGreater(quality1, quality2)
        # Quality should be between 0 and 1
        self.assertLessEqual(quality1, 1.0)
        self.assertGreater(quality1, 0.0)

    def test_overlapping_loops(self):
        pattern_info = {
            'pattern1': {
                'positions': [0, 16, 32],
                'length': 16
            },
            'pattern2': {
                'positions': [8, 24, 40],  # Overlaps with pattern1
                'length': 16
            }
        }
        events = []

        loops = self.loop_manager.detect_loops(events, pattern_info)
        optimized = self.loop_manager._optimize_loops(loops)
        
        # Check that overlapping loops are properly handled
        for loop1_id, loop1_info in optimized.items():
            for loop2_id, loop2_info in optimized.items():
                if loop1_id != loop2_id:
                    # Check significant overlap
                    overlap = min(loop1_info['end'], loop2_info['end']) - \
                            max(loop1_info['start'], loop2_info['start'])
                    overlap_ratio = overlap / min(
                        loop1_info['length'], 
                        loop2_info['length']
                    )
                    self.assertLessEqual(overlap_ratio, 0.5)

    def test_jump_table_generation(self):
        loops = {
            'loop1': {
                'start': 0,
                'end': 16,
                'length': 16,
                'repetitions': 4
            },
            'loop2': {
                'start': 16,
                'end': 24,
                'length': 8,
                'repetitions': 2
            }
        }

        jump_table = self.loop_manager.generate_jump_table(loops)
        
        # Check jump table structure
        self.assertIn(16, jump_table)  # End point of first loop
        self.assertIn(24, jump_table)  # End point of second loop
        
        # Check optimization hints
        self.assertEqual(
            jump_table[16]['optimization_hint'], 
            'subroutine'  # 16-length should be subroutine
        )
        self.assertEqual(
            jump_table[24]['optimization_hint'], 
            'inline'  # 8-length should be inline
        )

    def test_enhanced_loop_manager(self):
        # Convert 120 BPM to microseconds per quarter note (60000000 / BPM)
        tempo_us = int(60000000 / 120)
        self.tempo_map.add_tempo_change(16, tempo_us)

        # `events` must be a real, index-addressable list matching the
        # positions in pattern_info: detect_loops now reads each loop
        # boundary's tempo straight off the event at that index (#345/
        # TEMPO-16), so an empty/mismatched events list would IndexError.
        events = [{'frame': i, 'note': 60, 'volume': 100, 'tempo': 500000}
                  for i in range(48)]
        loops = self.enhanced_loop_manager.detect_loops(events, {
            'pattern1': {
                'positions': [0, 16, 32],
                'length': 16
            }
        })

    def test_multi_tempo_loop_boundary_reads_the_events_own_tempo(self):
        """Regression (#345/TEMPO-16): loop_info['start']/['end'] are indices
        into `events` (positions in the note-on sequence), not MIDI ticks.
        The old code fed them straight into get_tempo_at_tick, which for a
        multi-tempo song reads the wrong point in the tempo timeline (an
        event-index of, say, 20 has nothing to do with tick 20). Each event
        already carries the tempo that was really active at ITS tick, so the
        loop's recorded tempo_state must match that, not a tick-20 lookup."""
        tempo_map = EnhancedTempoMap(initial_tempo=500000)
        # A tempo change far past any event-index value this test uses, so a
        # wrong "index treated as tick" lookup would never see it.
        tempo_map.add_tempo_change(100_000, 300000)
        loop_manager = EnhancedLoopManager(tempo_map)

        # Event at index 20 really occurred (per its own 'tempo' field, as
        # parser_fast.py/parser.py stamp on every event) after the tempo
        # change -- its real tick is >= 100_000, just not encoded by its
        # small list index.
        events = [{'frame': i, 'note': 60, 'volume': 100, 'tempo': 500000}
                  for i in range(20)]
        events.append({'frame': 20, 'note': 60, 'volume': 100, 'tempo': 300000})
        events += [{'frame': i, 'note': 60, 'volume': 100, 'tempo': 300000}
                   for i in range(21, 40)]

        loops = loop_manager.detect_loops(events, {
            'pattern1': {'positions': [0, 20], 'length': 4}
        })

        self.assertTrue(loops, "fixture should yield at least one loop")
        tempo_key = next(iter(loop_manager.tempo_map.loop_points))
        loop_tempo_state = loop_manager.tempo_map.loop_points[tempo_key]
        # The wrong tick-20 lookup would report the initial tempo (500000,
        # since the real tempo change is at tick 100_000). The fix must
        # report the event's own real tempo instead.
        self.assertEqual(loop_tempo_state['end']['tempo'], 300000)
        self.assertNotEqual(loop_tempo_state['end']['tempo'],
                            tempo_map.get_tempo_at_tick(loop_tempo_state['end']['tick']))

    def test_invalid_loop_handling(self):
        # Test with invalid loop points
        loops = {
            'invalid_loop': {
                'start': 10,
                'end': 5,  # End before start
                'length': 5,
                'repetitions': 1
            }
        }
        
        jump_table = self.loop_manager.generate_jump_table(loops)
        self.assertEqual(len(jump_table), 0)  # Should ignore invalid loop

if __name__ == '__main__':
    unittest.main()
