# EXP-2026-08-21-9: export_direct_frames Data size summary counts 4 tables for every channel, contradicting its own estimator

GitHub: https://github.com/matiaszanolli/midi2nes/issues/444

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-08-21.md

## Description
The end-of-export summary multiplies frames × 4 × channel-count, overstating the emitted RODATA whenever noise (3 tables) or dpcm (1 table) is active — for a 5-channel song it reports 20 bytes/frame where 16 are emitted (+25%). The same file already contains the correct per-channel accounting in `estimate_direct_export_size`, added precisely so capacity decisions wouldn't rely on this kind of drift; only the human-facing print still uses the old math. Nothing downstream consumes the printed number (capacity pre-flight sizes the real file).

## Location
`exporter/exporter_ca65.py:1002` (`total_bytes = (max_frame + 1) * 4 * len(all_channels)`)

## Spec ref
`exporter/exporter_ca65.py:112-123` (`estimate_direct_export_size`'s own per-channel accounting: pulse/triangle 4, noise 3, dpcm 1)

## Impact
Cosmetic/misleading console output only, on the `--no-patterns` path.

## Related
Distinct from #361's capacity-estimate defect, which was about the *pre-flight* path and is fixed.

## Suggested Fix
Reuse `estimate_direct_export_size(frames)` (or its `bytes_per_frame` map) for the summary.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (summary byte count matches `estimate_direct_export_size` for a mixed pulse/noise/dpcm channel set)
