# tracker/pattern_detector.py
from collections import defaultdict
from typing import List, Dict, Tuple
import numpy as np
from tqdm import tqdm
from tracker.tempo_map import TempoChangeType, TempoChange, EnhancedTempoMap

# There are exactly TWO event caps, one per detector complexity class — they do
# NOT shadow each other; each binds a different algorithm (#102). Both decimate
# via the single `sample_events_for_detection` (uniform, lossy — see
# docs/legacy/PATTERN_DETECTION_IMPROVEMENTS.md); the old third limit (the
# ThreadedPatternDetector 2000-stride) was removed with that dead class.
#
# MAX_PATTERN_EVENTS: the O(n) parallel `ParallelPatternDetector` (hash grouping,
# #114) handles far more events, so the default full pipeline samples to this.
MAX_PATTERN_EVENTS = 15000

# DETECTOR_MAX_EVENTS: the sequential `PatternDetector` is O(n^2)-ish, so it caps
# its working set far lower. The `detect-patterns` subcommand and the pipeline's
# sequential fallback both run this detector, so they sample to THIS number, not
# MAX_PATTERN_EVENTS. Applied by *uniform* sampling (not a head cut) so the whole
# song is covered (#100); callers report THIS as the retained count.
DETECTOR_MAX_EVENTS = 1000


def sample_events_for_detection(events, max_events=MAX_PATTERN_EVENTS):
    """Uniformly down-sample ``events`` to at most ``max_events`` entries.

    Sampling is spread across the whole sequence (``np.linspace``) so the
    musical structure is preserved rather than head-truncated. This is a lossy
    step; callers should surface a warning when it triggers.

    Returns ``(sampled_events, was_sampled)``.
    """
    if len(events) <= max_events:
        return events, False
    indices = np.linspace(0, len(events) - 1, max_events, dtype=int)
    return [events[i] for i in indices], True


def score_pattern(length, exact_count, variation_count):
    """NES-optimized benefit score for a candidate pattern (#103).

    Shared by BOTH detectors so the sequential and parallel paths rank
    exact-repeat candidates identically. ``variation_count`` is the number of
    transposed/volume-scaled repeats: the sequential ``EnhancedPatternDetector``
    supplies it, while the parallel ``ParallelPatternDetector`` (O(n) hash
    grouping, exact repeats only) always passes 0 — the two paths therefore share
    scoring but the parallel path never scores variations (see
    ``pattern_detector_parallel._collect_length_candidates``).
    """
    total_count = exact_count + variation_count

    # Must have at least 3 total occurrences
    if total_count < 3:
        return -1

    # Base score: compression benefit (bytes saved)
    compression_benefit = length * (total_count - 1)
    # Storage cost: pattern definition + reference table (1 byte per reference)
    storage_cost = length + total_count
    net_benefit = compression_benefit - storage_cost

    # Slight bonus for exact matches
    exact_bonus = exact_count * 0.3

    # Length bonus: strongly favor longer patterns (exponential for 6+).
    if length >= 6:
        length_bonus = length * 3.0
    elif length >= 4:
        length_bonus = length * 2.0
    elif length == 3:
        length_bonus = 1.5
    else:
        length_bonus = 0.5

    # Frequency bonus: heavily favor patterns that repeat often.
    frequency_bonus = total_count * 0.5 if total_count >= 4 else 0

    return net_benefit + exact_bonus + length_bonus + frequency_bonus

