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

    def _calculate_pattern_similarity(self, pattern1: List[Tuple], pattern2: List[Tuple]) -> float:
        """Calculate similarity between two patterns considering note and volume variations"""
        if len(pattern1) != len(pattern2):
            return 0.0
            
        # Check if this is a consistent transposition
        note_diffs = [n2 - n1 for (n1, _), (n2, _) in zip(pattern1, pattern2)]
        is_transposition = len(set(note_diffs)) == 1  # All intervals are the same
        
        # Check if this is a consistent volume change
        vol_diffs = [v2 - v1 for (_, v1), (_, v2) in zip(pattern1, pattern2)]
        is_volume_change = len(set(vol_diffs)) == 1  # All volume changes are the same
        
        # For transpositions, give high similarity regardless of interval
        if is_transposition and note_diffs[0] != 0:
            transposition_similarity = 0.9
        else:
            # Traditional similarity for notes
            note_similarity = 0.0
            for (note1, _), (note2, _) in zip(pattern1, pattern2):
                if note1 == note2:
                    note_similarity += 1.0
                elif abs(note1 - note2) == 1:  # Semitone difference
                    note_similarity += 0.8
                elif abs(note1 - note2) <= 3:  # Minor third or less
                    note_similarity += 0.6
            transposition_similarity = note_similarity / len(pattern1)
        
        # Volume similarity
        if is_volume_change and vol_diffs[0] != 0:
            volume_similarity = 0.9
        else:
            volume_similarity = 0.0
            for (_, vol1), (_, vol2) in zip(pattern1, pattern2):
                vol_sim = 1 - (abs(vol1 - vol2) / 127)  # Normalized difference
                volume_similarity += vol_sim
            volume_similarity = volume_similarity / len(pattern1)
        
        # Combine note and volume similarities
        return (transposition_similarity + volume_similarity) / 2

    def _detect_pattern_variations(self, sequence: List[Tuple], base_pattern: Tuple) -> List[Dict]:
        """Detect variations of a base pattern (transpositions, volume changes)"""
        variations = []
        pattern_len = len(base_pattern)
        
        for pos in range(len(sequence) - pattern_len + 1):
            current = tuple(sequence[pos:pos + pattern_len])
            
            # Skip exact matches (they're handled separately)
            if current == base_pattern:
                continue
                
            similarity = self._calculate_pattern_similarity(base_pattern, current)
            
            if similarity >= 0.85:  # Threshold for considering as variation (tightened)
                # Calculate transformation from base pattern
                transposition = sum(n2 - n1 for (n1, _), (n2, _) in zip(base_pattern, current)) / pattern_len
                vol_change = sum(v2 - v1 for (_, v1), (_, v2) in zip(base_pattern, current)) / pattern_len
                
                variations.append({
                    'position': pos,
                    'similarity': similarity,
                    'transposition': int(transposition),
                    'volume_change': int(vol_change)
                })
                
        return variations

    def detect_patterns(self, events: List[Dict]) -> Dict:
        """Enhanced pattern detection with variation support optimized for NES"""
        if not events:
            return {}

        sequence = [(e['note'], e['volume']) for e in events]
        
        # Function to score the benefit of a pattern for NES
        def score_pattern(length, exact_count, variation_count):
            total_count = exact_count + variation_count
            
            # Must have at least 3 total occurrences
            if total_count < 3:
                return -1
                
            # NES-optimized scoring:
            # Focus on compression efficiency and musical meaningfulness
            
            # Base score: compression benefit (bytes saved)
            compression_benefit = length * (total_count - 1)
            
            # Storage cost: pattern definition + reference table (reduced for NES)
            storage_cost = length + total_count  # 1 byte per reference (optimized for NES)
            
            # Net benefit
            net_benefit = compression_benefit - storage_cost
            
            # Bonuses and penalties:
            exact_bonus = exact_count * 0.3  # Slight bonus for exact matches
            
            # Length sweet spot: favor patterns of 3-8 notes (musical phrases)
            if 3 <= length <= 8:
                length_bonus = 2.0
            elif length <= 16:
                length_bonus = 1.0
            else:
                length_bonus = -1.0  # Penalize very long patterns
            
            # Frequency bonus: heavily favor patterns that repeat often
            if total_count >= 4:
                frequency_bonus = total_count * 0.5
            else:
                frequency_bonus = 0
            
            return net_benefit + exact_bonus + length_bonus + frequency_bonus

        # First pass: collect all possible patterns with their scores
        candidate_patterns = []
        
        for length in range(self.min_pattern_length, 
                          min(self.max_pattern_length, len(sequence)) + 1):
            for start in range(len(sequence) - length + 1):
                pattern = tuple(sequence[start:start + length])
                variations = self._detect_pattern_variations(sequence, pattern)
                exact_matches = self._find_pattern_matches(sequence, pattern, start)
                
                pattern_score = score_pattern(length, len(exact_matches), len(variations))
                
                if pattern_score > 0:
                    all_positions = exact_matches + [var['position'] for var in variations]
                    candidate_patterns.append({
                        'start': start,
                        'length': length,
                        'pattern': pattern,
                        'exact_matches': exact_matches,
                        'variations': variations,
                        'positions': sorted(set(all_positions)),
                        'score': pattern_score,
                        'events': [events[i] for i in range(start, start + length)]
                    })
        
        # Second pass: select non-overlapping patterns with highest scores
        candidate_patterns.sort(key=lambda x: x['score'], reverse=True)
        
        patterns = {}
        used_positions = set()
        
        for candidate in candidate_patterns:
            # Check if this pattern overlaps with already selected patterns
            pattern_positions = set()
            for pos in candidate['positions']:
                pattern_positions.update(range(pos, pos + candidate['length']))
            
            if not pattern_positions.intersection(used_positions):
                pattern_id = f"pattern_{len(patterns)}"
                patterns[pattern_id] = {
                    'events': candidate['events'],
                    'positions': candidate['positions'],
                    'exact_matches': candidate['exact_matches'],
                    'variations': candidate['variations'],
                    'length': candidate['length']
                }
                used_positions.update(pattern_positions)
        
        return patterns

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
        Optimize pattern selection considering variations and exact matches
        """
        if not patterns:
            return {}

        optimized = {}
        used_positions = set()
        
        # Score patterns based on exact matches and variations
        def pattern_score(pattern_info):
            exact_count = len(pattern_info['exact_matches'])
            variation_count = len(pattern_info['variations'])
            pattern_length = pattern_info['length']
            return (exact_count + variation_count * 0.8) * pattern_length
        
        # Sort patterns by score
        sorted_patterns = sorted(
            patterns.items(),
            key=lambda x: pattern_score(x[1]),
            reverse=True
        )
        
        for pattern_id, pattern_info in sorted_patterns:
            # Check positions from both exact matches and variations
            positions = set()
            for pos in pattern_info['exact_matches']:
                positions.update(range(pos, pos + pattern_info['length']))
            for var in pattern_info['variations']:
                positions.update(range(var['position'], 
                                     var['position'] + pattern_info['length']))
            
            if not positions.intersection(used_positions):
                optimized[pattern_id] = pattern_info
                used_positions.update(positions)
        
        return optimized


class EnhancedPatternDetector(PatternDetector):
    def __init__(self, tempo_map: EnhancedTempoMap, 
                 min_pattern_length=3, max_pattern_length=32):
        super().__init__(min_pattern_length, max_pattern_length)
        self.tempo_map = tempo_map
        self.compressor = PatternCompressor()
        
    def detect_patterns(self, events: List[Dict]) -> Dict:
        # Detect patterns with variations using parent class
        patterns = super().detect_patterns(events)
        
        # Enhance patterns with tempo information
        for pattern_id, pattern_info in patterns.items():
            self._analyze_pattern_tempo(pattern_id, pattern_info, events)
            
            # Add variation-specific tempo analysis
            if 'variations' in pattern_info:
                self._analyze_variation_tempos(pattern_id, pattern_info, events)
        
        # Compress patterns
        compressed_patterns, pattern_refs = self.compressor.compress_patterns(patterns)
        
        # Add compression information to the result
        compression_stats = self.compressor.calculate_compression_stats(
            patterns, compressed_patterns
        )
        
        return {
            'patterns': compressed_patterns,
            'references': pattern_refs,
            'stats': compression_stats,
            'variations': self._get_variation_summary(patterns)
        }
    
    def _analyze_pattern_tempo(self, pattern_id: str, 
                             pattern_info: Dict, events: List[Dict]):
        """Analyze tempo characteristics of a pattern"""
        positions = pattern_info['exact_matches']
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

    def _analyze_variation_tempos(self, pattern_id: str, 
                                pattern_info: Dict, events: List[Dict]):
        """Analyze tempo characteristics of pattern variations"""
        if 'variations' not in pattern_info:
            return
            
        for var in pattern_info['variations']:
            pos = var['position']
            length = pattern_info['length']
            
            # Get tempo characteristics for this variation
            var_tempos = [
                self.tempo_map.get_tempo_at_tick(tick)
                for tick in range(pos, pos + length)
            ]
            
            var['tempo_info'] = {
                'average_tempo': int(sum(var_tempos) / len(var_tempos)),
                'tempo_range': (min(var_tempos), max(var_tempos))
            }

    def _get_variation_summary(self, patterns: Dict) -> Dict:
        """Generate summary of pattern variations"""
        summary = {}
        for pattern_id, pattern_info in patterns.items():
            if 'variations' in pattern_info:
                summary[pattern_id] = {
                    'variation_count': len(pattern_info['variations']),
                    'transposition_range': self._get_transposition_range(pattern_info['variations']),
                    'volume_range': self._get_volume_range(pattern_info['variations'])
                }
        return summary

    def _get_transposition_range(self, variations: List[Dict]) -> Tuple[int, int]:
        """Calculate the range of transpositions in variations"""
        if not variations:
            return (0, 0)
        transpositions = [var['transposition'] for var in variations]
        return (min(transpositions), max(transpositions))

    def _get_volume_range(self, variations: List[Dict]) -> Tuple[int, int]:
        """Calculate the range of volume changes in variations"""
        if not variations:
            return (0, 0)
        volume_changes = [var['volume_change'] for var in variations]
        return (min(volume_changes), max(volume_changes))


class PatternCompressor:
    def __init__(self):
        self.compressed_patterns = {}
        self.pattern_references = defaultdict(list)
        
    def compress_patterns(self, patterns: Dict) -> Tuple[Dict, Dict]:
        """
        Compress patterns by identifying identical patterns and creating references.
        """
        compressed_data = {}
        pattern_refs = defaultdict(list)
        pattern_hash_map = {}
        
        # First pass: hash patterns and identify duplicates
        for pattern_id, pattern_info in patterns.items():
            pattern_hash = self._hash_pattern(pattern_info['events'])
            
            if pattern_hash in pattern_hash_map:
                # Pattern already exists, add reference
                original_id = pattern_hash_map[pattern_hash]
                pattern_refs[original_id].extend(pattern_info['positions'])
            else:
                # New unique pattern
                pattern_hash_map[pattern_hash] = pattern_id
                compressed_data[pattern_id] = pattern_info.copy()
                pattern_refs[pattern_id].extend(pattern_info['positions'])
        
        # Sort positions for each pattern
        for pattern_id in pattern_refs:
            pattern_refs[pattern_id] = sorted(set(pattern_refs[pattern_id]))
            
            # Update the positions in the compressed data
            if pattern_id in compressed_data:
                compressed_data[pattern_id]['positions'] = pattern_refs[pattern_id]
        
        return compressed_data, dict(pattern_refs)
    
    def _hash_pattern(self, events: List[Dict]) -> str:
        """Create a unique hash for a pattern based on its events"""
        return hash(tuple((e['note'], e['volume']) for e in events))
    
    def calculate_compression_stats(self, original: Dict, compressed: Dict) -> Dict:
        """Calculate compression statistics"""
        original_size = sum(
            len(p['events']) * len(p['positions']) 
            for p in original.values()
        )
        compressed_size = sum(
            len(p['events']) for p in compressed.values()
        )
        
        compression_ratio = 0
        if original_size > 0:
            compression_ratio = ((original_size - compressed_size) / original_size) * 100
            
        return {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': compression_ratio,
            'unique_patterns': len(compressed)
        }
