# 473: REG-34: FamiStudio tests never assert SEQUENCE↔PATTERN consistency, dodging the buggy ≥64-frame multi-channel branch

URL: https://github.com/matiaszanolli/midi2nes/issues/473
Labels: bug, medium, regression

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-08-21.md

## Description
`TestFamiStudioGoldenBytes` (the #232/REG-14 fix) pins exact rows — but only for a 3-frame song, where every channel emits exactly one pattern via the tail branch (per-channel counter), never the mid-loop branch (global `len(patterns)` counter). For any song where a channel *after the first* fills a 64-row pattern, the mid-loop key (`pulse2_<global>`) diverges from the SEQUENCE references (`pulse2_0..n`), producing a project whose sequences reference patterns that don't exist.

Ironically the suite already *generates* this broken output — `test_dpcm_sample_map_side_table_does_not_crash` builds 400 frames of pulse1+dpcm — but asserts only that two substrings are absent. Nothing anywhere asserts "every name in a SEQUENCE line appears as a PATTERN block", and no test feeds int-keyed frames (valid for the CA65 exporter) to catch the silent all-rests export (`if str(frame) in events` at `exporter/exporter_famistudio.py`).

## Evidence
- `grep -n SEQUENCE tests/test_famistudio_export.py` → no matches (confirmed).
- Fixture at `tests/test_famistudio_export.py:140-147` (`FRAMES`, global max_frame = 2 — "every channel emits exactly rows 00..02").
- Exporter key mismatch confirmed by direct read of `exporter/exporter_famistudio.py`: mid-loop pattern key `f"{channel}_{len(patterns)}"` (global counter) vs. tail key `f"{channel}_{len([k for k in patterns.keys() if k.startswith(channel)])}"` (per-channel counter) vs. SEQUENCE line `" ".join(f'"{channel}_{i}"' for i in range(pattern_count))` (per-channel indices).
- Underlying defects: **EXP-2026-08-21-2** (#440) and **EXP-2026-08-21-3** (#441), filed by today's exporters audit.

## Impact
FamiStudio export is wrong for any multi-channel song ≥ 64 frames — i.e. essentially all real exports — and the suite cannot see it. The same self-consistency assertion would guard all future pattern-splitting changes.

## Related
#440 (EXP-2026-08-21-2), #441 (EXP-2026-08-21-3), #232/REG-14, #339/REG-20

## Suggested Fix
Add a test exporting multi-channel frames with ≥ 64 frames per channel (e.g. pulse1+pulse2+triangle over 130 frames) asserting (a) every SEQUENCE-referenced name has a matching `PATTERN "<name>"` block and (b) the per-channel pattern count equals `ceil(frames/64)`. Add a second test that int-keyed frames either raise or export identically to their str-keyed twin.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **TESTS**: A regression test pins this specific fix
