# P-05: Parallel and sequential detectors are not equivalent — different scoring and no variation detection in the parallel (default) path

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-29.md

## Description
The default pipeline uses `ParallelPatternDetector`, which scores with a simplified `_score_pattern` (no length tiers, no `exact_bonus`) and sets `"variations": []` unconditionally in `_select_best_patterns`. `EnhancedPatternDetector` (the fallback and `detect-patterns` subcommand) uses a richer `score_pattern` with exponential length bonuses and full variation detection. For the same input the two select **different** pattern sets. The `_get_variation_summary` in the parallel path reports `variation_count: 0` for every pattern.

## Location
`tracker/pattern_detector_parallel.py:218-234` (`_score_pattern`), `:195` (`"variations": []`), `:236-244` (`_get_variation_summary`) vs `tracker/pattern_detector.py:150-189` (`score_pattern` with tiers + variation detection).

## Evidence
Verified: parallel `_score_pattern` at `pattern_detector_parallel.py:218`; `"variations": []` at `:195`; variation summary at `:236`. Sequential `score_pattern` defined inline at `pattern_detector.py:150`; variation detection via `_detect_pattern_variations` at `:78`.

## Impact
Because `patterns` is only a boolean switch in CA65 export (#4), neither scoring nor variations change the emitted bytes today — so this is metrics-only divergence (different `compression_ratio`/variation counts between a default run and a `detect-patterns` run on the same data), not wrong music. Would rise to HIGH if `references`→bytes is ever wired.

## Related
#46 (REG-06, open — parallel path untested), #4 (closed), P-09.

## Suggested Fix
Either share a single scoring function between the two detectors (the duplication is also a tech-debt cross-ref) or document that the parallel path is intentionally coarser and variation-free.

## Completeness Checks
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same scoring/variation logic checked across both detectors
- [ ] **TESTS**: A regression test pins parallel/sequential equivalence (or documents the divergence)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
