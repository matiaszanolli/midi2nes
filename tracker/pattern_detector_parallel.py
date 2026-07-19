import multiprocessing as mp
import time
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from tracker.tempo_map import EnhancedTempoMap
from tracker.pattern_detector import (
    PatternCompressor, sample_events_for_detection, score_pattern, MAX_PATTERN_EVENTS
)

# Below this many events, a serial run finishes before a process pool would
# even finish spawning (pronounced under the `spawn` start method on macOS/
# Windows) -- skip pool construction entirely rather than pay full
# spawn/teardown overhead for a handful of events (#333/PERF-13).
SERIAL_EVENT_THRESHOLD = 200

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
        # Whether internal sampling below discarded events this run. Exposed so
        # a caller reporting coverage_ratio can label it as measured over a
        # lossy subset rather than the full song (#312/PAT-11).
        self.was_sampled = False
        if not events:
            return {
                'patterns': {},
                'references': {},
                'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0,
                          'unique_patterns': 0, 'total_events': 0, 'patterned_events': 0,
                          'coverage_ratio': 0},
                'variations': {}
            }

        # Provisional full-song count, used only for the no-valid-events early
        # return below; narrowed to the analyzed count after sampling (#257).
        total_events = len(events)

        print(f"🚀 Starting parallel pattern detection with up to {self.max_workers} workers")
        start_time = time.time()
        
        # Clean and validate events
        valid_events = self._filter_valid_events(events)
        if not valid_events:
            return self._empty_result(total_events)
        
        # Handle large sequences using the shared large-file policy (#21) so the
        # default path and the `detect-patterns` subcommand sample identically.
        original_count = len(valid_events)
        valid_events, self.was_sampled = sample_events_for_detection(valid_events, self.max_pattern_events)
        if self.was_sampled:
            print(f"⚠️  Large sequence ({original_count} events), sampling to "
                  f"{len(valid_events)} ({len(valid_events)/original_count*100:.1f}%, lossy)")
            print(f"   ✅ Sampled {len(valid_events)} events preserving temporal distribution")

        # coverage_ratio = patterned_events / total_events is measured over the
        # sampled sequence, so total_events must be the POST-sampling analyzed
        # count — using the pre-sampling len(events) understated coverage on a
        # large, fully-patterned song by (sampled / total) (#257/PAT-08).
        total_events = len(valid_events)

        # Convert to sequence for processing
        sequence = [(e['note'], e['volume']) for e in valid_events]

        # Split work into chunks for parallel processing
        patterns = self._detect_patterns_parallel(sequence, valid_events)
        
        # Compress patterns
        compressed_patterns, pattern_refs = self.compressor.compress_patterns(patterns)
        
        # Calculate compression statistics
        compression_stats = self.compressor.calculate_compression_stats(
            patterns, compressed_patterns, total_events
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
    
    def _build_work_chunks(self, sequence_len: int) -> List[Dict]:
        """Build (pattern_length, start_range) sub-chunks for the pool.

        The #114 fix made each chunk one whole pattern length, so total task
        count was exactly `max_pattern_length - min_pattern_length + 1` (10 at
        the pipeline defaults) regardless of core count or input size --
        several cores sit idle on a >10-core host (#332/PERF-12). Sub-chunk
        each length's start range so task count scales toward
        `self.max_workers`, while staying above `MIN_STARTS_PER_CHUNK` so
        tiny sub-ranges don't turn into pure per-task overhead."""
        lengths = list(range(self.min_pattern_length,
                             min(self.max_pattern_length, sequence_len) + 1))
        if not lengths:
            return []

        MIN_STARTS_PER_CHUNK = 2000
        target_total_chunks = max(len(lengths), self.max_workers * 2)
        subchunks_per_length = max(1, target_total_chunks // len(lengths))

        work_chunks = []
        for length in lengths:
            n_starts = sequence_len - length + 1
            n_sub = min(subchunks_per_length, max(1, n_starts // MIN_STARTS_PER_CHUNK))
            starts_per_sub = -(-n_starts // n_sub)  # ceil division
            for i in range(n_sub):
                start = i * starts_per_sub
                end = min(start + starts_per_sub, n_starts)
                if start >= end:
                    break
                work_chunks.append({'pattern_length': length, 'start_range': (start, end)})
        return work_chunks

    def _detect_patterns_parallel(self, sequence: List[Tuple], valid_events: List[Dict]) -> Dict:
        """Detect patterns using parallel processing.

        Each worker buckets window start positions for one (pattern_length,
        start-range) sub-chunk via the O(n) hash-grouping pass in
        `_collect_window_groups`, so total work is O(n·L) instead of the old
        per-start O(n²·L) rescan. Sub-chunks for the same length are merged
        (in start-range order, so position lists stay ascending) and scored
        once via `_select_candidates_from_groups` -- identical to what a
        single un-chunked pass over that length would produce (#332/PERF-12).
        The sequence and events are shipped to each worker process ONCE via
        the pool `initializer` rather than embedded in every chunk dict — the
        previous code pickled the full sequence ~(lengths × workers) times
        per detection run (#114)."""

        # Below this, a serial run finishes before a process pool would even
        # spawn (pronounced under the `spawn` start method), so skip pool
        # construction and the sub-chunk machinery entirely (#333/PERF-13).
        if len(sequence) < SERIAL_EVENT_THRESHOLD:
            print(f"🔄 Sequence below the {SERIAL_EVENT_THRESHOLD}-event serial "
                  f"threshold; skipping process pool")
            return self._detect_patterns_serial(sequence, valid_events)

        work_chunks = self._build_work_chunks(len(sequence))
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

        # Partial window-groups collected per length, as (start, groups) pairs
        # -- merged in start-range order once all of a length's sub-chunks are
        # in, so the merged position lists stay ascending (#332).
        length_group_parts: Dict[int, List[Tuple[int, Dict[Tuple, List[int]]]]] = {}
        failed_subchunks = []  # (length, start_range) that failed AND couldn't be recovered

        try:
            with ProcessPoolExecutor(
                max_workers=pool_workers,
                initializer=_init_pattern_worker,
                initargs=(sequence, valid_events),
            ) as executor:
                # Submit all work chunks
                future_to_chunk = {
                    executor.submit(_detect_window_groups_worker, chunk): chunk
                    for chunk in work_chunks
                }

                # Collect results as they complete with progress bar
                with tqdm(total=len(work_chunks), desc="Processing pattern chunks", unit="chunk") as pbar:
                    for future in as_completed(future_to_chunk):
                        chunk = future_to_chunk[future]
                        length = chunk['pattern_length']
                        start_range = chunk['start_range']
                        try:
                            groups = future.result(timeout=30)  # 30s timeout per chunk
                        except Exception as e:
                            # Instead of silently dropping this sub-chunk's window
                            # groups (degrading compression with only a transient
                            # tqdm line), recover it in-process with the same
                            # helper the workers use. Only if that also fails is
                            # this slice truly lost — recorded and surfaced
                            # durably after the loop (#106).
                            pbar.write(f"  ⚠️  Chunk for length {length} {start_range} "
                                       f"failed: {e} — retrying serially")
                            try:
                                groups = _collect_window_groups(sequence, length, *start_range)
                            except Exception as e2:
                                failed_subchunks.append((length, start_range))
                                groups = None
                                pbar.write(f"  ❌ Serial retry for length {length} {start_range} "
                                           f"also failed: {e2}")
                        if groups is not None:
                            length_group_parts.setdefault(length, []).append((start_range[0], groups))
                        pbar.update(1)

        except Exception as e:
            print(f"  ❌ Parallel processing failed, falling back to serial: {e}")
            # Fallback to serial processing
            return self._detect_patterns_serial(sequence, valid_events)

        # Merge each length's sub-chunk groups (in start-range order) and score
        # once per length -- identical result to an un-chunked pass.
        all_candidate_patterns = []
        for length in sorted(length_group_parts):
            parts = sorted(length_group_parts[length], key=lambda p: p[0])
            merged: Dict[Tuple, List[int]] = {}
            for _, groups in parts:
                for window, positions in groups.items():
                    merged.setdefault(window, []).extend(positions)
            all_candidate_patterns.extend(
                _select_candidates_from_groups(merged, valid_events, length)
            )

        # A transient stderr line vanishes with the tqdm bar; emit a persistent
        # end-of-run warning naming the lost slices so a partial detection run
        # stays visible (#106).
        if failed_subchunks:
            affected_lengths = sorted({length for length, _ in failed_subchunks})
            print(f"  ⚠️  Partial pattern detection: {len(failed_subchunks)} chunk(s) "
                  f"could not be analyzed (lengths {affected_lengths}); "
                  f"compression may be suboptimal")

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
        """Generate summary of pattern variations.

        Emits the SAME per-pattern shape as the sequential detector (#172):
        `{variation_count, exact_match_count, transposition_range, volume_range}`.
        The O(n) hash grouping finds exact repeats only, so variation_count is
        always 0 and the transposition/volume ranges are neutral (0, 0); only
        exact_match_count carries data on this path."""
        return {
            pattern_id: {
                'variation_count': len(pattern_info.get('variations', [])),
                'exact_match_count': len(pattern_info.get('exact_matches', [])),
                'transposition_range': (0, 0),
                'volume_range': (0, 0),
            }
            for pattern_id, pattern_info in patterns.items()
        }
    
    def _empty_result(self, total_events: int = 0) -> Dict:
        """Return empty result structure"""
        return {
            'patterns': {},
            'references': {},
            'stats': {'compression_ratio': 0, 'original_size': 0, 'compressed_size': 0,
                      'unique_patterns': 0, 'total_events': total_events,
                      'patterned_events': 0, 'coverage_ratio': 0},
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


def _collect_window_groups(sequence: List[Tuple], pattern_length: int,
                           start: int, end: int) -> Dict[Tuple, List[int]]:
    """Bucket each window start position in `[start, end)` by window value.

    This is the O(n) grouping half of `_collect_length_candidates`, split out
    so it can run over an arbitrary start-range slice instead of always the
    whole sequence (#332/PERF-12) -- `_detect_patterns_parallel` runs one of
    these per (length, start-range) sub-chunk and merges the partial dicts
    before handing them to `_select_candidates_from_groups`, so splitting
    this pass changes nothing about the result: it's the same total set of
    (window -> ascending start positions) entries, just computed in pieces.
    `end` may exceed `len(sequence) - pattern_length + 1`; callers clamp it.
    """
    groups: Dict[Tuple, List[int]] = {}
    for pos in range(start, end):
        window = tuple(sequence[pos:pos + pattern_length])
        groups.setdefault(window, []).append(pos)
    return groups


def _select_candidates_from_groups(groups: Dict[Tuple, List[int]], events: List[Dict],
                                   pattern_length: int) -> List[Dict]:
    """Turn a window->positions grouping into scored, non-overlapping-match
    candidates. `positions` for each window must already be in ascending
    order (true both for a single un-chunked `_collect_window_groups` call
    and for sub-chunk results merged in ascending start-range order)."""
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


def _collect_length_candidates(sequence: List[Tuple], events: List[Dict],
                               pattern_length: int) -> List[Dict]:
    """Find every repeated pattern of `pattern_length` in O(n) instead of O(n²).

    Thin wrapper over `_collect_window_groups` + `_select_candidates_from_groups`
    (split for #332/PERF-12 so the grouping pass can also run sub-chunked by
    start-range) -- used as-is by the serial fallback and by the parallel
    path's per-sub-chunk failure recovery, so their behavior is unchanged.

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
    groups = _collect_window_groups(sequence, pattern_length, 0, n - pattern_length + 1)
    return _select_candidates_from_groups(groups, events, pattern_length)


def _detect_window_groups_worker(work_chunk: Dict) -> Dict[Tuple, List[int]]:
    """Worker entry point: bucket window start positions for one
    (length, start-range) sub-chunk over the shared sequence stashed by
    `_init_pattern_worker`. Runs in a separate process (#332/PERF-12)."""
    sequence = _WORKER_SEQUENCE
    if sequence is None:
        # Defensive: only happens if invoked outside the initialised pool.
        return {}
    start, end = work_chunk['start_range']
    return _collect_window_groups(sequence, work_chunk['pattern_length'], start, end)


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
