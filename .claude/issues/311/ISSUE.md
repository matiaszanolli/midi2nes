# PAT-10: No test pins the exact-only round-trip invariant (referenced window == pattern events)

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-18.md
**Filed as:** #311

## Description
The PAT-01/#168 fix guarantees each persisted `positions` entry anchors a window whose `(note, volume)` content equals the pattern's stored `events`. This invariant holds in code, but the closest test only asserts that positions are `list`s of `int` — it never dereferences a position back into the sequence to confirm the window matches `events`.

## Location
`tests/test_pattern_integration.py:120-137` (`test_pattern_positions_format`)

## Suggested Fix
In `test_pattern_positions_format`, for each pattern assert `[(e['note'], e['volume']) for e in pattern['events']] == [sequence[p+k] for k in range(pattern['length'])]` for every `p` in `positions`, on a fixture with a known transposed/self-similar decoy.

## Related
#168/PAT-01, #170/PAT-04, PAT-11 (#312)
