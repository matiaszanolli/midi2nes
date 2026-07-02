# PAT-04: `_find_pattern_matches` lets the first match overlap the anchor — self-overlapping "non-overlapping" matches inflate counts and diverge from the parallel matcher

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
The scan for further occurrences starts at `start_pos + 1` instead of
`start_pos + pattern_len`, so in self-similar runs (period < pattern length) the first
"match" overlaps the anchor window. Only after a match does the code skip `pattern_len`.
The parallel `_collect_length_candidates` uses a correct `next_free` greedy, so the two
detectors return different `exact_matches` for identical input.

## Location
`tracker/pattern_detector.py:291-306` — `pos = start_pos + 1` (`:297`) contradicts the
"Skip the length of the pattern to avoid overlaps" intent (`:302`); correct greedy for
comparison: `tracker/pattern_detector_parallel.py:266-274`.

## Evidence
Reproduced. 12 identical notes, pattern length 4: sequential
`exact_matches = [0, 1, 5]` (positions 0 and 1 overlap); parallel returns `[0, 4, 8]`.
Because overlapping windows in a self-similar run have identical content, reconstruction
would still be value-consistent (no double-write corruption is possible from this alone) —
the damage is inflated occurrence counts -> inflated `score_pattern` totals and
`original_size`/`compression_ratio`, plus fallback-vs-default result divergence beyond the
documented variations difference (#103).

## Impact
Sequential path (fallback + `detect-patterns` subcommand) overstates repetition on
drones/ostinati and selects differently from the default path; stats inflate (feeds
PAT-03). No byte-level effect (#4).

## Related
#131 (open, duplication aspect), #103 (closed), PAT-01, PAT-03.

## Suggested Fix
Initialize the scan at `start_pos + pattern_len` (matching the stated intent and the
parallel greedy), and add a shared-behavior test comparing both detectors' `exact_matches`
on a constant run.

## Completeness Checks
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
