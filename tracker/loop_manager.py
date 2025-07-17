from typing import List, Dict, Optional

class LoopManager:
    def __init__(self):
        self.loops = {}
        self.jump_table = {}

    def detect_loops(self, events: List[Dict], pattern_info: Dict) -> Dict:
        """
        Detect potential loop points based on patterns and musical structure.
        Returns loop points and jump table information.
        """
        loops = {}
        
        # Find potential loop points from patterns
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

    def _optimize_loops(self, loops: Dict) -> Dict:
        """
        Optimize loop selection by:
        1. Removing nested loops
        2. Ensuring proper loop boundaries
        3. Maximizing loop length while minimizing memory usage
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
            jump_table[loop_info['end']] = loop_info['start']
        
        return jump_table
