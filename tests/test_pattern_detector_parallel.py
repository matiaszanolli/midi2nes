"""Dedicated tests for ParallelPatternDetector (#46 / REG-06).

These cover the parts the pipeline smoke tests and TestParallelPatternEquivalence
(in test_patterns.py) leave open:
  1. Determinism — detection results must NOT depend on host core count.
  2. Fallback — a worker-pool failure must fall back to in-process detection
     and still return the full result contract, not silently yield nothing.
  3. Round-trip / contract — the result keeps the documented key shape and every
     detected pattern's occurrences reconstruct identical content.
"""

import unittest
from unittest.mock import patch

from tracker.pattern_detector_parallel import (
    ParallelPatternDetector, _collect_window_groups, SERIAL_EVENT_THRESHOLD
)
from tracker.tempo_map import EnhancedTempoMap

REQUIRED_KEYS = {"patterns", "references", "stats", "variations"}


def _repeating_events(n=180):
    """Events with clear, overlapping repeats so several candidate patterns
    compete for selection (exercising the score-sort + non-overlap logic)."""
    return [{"frame": i, "note": 60 + (i % 6), "volume": 100 - (i % 4)}
            for i in range(n)]


class TestParallelDeterminism(unittest.TestCase):
    """Detection must be invariant to worker count (CI vs local core counts)."""

    def _detect_with_workers(self, events, workers):
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        detector.max_workers = workers
        return detector.detect_patterns(events)

    def test_results_identical_across_worker_counts(self):
        events = _repeating_events()
        r1 = self._detect_with_workers(events, 1)
        r2 = self._detect_with_workers(events, 2)
        r4 = self._detect_with_workers(events, 4)

        # Pattern selection (ids, events, positions) must match exactly.
        self.assertEqual(r1["patterns"], r2["patterns"])
        self.assertEqual(r1["patterns"], r4["patterns"])
        # References and the headline compression figure must match too.
        self.assertEqual(r1["references"], r4["references"])
        self.assertEqual(r1["stats"]["compression_ratio"],
                         r4["stats"]["compression_ratio"])
        self.assertGreater(len(r1["patterns"]), 0,
                           "fixture should yield patterns for the test to mean anything")


class TestParallelFallback(unittest.TestCase):
    """A pool failure must degrade to the in-process serial path, not to no
    patterns (guards the documented HIGH-severity fallback)."""

    def test_pool_failure_falls_back_to_serial(self):
        events = _repeating_events(120)
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)

        # Force the ProcessPoolExecutor construction to blow up so the outer
        # except-path in _detect_patterns_parallel takes the serial fallback.
        with patch("tracker.pattern_detector_parallel.ProcessPoolExecutor",
                   side_effect=RuntimeError("pool unavailable")):
            result = detector.detect_patterns(events)

        self.assertTrue(REQUIRED_KEYS.issubset(result.keys()))
        self.assertGreater(len(result["patterns"]), 0,
                           "fallback must still detect patterns, not silently yield none")

    def test_fallback_result_matches_normal_result(self):
        """The serial fallback output must equal the normal (pool) output —
        a failed pool must not change WHICH patterns ship."""
        events = _repeating_events(120)
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)

        normal = detector.detect_patterns(events)
        with patch("tracker.pattern_detector_parallel.ProcessPoolExecutor",
                   side_effect=RuntimeError("pool unavailable")):
            fell_back = detector.detect_patterns(events)

        self.assertEqual(normal["patterns"], fell_back["patterns"])
        self.assertEqual(normal["references"], fell_back["references"])


class TestParallelRoundTrip(unittest.TestCase):
    """Result-contract shape and lossless-repeat integrity."""

    def test_result_has_contract_keys(self):
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        result = detector.detect_patterns(_repeating_events())
        self.assertTrue(REQUIRED_KEYS.issubset(result.keys()))

    def test_empty_input_keeps_contract(self):
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000))
        result = detector.detect_patterns([])
        self.assertTrue(REQUIRED_KEYS.issubset(result.keys()))
        self.assertEqual(result["patterns"], {})

    def test_detected_occurrences_reconstruct_original(self):
        """Every occurrence of a detected pattern must be an exact repeat, so
        expanding references back over the sequence reproduces the original
        content (the lossless round-trip the compression relies on)."""
        events = _repeating_events(300)
        sequence = [(e["note"], e["volume"]) for e in events]
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        result = detector.detect_patterns(events)
        self.assertGreater(len(result["patterns"]), 0)
        for pid, info in result["patterns"].items():
            length = info["length"]
            positions = info["exact_matches"]
            ref = tuple(sequence[positions[0]:positions[0] + length])
            for pos in positions:
                self.assertLessEqual(pos + length, len(sequence),
                                     f"{pid} occurrence at {pos} runs past the sequence")
                self.assertEqual(tuple(sequence[pos:pos + length]), ref,
                                 f"{pid} occurrence at {pos} is not an exact repeat")


