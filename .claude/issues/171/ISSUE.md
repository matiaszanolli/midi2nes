# PAT-05: `_collect_length_candidates` docstring overclaims equivalence with the per-start scan — anchor-blocked windows lose all their later occurrences

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
The parallel path emits exactly one candidate per distinct window, anchored at its first
occurrence, and `_select_best_patterns` rejects a candidate wholesale if any of its
positions overlaps an already-selected pattern. The sequential path still emits per-start
candidates, so when a higher-scoring pattern overlaps only the window's first occurrence,
the sequential detector recovers the later occurrences via a later-anchored candidate while
the parallel detector loses them all. The docstring's "collapsed onto that first occurrence
anyway" equivalence claim is therefore wrong in the general case.

## Location
`tracker/pattern_detector_parallel.py:238-249` (equivalence claim: "matches the old
per-start output because duplicate starts of the same window collapsed onto that first
occurrence in `_select_best_patterns` anyway"); whole-candidate rejection at `:179-199`.

## Evidence
Reproduced. Winner pattern P (4 occurrences) overlapping only W's first occurrence:
sequential covers W's later occurrences at 18 and 30 (`covered = [True, True, False]`),
parallel covers none (`[False, False, False]`); the two detectors also select structurally
different sets on the same input (length-12 × 3 positions vs length-6 × 4).

## Impact
Metrics-only today (compression quality/stats differ between default and fallback paths);
becomes user-audible pattern-selection divergence if references ever drive bytes. Also
doc-accuracy: the docstring asserts an equivalence the code does not have.

## Related
#103 (closed), #114 (closed), #46 (closed — determinism verified intact), PAT-04.

## Suggested Fix
Correct the docstring (claim "equivalent modulo anchor-blocking") or emit
per-occurrence-suffix candidates for windows whose anchor region is contested;
alternatively make selection reject per-position rather than per-candidate in both
detectors.

## Completeness Checks
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **TESTS**: A regression test pins this specific fix
