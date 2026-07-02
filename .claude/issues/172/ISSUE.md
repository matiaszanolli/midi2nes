# PAT-06: `_get_variation_summary` shapes drift between the two detectors

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
The `variations` member of the detect-patterns envelope has a different per-pattern inner
shape depending on which detector produced it: the sequential summary carries
`transposition_range`/`volume_range`; the parallel summary instead carries `exact_matches`
and can never report a nonzero `variation_count`. A grep of `main.py`, `debug/`, `nes/`,
`exporter/` finds no reader of `['variations']`, and `run_detect_patterns` drops the key
from its JSON artifact entirely (by-design), so the drift is currently harmless — the same
latent-trap class as the fixed #104.

## Location
`tracker/pattern_detector.py:448-458` (`{variation_count, transposition_range,
volume_range}`) vs `tracker/pattern_detector_parallel.py:203-211` (`{variation_count,
exact_matches}`).

## Evidence
Reader grep returns nothing outside the detectors and tests; compare the two `_get_variation_summary` bodies.

## Impact
None today; a future consumer written against one shape breaks (or silently mis-reads) on the other path.

## Related
#104 (closed), #103 (closed).

## Suggested Fix
Emit one shape from both (e.g. always `{variation_count, exact_match_count,
transposition_range, volume_range}` with neutral values on the parallel path), mirroring
the #104 stats unification.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **TESTS**: A regression test pins this specific fix