class TestSubChunkedScaling(unittest.TestCase):
    """#332/PERF-12: task count must scale past the flat pattern-length-range
    ceiling for large inputs, while staying unchanged for small ones."""

    def test_large_input_scales_past_the_length_range_ceiling(self):
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        detector.max_workers = 16  # simulate a many-core host, host-independent
        chunks = detector._build_work_chunks(200_000)
        # 10 lengths (3..12): the pre-fix code always produced exactly 10.
        self.assertGreater(len(chunks), 10,
                           "a large sequence must sub-chunk past the old flat ceiling of 10")

    def test_small_input_keeps_one_chunk_per_length(self):
        """No sub-chunking below MIN_STARTS_PER_CHUNK -- small/medium inputs
        behave exactly as before the fix (one chunk per length)."""
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        detector.max_workers = 16
        chunks = detector._build_work_chunks(1000)
        self.assertEqual(len(chunks), 10)  # exactly one chunk per length (3..12)
        lengths = sorted(c["pattern_length"] for c in chunks)
        self.assertEqual(lengths, list(range(3, 13)))


class TestSubChunkMergeCorrectness(unittest.TestCase):
    """#332/PERF-12: splitting a length's start range into sub-chunks and
    merging the partial window-groups back (in start-range order) must
    reproduce EXACTLY what a single un-chunked grouping pass would -- this is
    the invariant the whole fix depends on for not changing ROM output."""

    def test_split_and_merged_groups_equal_unsplit_groups(self):
        sequence = [(60 + (i % 5), 100 - (i % 3)) for i in range(5000)]
        length = 7
        n_starts = len(sequence) - length + 1

        whole = _collect_window_groups(sequence, length, 0, n_starts)

        # Uneven sub-ranges (not a clean divisor of n_starts) on purpose.
        boundaries = [0, 1200, 3300, n_starts]
        merged = {}
        for a, b in zip(boundaries, boundaries[1:]):
            part = _collect_window_groups(sequence, length, a, b)
            for window, positions in part.items():
                merged.setdefault(window, []).extend(positions)

        self.assertEqual(whole, merged)


class TestSubChunkedEndToEnd(unittest.TestCase):
    """#332/PERF-12: a real (multi-process) sub-chunked run over a large,
    sub-chunking-triggering input must select the identical pattern set the
    serial baseline does."""

    def test_subchunked_parallel_run_matches_serial_baseline(self):
        events = _repeating_events(6000)
        sequence = [(e["note"], e["volume"]) for e in events]

        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        detector.max_workers = 16  # forces >1 sub-chunk/length at this size

        chunks = detector._build_work_chunks(len(sequence))
        self.assertGreater(len(chunks), 10, "fixture must actually exercise sub-chunking")

        parallel_patterns = detector._detect_patterns_parallel(sequence, events)
        serial_patterns = detector._detect_patterns_serial(sequence, events)

        self.assertGreater(len(serial_patterns), 0, "fixture should yield patterns")
        self.assertEqual(parallel_patterns, serial_patterns)


class TestSerialGuard(unittest.TestCase):
    """#333/PERF-13: a small input must never construct a process pool."""

    def test_small_input_does_not_construct_process_pool(self):
        events = _repeating_events(40)
        self.assertLess(len(events), SERIAL_EVENT_THRESHOLD)
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)

        with patch("tracker.pattern_detector_parallel.ProcessPoolExecutor") as mock_pool:
            result = detector.detect_patterns(events)

        mock_pool.assert_not_called()
        self.assertTrue(REQUIRED_KEYS.issubset(result.keys()))

    def test_input_at_threshold_boundary_still_uses_pool_path(self):
        """An input at/above SERIAL_EVENT_THRESHOLD must still be eligible for
        the process pool (the guard must not over-trigger). A mocked pool
        that raises is enough to prove the constructor was reached -- the
        existing outer fallback (#218) then degrades to serial gracefully,
        which test_pool_failure_falls_back_to_serial already covers."""
        events = _repeating_events(SERIAL_EVENT_THRESHOLD + 50)
        detector = ParallelPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                           min_pattern_length=3, max_pattern_length=12)
        with patch("tracker.pattern_detector_parallel.ProcessPoolExecutor",
                   side_effect=RuntimeError("pool unavailable")) as mock_pool:
            result = detector.detect_patterns(events)
        mock_pool.assert_called()
        self.assertTrue(REQUIRED_KEYS.issubset(result.keys()))


if __name__ == "__main__":
    unittest.main()
