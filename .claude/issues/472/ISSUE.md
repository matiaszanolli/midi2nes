# 472: REG-32: Arranger DPCM tests pin raw slot ids as expected values — no test crosses to the packer to catch the id-space mismatch

URL: https://github.com/matiaszanolli/midi2nes/issues/472
Labels: bug, medium, regression

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-08-21.md

## Description
The arranger emits slot numbers (0 = kick, 1 = snare) that the pack stage interprets as *catalog* ids — in the shipped `dpcm_index.json`, id 0 is "(Konami, Contra Force) Hit 1" and id 1 is a kick, so every `--arranger` kick plays a generic hit and every snare plays a kick. The unit tests assert the slot values themselves (so they pass — and will need touching when the fix lands), and no test anywhere follows an arranger drum through `pipeline_integration` → `get_dpcm_sample_ids_from_frames` → packed filename. The suite is green while the audible output is wrong on every `--arranger` build with kick/snare.

Distinct from ARR-2026-08-21-5 (#452, which covers allocator floor/clamp edge cases, filed by today's arranger audit — not duplicated here).

## Evidence
- `tests/test_voice_allocator.py:38-42` pins `_allocate_dpcm(...)` results as `0` / `1` directly (confirmed by direct read of current file).
- `grep -rln dpcm_sample_map tests/` matches 7 files (`test_performance_suite.py`, `test_audio_fixes.py`, `test_enhanced_drum_mapper.py`, `test_famistudio_export.py`, `test_core.py`, `test_ca65_export.py`, `test_dpcm_packer.py`) — none of them arranger tests (confirmed).
- Catalog id mapping per DPCM-2026-08-21-2 (#445): `kick` = catalog 1318, `snare` = 1620.

## Impact
A HIGH wrong-audio defect (#445, DPCM-2026-08-21-2) is invisible to the suite, and the existing assertions actively entrench the wrong contract. Any fix must update these tests, and without an end-to-end identity test the same class of id-space drift (the legacy path's long-fixed D-02/#65) can recur unobserved.

## Related
#445 (DPCM-2026-08-21-2), #452 (ARR-2026-08-21-5, sibling test-gap finding, different scope), #65

## Suggested Fix
Add an end-to-end test: arrange a channel-9 kick+snare MIDI (or synthetic events) via `arrange_for_nes`, run the frames through the pack-stage id extraction, and assert the resolved catalog entries are the curated `kick`/`snare` samples (e.g. packed filename endswith `kick.dmc`) — red today. Rewrite the slot-id unit assertions in terms of the corrected contract (catalog ids or a `dpcm_sample_map`) when the fix lands.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
