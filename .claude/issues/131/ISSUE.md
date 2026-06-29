# TD-03: Copy-pasted _find_pattern_matches across the two pattern detectors (already drifting)

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
Both detectors carry an effectively identical `_find_pattern_matches` (same algorithm, same `pos += pattern_len` overlap-skip), differing only in comments — i.e. the copies have already begun to drift. The two detectors must agree on match semantics for the fallback (`ParallelPatternDetector` → `EnhancedPatternDetector`) to produce equivalent output; a fix to one will silently not reach the other.

**Location:** `tracker/pattern_detector.py:277-292` vs `tracker/pattern_detector_parallel.py:202-217`

## Evidence
`diff` of the two slices shows only docstring/comment differences (`# Skip the length of the pattern to avoid overlaps` vs `# Skip to avoid overlaps`).

## Impact
Future correctness fix lands in one detector only; the parallel/serial paths can diverge in which matches they find.

## Suggested Fix
Extract `_find_pattern_matches` (and `_find_matches` in the dead threaded class) to a shared module-level helper.

## Related
TD-04 (dead `ThreadedPatternDetector` in the same module, tracked in #105), REG-06 (#46).

## Completeness Checks
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same pattern checked in related files (both detectors)
- [ ] **TESTS**: A regression test pins this specific fix
