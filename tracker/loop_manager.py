from typing import List, Dict
from tracker.tempo_map import EnhancedTempoMap

class LoopManager:
    def __init__(self, simple_mode=False):
        """Initialize LoopManager."""
        self.simple_mode = simple_mode
        self.loops = {}
        self.jump_table = {}

    def detect_loops(self, events: List[Dict], pattern_info: Dict) -> Dict:
        """
        Detect potential loop points based on patterns and musical structure.
        Returns loop points and jump table information.
        """
        loops = {}
        
        # First check for full sequence loops
        total_length = 0
        for pattern_id, info in pattern_info.items():
            positions = info['positions']
            if len(positions) > 1:
                pattern_end = positions[-1] + info['length']
                total_length = max(total_length, pattern_end)
                
                if positions[0] == 0:
                    loops['full_sequence'] = {
                        'start': 0,
                        'end': pattern_end,
                        'length': pattern_end,
                        'repetitions': len(positions)
                    }
        
        # Then check for other potential loops
        for pattern_id, info in pattern_info.items():
            positions = info['positions']
            if len(positions) > 1:
                # Consider the last occurrence as loop end
                loop_end = positions[-1] + info['length']
                # Consider the second-to-last occurrence as loop start
                loop_start = positions[-2]
                
                loops[f"loop_{pattern_id}"] = {
                    'start': loop_start,
                    'end': loop_end,
                    'length': info['length'],
                    'repetitions': len(positions)
                }
        
        return self._optimize_loops(loops)

    def _calculate_loop_quality(self, start: int, end: int, 
                            pattern_length: int, repetitions: int) -> float:
        """Calculate quality score for a potential loop."""
        # Base score from pattern repetitions
        base_score = min(1.0, repetitions / 4.0)  # Normalize, max at 4 repetitions
        
        # Favor loops that align with musical phrases
        loop_length = end - start
        musical_alignment = 1.0
        if loop_length % 16 == 0:  # Full phrase
            musical_alignment = 1.2
        elif loop_length % 8 == 0:  # Half phrase
            musical_alignment = 1.1
        elif loop_length % 4 == 0:  # Bar
            musical_alignment = 1.05
        
        # Ensure final score is capped at 1.0
        return min(1.0, base_score * musical_alignment)

    def _optimize_loops(self, loops: Dict) -> Dict:
        """
        Optimize loop selection by removing nested loops and ensuring proper boundaries.
        """
        optimized = {}
        
        # Sort loops by length * repetitions (descending)
        sorted_loops = sorted(
            loops.items(),
            key=lambda x: (x[1]['length'] * x[1]['repetitions']),
            reverse=True
        )
        
        used_ranges = set()
        for loop_id, loop_info in sorted_loops:
            loop_range = set(range(loop_info['start'], loop_info['end']))
            if not loop_range.intersection(used_ranges):
                optimized[loop_id] = loop_info
                used_ranges.update(loop_range)
        
        return optimized

    def generate_jump_table(self, loops: Dict) -> Dict:
        """Generate optimized jump table for the detected loops."""
        jump_table = {}
        
        for loop_id, loop_info in loops.items():
            if loop_info['end'] <= loop_info['start']:
                continue
                
            if self.simple_mode:
                # Simple mode for pattern detection tests
                jump_table[loop_info['end']] = loop_info['start']
            else:
                # Default mode with optimization hints
                jump_table[loop_info['end']] = {
                    'start_pos': loop_info['start'],
                    'length': loop_info['end'] - loop_info['start'],
                    'optimization_hint': 'inline' if (loop_info['end'] - loop_info['start']) < 16 else 'subroutine'
                }
            
        return jump_table


class EnhancedLoopManager(LoopManager):
    def __init__(self, tempo_map: 'EnhancedTempoMap'):
        """Initialize EnhancedLoopManager with tempo map."""
        super().__init__(simple_mode=False)  # Always use enhanced mode
        self.tempo_map = tempo_map
        
    def detect_loops(self, events: List[Dict], pattern_info: Dict) -> Dict:
        """Detect potential loop points based on patterns."""
        loops = super().detect_loops(events, pattern_info)

        # Register tempo information for each loop
        for loop_id, loop_info in loops.items():
            # loop_info['start']/['end'] are indices into `events` (positions
            # in the note-on sequence pattern detection ran over), not MIDI
            # ticks -- get_tempo_at_tick previously received them directly, a
            # unit mismatch harmless for a single-tempo song (one constant
            # tempo regardless of argument) but silently wrong for a
            # multi-tempo one (#345/TEMPO-16). Each event already carries the
            # real tempo active at its own tick (stamped during parsing), so
            # read it directly instead of a second, wrongly-unit'd lookup.
            # `end` is an EXCLUSIVE index (one past the loop's last event), so
            # its tempo comes from the last included event, not `events[end]`
            # (out of range when the loop reaches the end of the sequence).
            start_tempo = events[loop_info['start']]['tempo']
            end_tempo = events[loop_info['end'] - 1]['tempo']

            tempo_key = f"loop_{loop_info['end']}_{loop_info['start']}"
            self.tempo_map.loop_points[tempo_key] = {
                'start': {
                    'tempo': start_tempo,
                    'tick': loop_info['start']
                },
                'end': {
                    'tempo': end_tempo,
                    'tick': loop_info['end']
                }
            }
            
        return loops

    def generate_jump_table(self, loops: Dict) -> Dict:
        """Generate enhanced jump table with tempo information."""
        jump_table = {}
        
        for loop_id, loop_info in loops.items():
            if loop_info['end'] <= loop_info['start']:
                continue
                
            jump_table[loop_info['end']] = {
                'start_pos': loop_info['start'],
                'length': loop_info['end'] - loop_info['start'],
                'optimization_hint': 'inline' if (loop_info['end'] - loop_info['start']) < 16 else 'subroutine',
                'tempo_state': self.tempo_map.loop_points.get(f"loop_{loop_info['end']}_{loop_info['start']}")
            }
            
        return jump_table

    def _evaluate_loop_quality(self, start: int, end: int, length: int, repetitions: int) -> float:
        """
        Evaluate the quality of a potential loop based on multiple factors.
        Returns a score between 0 and 1.
        """
        # Base score from repetitions and length
        base_score = (repetitions * length) / (end - start)
        
        # Adjust based on musical metrics (bars/phrases)
        musical_alignment = (length % 16) == 0  # aligned to common bar lengths
        
        return base_score * (1.2 if musical_alignment else 1.0)
