"""Regression coverage for #365/PAT-A — >=3 exact-occurrence selection gate.

The sequential detector scored a candidate on exact + variation occurrences but
persisted only exact positions, so a window that cleared the occurrence gate on
its variations could store a single exact position (0% compression) and block a
genuinely-repeating shorter pattern. Selection now requires >=3 EXACT
occurrences, aligning the sequential path with the parallel one (which passes
variation_count=0 and so already requires >=3 exact repeats).
"""


class TestExactOccurrenceGate:
    @staticmethod
    def _ev(n):
        return {"note": n, "volume": 8}

    def _repeating_with_filler(self):
        seq = []
        for _ in range(4):
            seq += [self._ev(1), self._ev(2), self._ev(3), self._ev(4)]
        seq += [self._ev(9), self._ev(10), self._ev(11), self._ev(12), self._ev(13)]
        return seq

    def test_selects_repeating_pattern_not_single_occurrence(self):
        from tracker.pattern_detector import EnhancedPatternDetector
        d = EnhancedPatternDetector(tempo_map=None, min_pattern_length=3,
                                    max_pattern_length=12, analyze_tempo=False)
        res = d.detect_patterns(self._repeating_with_filler())
        # The real repeat (ABCD at 0,4,8,12) is selected...
        for pid, p in res["patterns"].items():
            assert len(p["positions"]) >= 3, (
                f"{pid} persisted {p['positions']} (<3 exact occurrences)")
        # ...and the ratio is non-zero (the old bug reported 0.0).
        assert res["stats"]["compression_ratio"] > 0

    def test_no_pattern_stored_with_fewer_than_three_exact(self):
        from tracker.pattern_detector import PatternDetector
        # ABC twice + distinct filler: only 2 exact repeats -> below the gate.
        seq = [self._ev(n) for n in (1, 2, 3, 1, 2, 3, 7, 8, 9)]
        d = PatternDetector(min_pattern_length=3, max_pattern_length=6)
        patterns = d.detect_patterns(seq)
        for p in patterns.values():
            assert len(p["positions"]) >= 3

    def test_min_occurrences_constant_shared(self):
        from tracker.pattern_detector import MIN_PATTERN_OCCURRENCES, score_pattern
        assert MIN_PATTERN_OCCURRENCES == 3
        # Below the threshold scores negative (rejected); at/above scores.
        assert score_pattern(4, MIN_PATTERN_OCCURRENCES - 1, 0) < 0
        assert score_pattern(4, MIN_PATTERN_OCCURRENCES, 0) > 0
