# tracker/fast_pattern_detector.py
from collections import defaultdict, Counter
from typing import List, Dict, Tuple
from tracker.tempo_map import EnhancedTempoMap
from tracker.pattern_detector import PatternCompressor
import hashlib

class FastPatternDetector:
    """
    Optimized pattern detector with O(n²) complexity instead of O(n⁴).
    
    Key optimizations:
    1. Hash-based pattern matching instead of similarity calculations
    2. Sliding window approach with early termination
    3. Limited pattern length ranges (4-16 instead of 3-32)
    4. Skip variation detection for large sequences
    5. Batch processing of similar patterns
    """
    
    def __init__(self, min_pattern_length=4, max_pattern_length=16):
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = min(max_pattern_length, 16)  # Cap at 16 for performance
        
    def detect_patterns(self, events: List[Dict]) -> Dict:
        """Fast pattern detection with reduced complexity"""
        if not events or len(events) < self.min_pattern_length:
            return {}
            
        # Input validation and cleaning (reuse from original)
        valid_events = self._clean_events(events)
        if len(valid_events) < self.min_pattern_length:
            return {}
            
        sequence = [(e['note'], e['volume']) for e in valid_events]
        
        # Apply performance limits
        MAX_EVENTS = 2000  # Reduced from 1000 for better balance
        if len(sequence) > MAX_EVENTS:
            print(f"Warning: Large sequence ({len(sequence)} events), limiting to {MAX_EVENTS}")
            sequence = sequence[:MAX_EVENTS]
            valid_events = valid_events[:MAX_EVENTS]
            
        # Fast hash-based pattern detection
        patterns = self._detect_patterns_fast(sequence, valid_events)
        
        return patterns
    
    def _clean_events(self, events: List[Dict]) -> List[Dict]:
        """Clean and validate input events (same as original)"""
        valid_events = []
        for i, e in enumerate(events):
            if not isinstance(e, dict) or 'note' not in e or 'volume' not in e:
                continue
                
            try:
                note = int(e['note'])
                volume = int(e['volume'])
                if note < 0 or note > 127 or volume < 0 or volume > 127:
                    continue
                valid_events.append({
                    'frame': e.get('frame', i),
                    'note': note,
                    'volume': volume
                })
            except (ValueError, TypeError):
                continue
                
        return valid_events
    
    def _detect_patterns_fast(self, sequence: List[Tuple], events: List[Dict]) -> Dict:
        """Fast hash-based pattern detection - O(n²) complexity"""
        pattern_hashes = defaultdict(list)  # hash -> list of (start_pos, length)
        pattern_candidates = {}  # hash -> pattern info
        
        # First pass: hash all possible patterns
        for length in range(self.min_pattern_length, min(self.max_pattern_length + 1, len(sequence) + 1)):
            for start in range(len(sequence) - length + 1):
                pattern_tuple = tuple(sequence[start:start + length])
                pattern_hash = self._hash_pattern(pattern_tuple)
                
                pattern_hashes[pattern_hash].append((start, length))
                
                # Store pattern info on first occurrence
                if pattern_hash not in pattern_candidates:
                    pattern_candidates[pattern_hash] = {
                        'pattern': pattern_tuple,
                        'length': length,
                        'events': [events[i] for i in range(start, start + length)]
                    }
        
        # Second pass: filter patterns that occur multiple times
        patterns = {}
        used_positions = set()
        
        # Sort by frequency and length (prefer longer, more frequent patterns)
        sorted_hashes = sorted(
            pattern_hashes.keys(),
            key=lambda h: (len(pattern_hashes[h]), pattern_candidates[h]['length']),
            reverse=True
        )
        
        for pattern_hash in sorted_hashes:
            positions = pattern_hashes[pattern_hash]
            
            # Must occur at least 3 times to be considered
            if len(positions) < 3:
                continue
                
            candidate = pattern_candidates[pattern_hash]
            length = candidate['length']
            
            # Check for overlap with already selected patterns
            pattern_positions = set()
            for start_pos, _ in positions:
                pattern_positions.update(range(start_pos, start_pos + length))
            
            # Skip if significant overlap with existing patterns
            if len(pattern_positions.intersection(used_positions)) > length * 0.3:
                continue
            
            # Accept this pattern
            start_positions = [pos for pos, _ in positions]
            pattern_id = f"pattern_{len(patterns)}"
            
            patterns[pattern_id] = {
                'events': candidate['events'],
                'positions': sorted(start_positions),
                'exact_matches': sorted(start_positions),
                'variations': [],  # Skip variation detection for performance
                'length': length
            }
            
            used_positions.update(pattern_positions)
            
            # Stop when we have enough patterns
            if len(patterns) >= 10:  # Limit number of patterns
                break
                
        return patterns
    
    def _hash_pattern(self, pattern_tuple: Tuple) -> str:
        """Create a hash for a pattern tuple"""
        return hash(pattern_tuple)


