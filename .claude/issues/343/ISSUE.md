# DP-DPCM-04
**Filed as:** #343

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-18.md

## Description
The dense remap encodes `note = min(255, dense_id + 1)` (`nes/emulator_core.py:220`). For a song referencing N distinct DPCM samples, `dense_id` ranges 0..N-1. At N ≤ 255 the round-trip is exact (max `note` = 255). At N ≥ 256, `dense_id = 255` also encodes to `note = 255` and collides with `dense_id = 254`; every `dense_id ≥ 255` becomes unreachable and its hits play sample #254 instead. The `min()` clamp prevents an out-of-range byte (no crash), but the aliasing is silent — no warning, unlike the same-frame-collapse drop counters nearby. This is the residual of #200/D-14 pushed to the dense level rather than the raw-catalog level.

## Evidence
`emulator_core.py:207-223` builds `dense_id_of` and encodes `min(255, dense_id + 1)` with no branch/warning when `len(referenced_ids) > 255`.

## Impact
A song with 256+ distinct drum samples (packable — 256 tiny 64-byte samples fit in ~2 banks) silently plays the wrong sample for the overflow drums. Musically near-unreachable, but the failure mode is silent wrong-content.

## Related
#200/D-14 (raw-catalog aliasing, fixed by this remap).

## Suggested Fix
When `len(referenced_ids) > 255`, emit a warning (mirroring the same-frame-collapse drop count) so the aliasing is visible; optionally document the 255-distinct-drum ceiling.

## Completeness Checks
- [ ] **RANGE**: the dense_id→note encoding stays in byte range and the ceiling is surfaced
- [ ] **TESTS**: a test with >255 distinct samples asserts a warning is emitted
- [ ] **DOC**: the 255-distinct-drum ceiling documented