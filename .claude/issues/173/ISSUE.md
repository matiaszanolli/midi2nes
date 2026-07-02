# PAT-07: `_hash_pattern` returns `hash()` (docstring says str) — a collision silently merges unrelated patterns' references

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
The dedup key for "identical patterns" is Python's 64-bit
`hash(tuple((note, volume), ...))`, not the tuple itself (the docstring claims a "unique
hash"/str). A hash collision between two different event tuples would merge the second
pattern into the first: its `positions` are appended to the wrong pattern's `references`
and its own definition is dropped. Probability is astronomically low per song, but the
failure is silent and the fix is free — the tuple is already hashable and using it directly
as the dict key is exact.

## Location
`tracker/pattern_detector.py:769-771`; consumer `compress_patterns` (`:745-757`).

## Evidence
`pattern_hash = self._hash_pattern(...)` used as the sole identity key in `pattern_hash_map`; no equality confirmation on hit.

## Impact
Worst case (collision): wrong positions attributed to a pattern in `patterns.json`/stats — analysis-only today (#4). Also minor doc-rot (int vs documented str).

## Related
#4 (closed), PAT-01.

## Suggested Fix
Key `pattern_hash_map` on the event tuple itself (drop `_hash_pattern`, or make it return that tuple).

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
