# PAT-10: No test pins the exact-only round-trip invariant (referenced window == pattern events)

**URL:** https://github.com/matiaszanolli/midi2nes/issues/311
**Labels:** bug, low, patterns

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-18.md

## Description
The PAT-01/#168 fix guarantees each persisted `positions` entry anchors a window whose `(note, volume)` content equals the pattern's stored `events`. This invariant holds in code (independently re-verified this audit via a fresh round-trip), but the closest test only asserts that positions are `list`s of `int` — it never dereferences a position back into the sequence to confirm the window matches `events`. A regression that re-admitted variation/self-overlap positions into `positions` (the exact defect #168/#170 fixed) would leave this test green.

## Evidence
```python
# tests/test_pattern_integration.py:129-137 (test_pattern_positions_format)
for pos in base_pattern['positions']:
    self.assertIsInstance(pos, int)
...
for pos in enhanced_pattern['positions']:
    self.assertIsInstance(pos, int)
```
No assertion compares `sequence[pos:pos+length]` against `pattern['events']`.

## Impact
None today (invariant holds). Latent: a regression of the highest-risk property in this subsystem (positions must be true exact repeats — the CRITICAL round-trip guarantee) would not be caught by the test named for exactly this check.

## Related
#168/PAT-01 (the invariant this would guard), #170/PAT-04 (self-overlap, same class), PAT-11 (companion finding, same report).

## Suggested Fix
In `test_pattern_positions_format`, for each pattern assert `[(e['note'], e['volume']) for e in pattern['events']] == [sequence[p+k] for k in range(pattern['length'])]` for every `p` in `positions`, on a fixture with a known transposed/self-similar decoy so the assertion has teeth.

## Completeness Checks
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **TESTS**: A regression test pins this specific fix
