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

from tracker.pattern_detector_parallel import ParallelPatternDetector
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


if __name__ == "__main__":
    unittest.main()
