import multiprocessing as mp
import time
from typing import List, Dict, Tuple, Any, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from tracker.tempo_map import EnhancedTempoMap
from tracker.pattern_detector import (
    PatternCompressor, sample_events_for_detection, score_pattern, MAX_PATTERN_EVENTS
)

class ParallelPatternDetector:
    """
    High-performance pattern detector using multiprocessing to utilize all CPU cores.
    Designed for large MIDI files with thousands of events.
    """
    
    def __init__(self, tempo_map: EnhancedTempoMap, min_pattern_length=3, max_pattern_length=32,
                 max_pattern_events=MAX_PATTERN_EVENTS):
        self.tempo_map = tempo_map
        self.min_pattern_length = min_pattern_length
        self.max_pattern_length = max_pattern_length
        # Overridable sampling cap (#219) — defaults to the module constant so
        # behavior is unchanged unless a caller (e.g. a loaded config file)
        # supplies a different value.
        self.max_pattern_events = max_pattern_events
        self.compressor = PatternCompressor()

        # Get optimal number of workers
        self.max_workers = max(1, mp.cpu_count() - 1)  # Leave one core for OS
        
    def detect_patterns(self, events: List[Dict]) -> Dict:
        """
        Detect patterns using parallel processing across multiple CPU cores.
        """
        if not events:
            return {
                'patterns': {},
                'references': {},
                'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0, 'unique_patterns': 0},
                'variations': {}
            }
        
        print(f"🚀 Starting parallel pattern detection with up to {self.max_workers} workers")
        start_time = time.time()
        
        # Clean and validate events
        valid_events = self._filter_valid_events(events)
        if not valid_events:
            return self._empty_result()
        
        # Handle large sequences using the shared large-file policy (#21) so the
        # default path and the `detect-patterns` subcommand sample identically.
        original_count = len(valid_events)
        valid_events, was_sampled = sample_events_for_detection(valid_events, self.max_pattern_events)
        if was_sampled:
            print(f"⚠️  Large sequence ({original_count} events), sampling to "
                  f"{len(valid_events)} ({len(valid_events)/original_count*100:.1f}%, lossy)")
            print(f"   ✅ Sampled {len(valid_events)} events preserving temporal distribution")

        # Convert to sequence for processing
        sequence = [(e['note'], e['volume']) for e in valid_events]

        # Split work into chunks for parallel processing
        patterns = self._detect_patterns_parallel(sequence, valid_events)
        
        # Compress patterns
        compressed_patterns, pattern_refs = self.compressor.compress_patterns(patterns)
        
        # Calculate compression statistics
        compression_stats = self.compressor.calculate_compression_stats(
            patterns, compressed_patterns
        )
        
        end_time = time.time()
        print(f"✅ Parallel pattern detection completed in {end_time - start_time:.2f}s")
        
        return {
            'patterns': compressed_patterns,
            'references': pattern_refs,
            'stats': compression_stats,
            'variations': self._get_variation_summary(patterns)
        }
    
    def _filter_valid_events(self, events: List[Dict]) -> List[Dict]:
        """Filter and validate events for pattern detection"""
        return [
            event for event in events
            if isinstance(event.get('note'), (int, float)) and
               isinstance(event.get('volume'), (int, float)) and
               0 <= event.get('note', 0) <= 127 and
               0 <= event.get('volume', 0) <= 127
        ]
    
    def _detect_patterns_parallel(self, sequence: List[Tuple], valid_events: List[Dict]) -> Dict:
        """Detect patterns using parallel processing.

        Each worker handles ONE pattern length over the whole sequence using the
        O(n) hash-grouping pass in `_collect_length_candidates`, so total work is
        O(n·L) instead of the old per-start O(n²·L) rescan. The sequence and
        events are shipped to each worker process ONCE via the pool `initializer`
        rather than embedded in every chunk dict — the previous code pickled the
        full sequence ~(lengths × workers) times per detection run (#114)."""

        # One chunk per pattern length; the heavy data travels via initargs below.
        work_chunks = [
            {'pattern_length': length}
            for length in range(self.min_pattern_length,
                                min(self.max_pattern_length, len(sequence)) + 1)
        ]
        if not work_chunks:
            return {}

        # A single work chunk gains nothing from a process pool but still pays
        # full spawn/teardown overhead — on the `spawn` start method (macOS/
        # Windows) that overhead can run to 100ms+ per process, dwarfing the
        # sub-100ms serial-path cost for the trivial input that produces one
        # chunk. Skip pool construction entirely in that case (#218).
        if len(work_chunks) == 1:
            print("🔄 Only one work chunk; skipping process pool")
            return self._detect_patterns_serial(sequence, valid_events)

        print(f"🔧 Created {len(work_chunks)} work chunks for parallel processing")

        # Never spawn more worker processes than there are chunks to hand out —
        # cpu_count()-1 is an upper bound on usable parallelism, not a target
        # process count (#218).
        pool_workers = min(self.max_workers, len(work_chunks))

        # Process chunks in parallel
        all_candidate_patterns = []

        try:
            with ProcessPoolExecutor(
                max_workers=pool_workers,
                initializer=_init_pattern_worker,
                initargs=(sequence, valid_events),
            ) as executor:
                # Submit all work chunks
                future_to_chunk = {
                    executor.submit(_detect_patterns_worker, chunk): chunk
                    for chunk in work_chunks
                }
                
                # Collect results as they complete with progress bar
                with tqdm(total=len(work_chunks), desc="Processing pattern chunks", unit="chunk") as pbar:
                    for future in as_completed(future_to_chunk):
                        try:
                            chunk_patterns = future.result(timeout=30)  # 30s timeout per chunk
                            all_candidate_patterns.extend(chunk_patterns)
                            pbar.update(1)
                            pbar.set_postfix(patterns=len(all_candidate_patterns))
                        except Exception as e:
                            pbar.write(f"  ⚠️  Chunk failed: {e}")
                            pbar.update(1)
                            continue
        
        except Exception as e:
            print(f"  ❌ Parallel processing failed, falling back to serial: {e}")
            # Fallback to serial processing
            return self._detect_patterns_serial(sequence, valid_events)
        
        print(f"📈 Found {len(all_candidate_patterns)} candidate patterns")
        
        # Select best non-overlapping patterns
        return self._select_best_patterns(all_candidate_patterns)
    
    def _detect_patterns_serial(self, sequence: List[Tuple], valid_events: List[Dict]) -> Dict:
        """Fallback serial pattern detection.

        Shares the same O(n·L) grouping helper as the parallel workers so the
        in-process fallback yields equivalent patterns to the parallel path
        (the old fallback used a different forward-only match scan)."""
        print("🔄 Using serial pattern detection")

        candidate_patterns = []
        for length in range(self.min_pattern_length,
                          min(self.max_pattern_length, len(sequence)) + 1):
            candidate_patterns.extend(
                _collect_length_candidates(sequence, valid_events, length)
            )

        return self._select_best_patterns(candidate_patterns)
    
    def _select_best_patterns(self, candidate_patterns: List[Dict]) -> Dict:
        """Select best non-overlapping patterns from candidates"""
        if not candidate_patterns:
            return {}

        # Sort by score (best first) with a deterministic tie-break on
        # (start, length). Parallel chunks complete in arbitrary `as_completed`
        # order, so sorting on score alone would let equal-score candidates
        # resolve by arrival order — making which non-overlapping patterns win
        # depend on host core count. The (start, length) tie-break makes the
        # selection identical across worker counts and vs the serial path (#46).
        candidate_patterns.sort(key=lambda x: (-x['score'], x['start'], x['length']))

        patterns = {}
        used_positions = set()
        
        for candidate in candidate_patterns:
            # Check if this pattern overlaps with already selected patterns
            pattern_positions = set()
            for pos in candidate['positions']:
                pattern_positions.update(range(pos, pos + candidate['length']))
            
            if not pattern_positions.intersection(used_positions):
                pattern_id = f"pattern_{len(patterns)}"
                # `variations` is always empty in the parallel path by design: the
                # O(n) hash grouping only finds EXACT repeats, so there is no
                # transposition/volume-variation detection here (unlike the
                # sequential EnhancedPatternDetector). Scoring is still shared via
                # score_pattern(length, exact_count, 0) (#103).
                patterns[pattern_id] = {
                    'events': candidate['events'],
                    'positions': candidate['positions'],
                    'exact_matches': candidate['positions'],
                    'variations': [],
                    'length': candidate['length']
                }
                used_positions.update(pattern_positions)
        
        return patterns

    def _get_variation_summary(self, patterns: Dict) -> Dict:
        """Generate summary of pattern variations"""
        return {
            pattern_id: {
                'variation_count': len(pattern_info.get('variations', [])),
                'exact_matches': len(pattern_info.get('exact_matches', []))
            }
            for pattern_id, pattern_info in patterns.items()
        }
    
    def _empty_result(self) -> Dict:
        """Return empty result structure"""
        return {
            'patterns': {},
            'references': {},
            'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0, 'unique_patterns': 0},
            'variations': {}
        }


