# tracker/pattern_detector.py
from collections import defaultdict
from typing import List, Dict, Tuple
from tracker.tempo_map import TempoChangeType, TempoChange, EnhancedTempoMap

class PatternDetector:
    def __init__(self, min_pattern_length=3, max_pattern_length=32):
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = max_pattern_length
        self.patterns = {}
        self.pattern_instances = defaultdict(list)

    def detect_patterns(self, events: List[Dict]) -> Dict:
        """
        Detect repeating patterns in a sequence of note events.
        Returns a dictionary of patterns and their positions.
        """
        if not events:
            return {}

        patterns = {}
        # Convert events to tuples for easier comparison, but only use note and volume
        sequence = [(e['note'], e['volume']) for e in events]  # Removed frame from comparison
        
        # Try different pattern lengths
        for length in range(self.min_pattern_length, 
                          min(self.max_pattern_length, len(sequence)) + 1):
            for start in range(len(sequence) - length + 1):
                pattern = tuple(sequence[start:start + length])
                
                # Look for this pattern in the rest of the sequence
                matches = self._find_pattern_matches(sequence, pattern, start)
                if len(matches) >= 3:  # Pattern must appear at least 3 times
                    pattern_id = f"pattern_{len(patterns)}"
                    patterns[pattern_id] = {
                        'events': [events[i] for i in range(start, start + length)],
                        'positions': matches,
                        'length': length
                    }

        return self._optimize_patterns(patterns)

    def _find_pattern_matches(self, sequence: List, pattern: Tuple, start_pos: int) -> List[int]:
        """Find all occurrences of a pattern in the sequence."""
        matches = [start_pos]  # Include the initial position
        pattern_len = len(pattern)
        
        # Start searching after the pattern
        pos = start_pos + 1
        while pos <= len(sequence) - pattern_len:
            current = tuple(sequence[pos:pos + pattern_len])
            if current == pattern:
                matches.append(pos)
                pos += pattern_len  # Skip the length of the pattern to avoid overlaps
            else:
                pos += 1
        
        return matches

    def _optimize_patterns(self, patterns: Dict) -> Dict:
        """
        Optimize pattern selection by:
        1. Removing overlapping patterns
        2. Preferring longer patterns
        3. Preferring patterns with more repetitions
        """
        if not patterns:
            return {}

        optimized = {}
        used_positions = set()
        
        # Sort patterns by score (length * repetitions)
        sorted_patterns = sorted(
            patterns.items(),
            key=lambda x: (len(x[1]['positions']) * x[1]['length']),
            reverse=True
        )
        
        for pattern_id, pattern_info in sorted_patterns:
            # Check if this pattern overlaps with already selected patterns
            positions = set(
                pos 
                for start in pattern_info['positions']
                for pos in range(start, start + pattern_info['length'])
            )
            
            if not positions.intersection(used_positions):
                optimized[pattern_id] = pattern_info
                used_positions.update(positions)
        
        return optimized

class EnhancedPatternDetector(PatternDetector):
    def __init__(self, tempo_map: EnhancedTempoMap, 
                 min_pattern_length=3, max_pattern_length=32):
        super().__init__(min_pattern_length, max_pattern_length)
        self.tempo_map = tempo_map
        
    def detect_patterns(self, events: List[Dict]) -> Dict:
        patterns = super().detect_patterns(events)
        
        # Enhance patterns with tempo information
        for pattern_id, pattern_info in patterns.items():
            self._analyze_pattern_tempo(pattern_id, pattern_info, events)
            
        return patterns
    
    def _analyze_pattern_tempo(self, pattern_id: str, 
                             pattern_info: Dict, events: List[Dict]):
        """Analyze tempo characteristics of a pattern"""
        positions = pattern_info['positions']
        length = pattern_info['length']
        
        # Calculate average tempo for the pattern
        pattern_tempos = []
        for pos in positions:
            segment_tempos = [
                self.tempo_map.get_tempo_at_tick(tick)
                for tick in range(pos, pos + length)
            ]
            pattern_tempos.append(sum(segment_tempos) / len(segment_tempos))
            
        base_tempo = int(sum(pattern_tempos) / len(pattern_tempos))
        
        # Detect tempo variations within the pattern
        variations = []
        for pos in positions:
            current_tempos = [
                self.tempo_map.get_tempo_at_tick(tick)
                for tick in range(pos, pos + length)
            ]
            if max(current_tempos) - min(current_tempos) > 1000:  # Significant variation
                variations.append(
                    TempoChange(
                        pos, max(current_tempos),
                        TempoChangeType.PATTERN_SYNC,
                        length
                    )
                )
        
        # Register pattern tempo information
        self.tempo_map.add_pattern_tempo(pattern_id, base_tempo, variations)