class PatternDetector:
    def __init__(self, min_pattern_length=3, max_pattern_length=32,
                 max_events=DETECTOR_MAX_EVENTS):
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = max_pattern_length
        # Overridable event-sampling cap (#219) — defaults to the module
        # constant so behavior is unchanged unless a caller (e.g. a loaded
        # config file) supplies a different value.
        self.max_events = max_events
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

        # Validate and clean input events
        valid_events = []
        for i, e in enumerate(events):
            # Check if event has required keys
            if not isinstance(e, dict):
                continue
            if 'note' not in e or 'volume' not in e:
                continue
            
            # Validate data types and ranges
            try:
                note = int(e['note'])
                volume = int(e['volume'])
                # Allow negative frames, but ensure note and volume are reasonable
                if note < 0 or note > 127 or volume < 0 or volume > 127:
                    continue
                valid_events.append({
                    'frame': e.get('frame', i),  # Use index if frame missing
                    'note': note,
                    'volume': volume
                })
            except (ValueError, TypeError):
                continue
        
        # Return empty if no valid events
        if not valid_events:
            return {}

        # Safeguard: this detector is O(n^2)-ish, so cap the working set. Sample
        # UNIFORMLY (not head-truncate) so the whole song's structure is covered
        # rather than dropping the entire tail (#100). `self.max_events`
        # defaults to DETECTOR_MAX_EVENTS but is overridable per-instance (#219).
        if len(valid_events) > self.max_events:
            print(f"Warning: Large sequence ({len(valid_events)} events), "
                  f"uniformly sampling to {self.max_events} for performance")
            valid_events, _ = sample_events_for_detection(valid_events, self.max_events)

        sequence = [(e['note'], e['volume']) for e in valid_events]
        events = valid_events  # Use cleaned events for the rest of the method

        # Scoring is the module-level score_pattern (shared with the parallel
        # detector so both rank exact-repeat candidates identically, #103).

        # First pass: collect all possible patterns with their scores
        candidate_patterns = []
        
        # Calculate total iterations for progress tracking
        total_iterations = sum(
            len(sequence) - length + 1 
            for length in range(self.min_pattern_length, 
                              min(self.max_pattern_length, len(sequence)) + 1)
        )
        
        if total_iterations > 1000:  # Only show progress bar for large tasks
            with tqdm(total=total_iterations, desc="Finding patterns", unit="pos") as pbar:
                for length in range(self.min_pattern_length, 
                                  min(self.max_pattern_length, len(sequence)) + 1):
                    for start in range(len(sequence) - length + 1):
                        pattern = tuple(sequence[start:start + length])
                        variations = self._detect_pattern_variations(sequence, pattern)
                        exact_matches = self._find_pattern_matches(sequence, pattern, start)
                        
                        pattern_score = score_pattern(length, len(exact_matches), len(variations))
                        
                        if pattern_score > 0:
                            # `positions` is exact-only (#168/PAT-01): a variation
                            # position's actual content differs from `events`
                            # (the anchor's events), so merging it in here made
                            # `references` claim the pattern reproduces content it
                            # doesn't. `occupied_positions` (exact + variations)
                            # still blocks a *different* candidate from claiming
                            # the same frames during the non-overlap selection below.
                            occupied_positions = exact_matches + [var['position'] for var in variations]
                            candidate_patterns.append({
                                'start': start,
                                'length': length,
                                'pattern': pattern,
                                'exact_matches': exact_matches,
                                'variations': variations,
                                'positions': sorted(set(exact_matches)),
                                'occupied_positions': sorted(set(occupied_positions)),
                                'score': pattern_score,
                                'events': [events[i] for i in range(start, start + length)]
                            })

                        pbar.update(1)
                        pbar.set_postfix(candidates=len(candidate_patterns))
        else:
            # No progress bar for small tasks
            for length in range(self.min_pattern_length, 
                              min(self.max_pattern_length, len(sequence)) + 1):
                for start in range(len(sequence) - length + 1):
                    pattern = tuple(sequence[start:start + length])
                    variations = self._detect_pattern_variations(sequence, pattern)
                    exact_matches = self._find_pattern_matches(sequence, pattern, start)
                    
                    pattern_score = score_pattern(length, len(exact_matches), len(variations))
                    
                    if pattern_score > 0:
                        # See the tqdm branch above for why `positions` is
                        # exact-only and `occupied_positions` keeps both (#168/PAT-01).
                        occupied_positions = exact_matches + [var['position'] for var in variations]
                        candidate_patterns.append({
                            'start': start,
                            'length': length,
                            'pattern': pattern,
                            'exact_matches': exact_matches,
                            'variations': variations,
                            'positions': sorted(set(exact_matches)),
                            'occupied_positions': sorted(set(occupied_positions)),
                            'score': pattern_score,
                            'events': [events[i] for i in range(start, start + length)]
                        })
        
        # Second pass: select non-overlapping patterns with highest scores
        candidate_patterns.sort(key=lambda x: x['score'], reverse=True)
        
        patterns = {}
        used_positions = set()
        
        for candidate in candidate_patterns:
            # Check if this pattern overlaps with already selected patterns.
            # Uses occupied_positions (exact + variations, #168/PAT-01) so a
            # variation window still blocks a different candidate from
            # claiming the same frames, even though it's excluded from the
            # persisted `positions`/`references` (which must stay exact-only).
            pattern_positions = set()
            for pos in candidate['occupied_positions']:
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

        # Start searching after the anchor window itself, not one element into
        # it -- starting at start_pos + 1 let the first "match" overlap the
        # anchor in self-similar runs (period < pattern_len), inflating the
        # occurrence count vs. the parallel detector's next_free greedy
        # (#170/PAT-04).
        pos = start_pos + pattern_len
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
                 min_pattern_length=3, max_pattern_length=32,
                 max_events=DETECTOR_MAX_EVENTS, analyze_tempo=True):
        super().__init__(min_pattern_length, max_pattern_length, max_events)
        self.tempo_map = tempo_map
        self.compressor = PatternCompressor()
        # Callers that pass a default-constructed EnhancedTempoMap purely to
        # satisfy this constructor's required argument (it holds no real
        # tempo-change data, so get_tempo_at_tick() below would just report a
        # single flat value for every "tick" — which here is a pattern
        # position, not a real MIDI tick anyway) can skip the analysis pass
        # entirely rather than pay for a discarded/meaningless result (#119).
        self.analyze_tempo = analyze_tempo

    def detect_patterns(self, events: List[Dict]) -> Dict:
        # Return empty structure if no events
        if not events:
            return {
                'patterns': {},
                'references': {},
                'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0,
                          'unique_patterns': 0, 'total_events': 0, 'patterned_events': 0,
                          'coverage_ratio': 0},
                'variations': {}
            }

        # Total events this detection run actually covers (#169/PAT-03) --
        # captured before super().detect_patterns() does its own internal
        # validation/sampling, so this reflects what was handed to the
        # detector, not a narrower post-filter count.
        total_events = len(events)

        # Detect patterns with variations using parent class
        patterns = super().detect_patterns(events)

        # Enhance patterns with tempo information (#119: skippable when the
        # caller's tempo map carries no real data and the result is unused).
        if self.analyze_tempo:
            for pattern_id, pattern_info in patterns.items():
                self._analyze_pattern_tempo(pattern_id, pattern_info, events)

                # Add variation-specific tempo analysis
                if 'variations' in pattern_info:
                    self._analyze_variation_tempos(pattern_id, pattern_info, events)
        
        # Compress patterns
        compressed_patterns, pattern_refs = self.compressor.compress_patterns(patterns)
        
        # Add compression information to the result
        compression_stats = self.compressor.calculate_compression_stats(
            patterns, compressed_patterns, total_events
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
        """Generate summary of pattern variations.

        Both detectors emit this SAME per-pattern shape (#172) so a consumer can
        read either path's `variations` uniformly:
        `{variation_count, exact_match_count, transposition_range, volume_range}`.
        The parallel detector finds exact repeats only, so on that path
        variation_count is 0 and the ranges are neutral (0, 0); here all four
        carry real data."""
        summary = {}
        for pattern_id, pattern_info in patterns.items():
            variations = pattern_info.get('variations', [])
            summary[pattern_id] = {
                'variation_count': len(variations),
                'exact_match_count': len(pattern_info.get('exact_matches', [])),
                'transposition_range': self._get_transposition_range(variations),
                'volume_range': self._get_volume_range(variations),
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
    
    def _hash_pattern(self, events: List[Dict]) -> Tuple[Tuple[int, int], ...]:
        """Return a pattern's exact identity key: the tuple of its (note, volume)
        events.

        This is used as the dedup key in compress_patterns. It returns the tuple
        itself, not hash() of it: hash() is a lossy 64-bit int, and a collision
        between two different event tuples would silently merge the second
        pattern's references into the first (and drop its definition), since the
        map has no equality check on a hit. The tuple is already hashable, so
        keying on it directly is exact and collision-free (#173)."""
        return tuple((e['note'], e['volume']) for e in events)
    
    def calculate_compression_stats(self, original: Dict, compressed: Dict,
                                     total_events: int = 0) -> Dict:
        """Calculate compression statistics.

        NOTE: ``compression_ratio`` is a percentage *reduction* in [0, 100]
        (``(original - compressed) / original * 100``), not a multiplier. Callers
        must print it with a ``%`` label, never an ``x`` suffix — a 96% reduction
        is not "96x" (#17). It measures dedup within the *patterned subset only*
        (how much smaller the unique templates are vs. storing every occurrence)
        -- it is NOT a measure of the whole song, and has no relationship to
        emitted ROM bytes (#4).

        ``total_events`` (the event count pattern detection actually ran over,
        i.e. after any upstream sampling) is optional for backward
        compatibility, but callers should always pass it (#169/PAT-03):
        without it, ``coverage_ratio`` reads 0 even though most of a song is
        typically un-patterned, which is the exact "96% reduction on an
        un-patterned song" confusion this field exists to prevent.
        """
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

        # patterned_events is the exact-only event count covered by a detected
        # pattern occurrence (== original_size now that positions is exact-only,
        # #168/PAT-01) -- named separately here so a consumer doesn't have to
        # know that equivalence to read "how much of the song is patterned".
        patterned_events = original_size
        coverage_ratio = 0
        if total_events > 0:
            coverage_ratio = (patterned_events / total_events) * 100

        return {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': compression_ratio,
            'unique_patterns': len(compressed),
            'total_events': total_events,
            'patterned_events': patterned_events,
            'coverage_ratio': coverage_ratio
        }