# Shared, read-only data for the worker processes. The sequence and events are
# stashed here ONCE per worker via the pool initializer (see ProcessPoolExecutor
# initargs) instead of being pickled into every per-length work chunk (#114).
_WORKER_SEQUENCE: Optional[List[Tuple]] = None
_WORKER_EVENTS: Optional[List[Dict]] = None


def _init_pattern_worker(sequence: List[Tuple], events: List[Dict]) -> None:
    """ProcessPoolExecutor initializer: stash the shared sequence/events as module
    globals so each worker invocation reuses them instead of re-shipping them."""
    global _WORKER_SEQUENCE, _WORKER_EVENTS
    _WORKER_SEQUENCE = sequence
    _WORKER_EVENTS = events


def _collect_length_candidates(sequence: List[Tuple], events: List[Dict],
                               pattern_length: int) -> List[Dict]:
    """Find every repeated pattern of `pattern_length` in O(n) instead of O(n²).

    A single linear pass buckets each window's start position by window value.
    For each bucket the greedy non-overlapping match list is derived directly
    from the ascending positions — equivalent to the old "scan from pos 0, jump
    pattern_len on a match" rescan, but without re-scanning the whole sequence
    for every start.

    NOT fully equivalent to the old per-start output, though (#171/PAT-05):
    emitting a single candidate per distinct window, anchored at its first
    occurrence, means `_select_best_patterns` rejects or accepts that
    candidate's positions as one unit. If a higher-scoring pattern overlaps
    only this window's first occurrence, the whole candidate -- including its
    later, non-conflicting occurrences -- is rejected here. The per-start
    sequential detector can still recover those later occurrences via a
    separate candidate anchored past the contested region. So the two
    detectors' selected pattern sets can differ (metrics only today, #4) when
    the anchor occurrence of a window is itself contested."""
    n = len(sequence)
    if pattern_length > n:
        return []

    # Single linear pass: bucket each window's start position by window value.
    groups: Dict[Tuple, List[int]] = {}
    for start in range(n - pattern_length + 1):
        window = tuple(sequence[start:start + pattern_length])
        groups.setdefault(window, []).append(start)

    candidate_patterns = []
    for window, positions in groups.items():
        # Fewer than 3 occurrences can never yield 3 non-overlapping matches.
        if len(positions) < 3:
            continue

        # Greedy non-overlapping selection over ascending positions: take a
        # position whenever it starts at/after the previous match's end. This
        # reproduces the old scan-and-skip-`pattern_len` match list exactly.
        matches = []
        next_free = -1
        for pos in positions:
            if pos >= next_free:
                matches.append(pos)
                next_free = pos + pattern_length

        if len(matches) < 3:  # Minimum 3 non-overlapping occurrences
            continue

        # Score with the SHARED score_pattern (#103) so the parallel default path
        # ranks exact repeats identically to the sequential detector. This path is
        # exact-repeats-only (the O(n) hash grouping cannot detect transposed /
        # volume-scaled variations), so variation_count is always 0 here.
        total_count = len(matches)
        score = score_pattern(pattern_length, total_count, 0)

        if score > 0:
            anchor = matches[0]
            candidate_patterns.append({
                'start': anchor,
                'length': pattern_length,
                'pattern': window,
                'positions': matches,
                'score': score,
                'events': [events[i] for i in range(anchor, anchor + pattern_length)]
            })

    return candidate_patterns


def _detect_patterns_worker(work_chunk: Dict) -> List[Dict]:
    """Worker entry point: detect all patterns of one length over the shared
    sequence stashed by `_init_pattern_worker`. Runs in a separate process."""
    sequence = _WORKER_SEQUENCE
    events = _WORKER_EVENTS
    if sequence is None or events is None:
        # Defensive: only happens if invoked outside the initialised pool.
        return []
    return _collect_length_candidates(sequence, events, work_chunk['pattern_length'])


if __name__ == "__main__":
    # Test the parallel pattern detector
    print("🧪 Testing Parallel Pattern Detector")
    
    # Create test data
    test_events = []
    for i in range(1000):
        test_events.append({
            'frame': i,
            'note': 60 + (i % 12),  # Create some repeating patterns
            'volume': 100 - (i % 20)
        })
    
    from tracker.tempo_map import EnhancedTempoMap
    tempo_map = EnhancedTempoMap()
    
    # Test parallel detector
    parallel_detector = ParallelPatternDetector(tempo_map)
    result = parallel_detector.detect_patterns(test_events)
    
    print(f"Found {len(result['patterns'])} patterns")
    print(f"Compression ratio: {result['stats']['compression_ratio']:.1f}% reduction")
