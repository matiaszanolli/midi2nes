# REG-38: generator laziness test can't distinguish lazy consumption from eager materialization

**Severity:** LOW · **Domain:** regression
**Source:** AUDIT_REGRESSION_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/515

## Description
`test_generator_songs_are_pulled_one_at_a_time_not_materialized_upfront`
(`tests/test_ca65_export.py:1128-1158`) only checks a generator's final yielded-count
state, which is identical whether songs were pulled lazily or the generator was fully
drained upfront. The actual laziness property is proven by two sibling tests in the
same commit batch (`test_bank_overflow_on_generator_input_stops_before_later_songs_are_pulled`,
`test_dpcm_bearing_song_stops_before_later_songs_are_pulled`), so no real coverage gap
exists — this specific test's name overstates what it verifies.

## Evidence
Only assertion is `assertEqual(yielded_so_far, [1, 2, 3, 4])` after the full call
returns — no interleaving check.

## Impact
None today (property covered elsewhere); would silently lose its stated purpose on a
future regression that reintroduces eager materialization.

## Related
#505/PERF-B-02; the two sibling tests that actually prove laziness; #514 (same audit).

## Suggested Fix
Strengthen to assert interleaving order, or delete as redundant.
