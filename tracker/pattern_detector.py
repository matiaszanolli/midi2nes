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
        
        # Add safeguard: limit processing to reasonable size
        MAX_EVENTS = 1000  # Limit to prevent excessive processing time
        if len(sequence) > MAX_EVENTS:
            print(f"Warning: Large sequence ({len(sequence)} events), limiting to {MAX_EVENTS} for performance")
            sequence = sequence[:MAX_EVENTS]
            events = events[:MAX_EVENTS]
        
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
            
            # Length bonus: strongly favor longer patterns for better compression
            # Exponential bonus for longer patterns
            if length >= 6:
                length_bonus = length * 3.0  # Strong bonus for 6+ note patterns
            elif length >= 4:
                length_bonus = length * 2.0  # Good bonus for 4-5 note patterns
            elif length == 3:
                length_bonus = 1.5  # Basic bonus for minimum patterns
            else:
                length_bonus = 0.5  # Small bonus for 2-note patterns
            
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
        
        # The tests expect just the patterns dict, not wrapped in a structure
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


class DrumPatternDetector(PatternDetector):
    def __init__(self, min_pattern_length=2, max_pattern_length=16):
        super().__init__(min_pattern_length, max_pattern_length)
        self.drum_patterns = {
            'basic_beat': [(36, 100), (42, 80), (36, 100), (42, 80)],  # Basic kick-hihat
            'basic_rock': [(36, 100), (42, 80), (38, 100), (42, 80)],  # Basic rock beat
            'fill_pattern': [(38, 100), (38, 100), (38, 100), (38, 120)]  # Basic fill
        }
        self.detected_patterns = {}  # Store detected patterns for access by tests
        
    def _calculate_drum_similarity(self, pattern1: List[Tuple], pattern2: List[Tuple]) -> float:
        """
        Specialized similarity calculation for drum patterns considering:
        - Exact note matches (same drum instrument)
        - Velocity variations (dynamics)
        - Timing relationships (relative positions)
        """
        if len(pattern1) != len(pattern2):
            return 0.0
            
        similarity_score = 0.0
        timing_weight = 0.4
        velocity_weight = 0.3
        instrument_weight = 0.3
        
        for i, ((note1, vel1), (note2, vel2)) in enumerate(zip(pattern1, pattern2)):
            # Instrument match (exact drum type)
            if note1 == note2:
                similarity_score += instrument_weight
            # Similar drum type (e.g., high tom vs mid tom)
            elif abs(note1 - note2) <= 2 and note1 in range(41, 49):  # Toms range
                similarity_score += instrument_weight * 0.5
                
            # Velocity similarity
            vel_similarity = 1.0 - (abs(vel1 - vel2) / 127.0)
            similarity_score += vel_similarity * velocity_weight
            
            # Timing pattern similarity (position in the pattern)
            position_similarity = 1.0 if i % 2 == 0 else 0.8  # Emphasize strong beats
            similarity_score += position_similarity * timing_weight
            
        return similarity_score / len(pattern1)
        
    def detect_drum_patterns(self, events: List[Dict]) -> Dict:
        """
        Enhanced pattern detection specifically for drum tracks
        """
        if not events:
            return {}
            
        sequence = [(e['note'], e.get('volume', e.get('velocity', 100))) for e in events]
        patterns = {}
        
        def score_drum_pattern(length: int, matches: List[int], 
                             variations: List[Dict]) -> float:
            """
            Score drum patterns based on:
            - Pattern length (favor common drum pattern lengths: 2, 4, 8, 16)
            - Number of repetitions
            - Consistency of variations
            """
            total_occurrences = len(matches) + len(variations)
            
            # Base score from pattern length
            if length in [4, 8]:  # Common drum pattern lengths
                length_score = 2.0
            elif length in [2, 16]:  # Less common but valid
                length_score = 1.5
            else:
                length_score = 1.0
                
            # Repetition score
            repetition_score = total_occurrences * 0.5
            
            # Variation consistency score
            if variations:
                variation_similarities = [v['similarity'] for v in variations]
                consistency_score = sum(variation_similarities) / len(variations)
            else:
                consistency_score = 1.0
                
            return (length_score + repetition_score) * consistency_score
            
        # Detect common drum patterns first
        for name, template in self.drum_patterns.items():
            for pos in range(len(sequence) - len(template) + 1):
                current = sequence[pos:pos + len(template)]
                similarity = self._calculate_drum_similarity(template, current)
                
                if similarity > 0.85:
                    if name not in patterns:
                        patterns[name] = {
                            'template': template,
                            'matches': [pos],
                            'variations': []
                        }
                    else:
                        patterns[name]['matches'].append(pos)
                elif similarity > 0.7:
                    if name not in patterns:
                        patterns[name] = {
                            'template': template,
                            'matches': [],
                            'variations': []
                        }
                    patterns[name]['variations'].append({
                        'position': pos,
                        'similarity': similarity,
                        'pattern': current
                    })
                    
        # Detect emergent patterns
        for length in range(self.min_pattern_length, 
                          min(self.max_pattern_length, len(sequence)) + 1):
            for start in range(len(sequence) - length + 1):
                pattern = sequence[start:start + length]
                
                # Skip if this segment is already part of a known pattern
                if any(start in p['matches'] for p in patterns.values()):
                    continue
                    
                matches = []
                variations = []
                
                # Look for similar patterns
                for pos in range(start + 1, len(sequence) - length + 1):
                    current = sequence[pos:pos + length]
                    similarity = self._calculate_drum_similarity(pattern, current)
                    
                    if similarity > 0.85:
                        matches.append(pos)
                    elif similarity > 0.7:
                        variations.append({
                            'position': pos,
                            'similarity': similarity,
                            'pattern': current
                        })
                
                if matches or variations:
                    pattern_score = score_drum_pattern(length, matches, variations)
                    if pattern_score > 1.5:  # Threshold for accepting new patterns
                        pattern_id = f"emergent_pattern_{len(patterns)}"
                        patterns[pattern_id] = {
                            'template': pattern,
                            'matches': [start] + matches,
                            'variations': variations,
                            'score': pattern_score
                        }
        
        # Post-process patterns
        optimized_patterns = self._optimize_drum_patterns(patterns, events)
        
        # Store detected patterns for access by tests
        self.detected_patterns = optimized_patterns
        
        return optimized_patterns
        
    def _optimize_drum_patterns(self, patterns: Dict, events: List[Dict]) -> Dict:
        """
        Optimize detected drum patterns by:
        1. Removing overlapping patterns, keeping the highest scoring ones
        2. Merging similar patterns
        3. Adding musical context (strong/weak beats, fills, etc.)
        """
        optimized = {}
        used_positions = set()
        
        # Sort patterns by score
        sorted_patterns = sorted(
            patterns.items(),
            key=lambda x: len(x[1]['matches']) + len(x[1]['variations']),
            reverse=True
        )
        
        for pattern_id, pattern_info in sorted_patterns:
            # Check for position overlap
            pattern_positions = set()
            for pos in pattern_info['matches']:
                pattern_positions.update(
                    range(pos, pos + len(pattern_info['template']))
                )
            
            # Add variations positions
            for var in pattern_info['variations']:
                pattern_positions.update(
                    range(var['position'], 
                          var['position'] + len(pattern_info['template']))
                )
            
            # If no significant overlap, add to optimized patterns
            if len(pattern_positions.intersection(used_positions)) < \
               len(pattern_positions) * 0.3:
                optimized[pattern_id] = pattern_info
                used_positions.update(pattern_positions)
                
                # Add musical context
                pattern_info['musical_context'] = self._analyze_musical_context(
                    pattern_info, events
                )
        
        return optimized
        
    def _analyze_musical_context(self, pattern_info: Dict, 
                               events: List[Dict]) -> Dict:
        """
        Analyze the musical context of a drum pattern
        """
        context = {
            'is_fill': False,
            'intensity': 0,
            'common_variations': [],
            'typical_position': 'any'
        }
        
        template = pattern_info['template']
        
        # Check if it's a fill (increasing density or velocity)
        velocities = [v for _, v in template]
        if (len(set(n for n, _ in template)) >= 3 and  # Multiple drum types
            sum(velocities[len(velocities)//2:]) > 
            sum(velocities[:len(velocities)//2])):  # Increasing intensity
            context['is_fill'] = True
            
        # Calculate intensity
        context['intensity'] = sum(v for _, v in template) / len(template)
        
        # Analyze common variations
        if pattern_info['variations']:
            variation_types = defaultdict(int)
            for var in pattern_info['variations']:
                var_pattern = var['pattern']
                if all(v2 > v1 for (_, v1), (_, v2) in 
                      zip(template, var_pattern)):
                    variation_types['crescendo'] += 1
                elif all(n1 == n2 for (n1, _), (n2, _) in 
                        zip(template, var_pattern)):
                    variation_types['velocity_only'] += 1
                    
            context['common_variations'] = [
                k for k, v in variation_types.items() 
                if v >= len(pattern_info['variations']) * 0.3
            ]
            
        # Determine typical position
        positions = pattern_info['matches']
        if positions:
            avg_pos = sum(positions) / len(positions)
            if avg_pos < len(events) * 0.3:
                context['typical_position'] = 'early'
            elif avg_pos > len(events) * 0.7:
                context['typical_position'] = 'late'
            else:
                context['typical_position'] = 'middle'
                
        return context


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
