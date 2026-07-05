# PAT-09: --no-patterns direct-export stub omits the top-level variations key both detectors emit

GitHub: #258

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-05.md

## Description
Both real pattern producers return a 4-key envelope `{patterns, references, stats, variations}` (`tracker/pattern_detector.py:427-432`, `tracker/pattern_detector_parallel.py:84-89`). The `--no-patterns` direct-export stub returns only `{patterns, references, stats}` — no `variations`. The `stats` sub-schema was reconciled with the detectors by #104 (all 7 keys present, verified), but the top-level key set still drifts by one.

## Evidence
`main.py:779-791` — stub dict has keys `patterns`, `references`, `stats` only; no `variations`.
`grep -rn "\['variations'\]" main.py exporter/ nes/` finds **no consumer** of `pattern_result['variations']` outside the detectors/tests, so nothing `KeyError`s today.

## Impact
None today (the key is unread). Latent: the exact same trap class as the #104 bug that *was* fixed — the first consumer to do `pattern_result['variations']` unconditionally would `KeyError` only on the `--no-patterns` path, i.e. only under a flag combination tests may not cover.

## Suggested Fix
Add `'variations': {}` to the stub dict at `main.py:779-791` so all three producers emit an identical top-level key set.

## Related
#104 (closed, fixed the sibling `stats` drift), PAT-06/#172 (the *inner* variation shape also drifts between the two detectors).

## Completeness Checks
- [ ] **CONTRACT**: Stub top-level key set matches both detectors' `{patterns, references, stats, variations}` exactly
- [ ] **SIBLING**: No other stub/dummy pattern_result path omits the key
- [ ] **TESTS**: A test asserts the `--no-patterns` stub carries all four top-level keys
