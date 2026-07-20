# PAT-A: Variation-driven selection persists single-occurrence patterns with 0% compression

**Issue:** #365
**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-19.md
**Labels:** medium, patterns, bug

## Description
The sequential `PatternDetector` scores a candidate with `score_pattern(length, len(exact_matches), len(variations))` — variations count toward the `total_count` that clears the "≥3 occurrences" gate and drives the length/frequency bonuses. But after the PAT-01 (#168) fix, the candidate persists `positions = sorted(set(exact_matches))` (exact-only). A candidate can therefore be selected on the strength of its variations yet store a single exact position. Selection then marks that candidate's whole `occupied_positions` range used, blocking the genuinely-repeating shorter exact pattern that overlaps it. `calculate_compression_stats` computes `original_size = Σ len(events)·len(positions)` over the exact-only positions, so a single-position pattern yields `original_size == compressed_size` → `compression_ratio = 0.0`.

**Location:** `tracker/pattern_detector.py:242-263` (scoring/candidate build), `:295-319` (selection), `:866-885` (`calculate_compression_stats`)

## Evidence
Reproduced. Input = `ABCD` (4 events) repeated 4× followed by 5 filler events. Clean `ABCD×4` alone detects `pattern_0 len 4 positions [0,4,8,12]`, ratio 75.0%, coverage 100%. Add filler and the detector selects `pattern_0 len 10 positions [8]` (single occurrence), `compression_ratio 0.0`, `coverage_ratio 47.6`. The length-10 window wins on variation count; its variation positions consume frames 8–17 and block the length-4 `ABCD` candidate. Round-trip still exact — degraded compression + misleading 0% ratio, not a losslessness bug.

Confirmed in code: `score_pattern(...)` at `:242`/`:276`; `'positions': sorted(set(exact_matches))` at `:259`/`:288`; overlap-blocking on `occupied_positions` at `:307`; `original_size = Σ len(events)·len(positions)` at `:866-869`.

## Impact
`detect-patterns` output and both success banners under-report real compressibility and can report `compression_ratio 0.0` on songs with obvious repeats. No ROM impact (`export_tables_with_patterns` derives every byte from `frames`, does not consume `references`, #4). Parallel path unaffected.

## Related
PAT-01 (#168, closed), #4, #169/PAT-03.

## Suggested Fix
Score the sequential candidate on `len(positions)` (exact-only) so a single-exact-occurrence window cannot clear the ≥3 gate, or drop candidates whose exact `len(positions) < 3` before selection. Keep `occupied_positions` for overlap-blocking.

## Status
NEW / CONFIRMED at filing.