class FastEnhancedPatternDetector(FastPatternDetector):
    """Fast version of EnhancedPatternDetector"""
    
    def __init__(self, tempo_map: EnhancedTempoMap, min_pattern_length=4, max_pattern_length=16):
        super().__init__(min_pattern_length, max_pattern_length)
        self.tempo_map = tempo_map
        self.compressor = PatternCompressor()
        
    def detect_patterns(self, events: List[Dict]) -> Dict:
        """Fast enhanced pattern detection"""
        if not events:
            return {
                'patterns': {},
                'references': {},
                'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0, 'unique_patterns': 0},
                'variations': {}
            }
        
        # Use fast base detection
        patterns = super().detect_patterns(events)
        
        # Skip tempo analysis for performance (can be added back if needed)
        
        # Compress patterns (this is fast)
        compressed_patterns, pattern_refs = self.compressor.compress_patterns(patterns)
        
        # Calculate compression stats
        compression_stats = self.compressor.calculate_compression_stats(patterns, compressed_patterns)
        
        return {
            'patterns': compressed_patterns,
            'references': pattern_refs,
            'stats': compression_stats,
            'variations': {}  # Skip variation summary for performance
        }


class MinimalPatternDetector:
    """
    Minimal pattern detector that only finds exact repeats.
    Extremely fast for large files - O(n log n) complexity.
    """
    
    def __init__(self, min_pattern_length=4, max_pattern_length=8):
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = min(max_pattern_length, 8)
        
    def detect_patterns(self, events: List[Dict]) -> Dict:
        """Minimal pattern detection - only exact repeats"""
        if not events or len(events) < self.min_pattern_length * 2:
            return {}
            
        # Simple validation
        valid_events = []
        for i, e in enumerate(events):
            if isinstance(e, dict) and 'note' in e and 'volume' in e:
                try:
                    valid_events.append({
                        'frame': e.get('frame', i),
                        'note': int(e['note']),
                        'volume': int(e['volume'])
                    })
                except (ValueError, TypeError):
                    continue
                    
        if len(valid_events) < self.min_pattern_length * 2:
            return {}
            
        sequence = [(e['note'], e['volume']) for e in valid_events]
        
        # Find only the most obvious repeating patterns
        pattern_counts = Counter()
        
        # Use a sliding window to find repeating subsequences
        for length in range(self.min_pattern_length, min(self.max_pattern_length + 1, len(sequence) // 2 + 1)):
            for start in range(len(sequence) - length + 1):
                pattern = tuple(sequence[start:start + length])
                pattern_counts[pattern] += 1
        
        # Keep only patterns that repeat at least 4 times
        patterns = {}
        for pattern_tuple, count in pattern_counts.items():
            if count >= 4:
                length = len(pattern_tuple)
                
                # Find all positions of this pattern
                positions = []
                for i in range(len(sequence) - length + 1):
                    if tuple(sequence[i:i + length]) == pattern_tuple:
                        positions.append(i)
                
                if len(positions) >= 3:  # Final check
                    pattern_id = f"pattern_{len(patterns)}"
                    start_pos = positions[0]
                    
                    patterns[pattern_id] = {
                        'events': [valid_events[i] for i in range(start_pos, start_pos + length)],
                        'positions': positions,
                        'exact_matches': positions,
                        'variations': [],
                        'length': length
                    }
                    
                    if len(patterns) >= 5:  # Limit patterns for performance
                        break
                        
        return patterns


# Factory function to choose the right detector based on input size
def get_optimal_pattern_detector(tempo_map: EnhancedTempoMap, event_count: int, 
                                fast_mode: bool = False) -> 'PatternDetector':
    """
    Choose the optimal pattern detector based on event count and performance requirements.
    
    Args:
        tempo_map: Enhanced tempo map
        event_count: Number of events to process
        fast_mode: If True, prioritize speed over accuracy
        
    Returns:
        Appropriate pattern detector instance
    """
    if fast_mode or event_count > 5000:
        return MinimalPatternDetector(min_pattern_length=4, max_pattern_length=8)
    elif event_count > 2000:
        return FastEnhancedPatternDetector(tempo_map, min_pattern_length=4, max_pattern_length=12)
    elif event_count > 500:
        return FastEnhancedPatternDetector(tempo_map, min_pattern_length=4, max_pattern_length=16)
    else:
        # Use original EnhancedPatternDetector for small files
        from tracker.pattern_detector import EnhancedPatternDetector
        return EnhancedPatternDetector(tempo_map, min_pattern_length=3, max_pattern_length=16)
