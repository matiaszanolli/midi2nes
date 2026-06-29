# P-02: PatternExporter maps pattern_refs values as frame numbers, but the detector emits sequence indices (index-space vs frame-space mismatch)

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-29.md

## Description
`_create_pattern_map` lays each pattern's events at `start_pos + offset` and `expand_to_frames` iterates `range(max_frame + 1)`, i.e. it reconstructs a *contiguous index-space* frame stream keyed by the `positions` values. Those `positions` come from `compress_patterns` and are **sequence indices** (0,3,6,…), not the original `frame` numbers (which can be sparse, e.g. 0,10,20,… at 60 fps with rests). A round-trip therefore reproduces the original notes/volumes but at the wrong frame keys whenever frames are not densely packed from 0.

## Location
`exporter/pattern_exporter.py:12-20,36-41` (verified: `frame_to_pattern[start_pos + offset]`; `for frame in range(max_frame + 1)`); producer `tracker/pattern_detector.py` `compress_patterns`.

## Evidence
With events at frames `0,10,20,…110`, the detector returns `references = {"pattern_0": [0,3,6,9]}` and `expand_to_frames()` yields keys `0..11`, while the input frames were `0,10,…110`. The existing test `tests/test_pattern_exporter.py` *encodes* this index-space assumption (refs `[0,5]` → frames `0,1,5,6`), so it passes while masking the contract gap.

## Impact
Latent. The only consumer of `PatternExporter` is `exporter/exporter.py:generate_famitracker_txt_with_patterns`, which is **imported but never invoked** (the `export --format` choices are `nsf`/`ca65` only; the FamiTracker text path is dead). So no live ROM is affected today. If the FamiTracker exporter were ever wired up, every note would land on the wrong row for sparse input.

## Related
#4 (F-01, closed — references made analysis-only), P-08.

## Suggested Fix
Either (a) delete the dead `PatternExporter`/`exporter.py` FamiTracker path, or (b) carry the original `frame` numbers in `positions`/events and key `expand_to_frames` on real frames. Add a round-trip test with sparse frame numbers.

## Completeness Checks
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **TESTS**: A regression test pins this specific fix (sparse-frame round-trip)
- [ ] **SIBLING**: Same pattern checked in related files (other exporters)
