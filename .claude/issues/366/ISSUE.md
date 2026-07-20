# PAT-B: DrumPatternDetector emergent scan self-overlaps (PAT-04/#170 fix not applied here)

**Issue:** #366
**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-19.md
**Labels:** low, patterns, dpcm, bug

## Description
PAT-04 (#170) fixed the self-overlap in `_find_pattern_matches` by starting the post-anchor scan at `start_pos + pattern_len`. The sibling `DrumPatternDetector.detect_drum_patterns` emergent-pattern scan was not updated: it iterates `for pos in range(start + 1, len(sequence) - length + 1)` and appends every similar `pos` with no skip-by-`length`. On a self-similar drum run (period < pattern length) this counts overlapping matches, inflating `len(matches)` fed to `score_drum_pattern` and `_optimize_drum_patterns` overlap math.

**Location:** `tracker/pattern_detector.py:666` (`detect_drum_patterns` emergent-pattern loop)

## Evidence
`tracker/pattern_detector.py:666` `for pos in range(start + 1, len(sequence) - length + 1):` with `matches.append(pos)` at `:671` and no `pos += length` skip, contrasted with fixed `_find_pattern_matches` at `:334-341` (`pos = start_pos + pattern_len` … `pos += pattern_len`). `DrumPatternDetector` is live: imported/used by `dpcm_sampler/enhanced_drum_mapper.py:4,208,257`.

## Impact
Suboptimal / inflated drum-pattern selection heuristics in the DPCM drum mapper. Affects which drum patterns are flagged, not lossless music data — no ROM corruption. Blast radius is drum-mapping quality only.

## Related
PAT-04 (#170, closed for `_find_pattern_matches`).

## Suggested Fix
Mirror the `_find_pattern_matches` non-overlap discipline in the emergent drum scan — skip `length` after a match.

## Status
NEW / CONFIRMED at filing.
