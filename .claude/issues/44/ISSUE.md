# REG-04: The entire --arranger front-end has zero test coverage (no test references it)

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
`grep -rln "arrange_for_nes|--arranger|arranger" tests/` returns **nothing**. The arranger is one of two front-ends (`--arranger` mode does role analysis, GM mapping, smart channel allocation, and arpeggiation for polyphony) and feeds the same downstream `frames` contract. None of its logic is exercised by any test — the 56-73% coverage shown is incidental import/init, not behavioral verification. Arpeggiation correctness (chord → alternating-note sequence) and channel allocation are completely unguarded.

## Evidence
No test file imports `arrange_for_nes`, `VoiceRoleAnalyzer`, or `VoiceAllocator` (confirmed: `grep -rln` in `tests/` returns nothing). Coverage of `arranger/role_analyzer.py` (56%), `arranger/voice_allocator.py` (73%), `arranger/pipeline_integration.py` (69%), `arranger/gm_instruments.py` (92%) decision branches is incidental.

## Impact
Any regression in role detection, GM→channel mapping, or arpeggiation ships silently. Blast radius: every `--arranger` run (polyphonic MIDI). A wrong voice dropped or a triangle assigned a duty would not be caught.

## Related
See `/audit-arranger` for behavioral correctness.

## Suggested Fix
Add `tests/test_arranger.py`:
1. **Role analysis**: feed `test_midi/multiple_tracks.mid`; assert `VoiceRoleAnalyzer` tags the lowest-avg-pitch track as bass and highest as melody.
2. **Arpeggiation**: craft a 3-note chord event (C/E/G at one tick) → assert `arrange_for_nes` emits an alternating single-note sequence on one channel; period matches `docs/arpeggio.md`.
3. **Channel-honoring invariant**: assert no event routed to `triangle` carries a duty/volume field the triangle can't honor (cross-check `docs/APU_TRIANGLE_REFERENCE.md`).
4. **Contract**: assert `arrange_for_nes(events)` output is structurally interchangeable with `process_all_tracks` output (same `{channel: {frame: {...}}}` shape).

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **CONTRACT**: `arrange_for_nes` output shape matches `process_all_tracks` (asserted by a test)
- [ ] **SIBLING**: Both front-ends (legacy + arranger) covered by the channel-honoring invariant
- [ ] **TESTS**: `tests/test_arranger.py` pins role/arpeggio/channel/contract behavior
- [ ] **DOC**: Arpeggiation period matches `docs/arpeggio.md`
