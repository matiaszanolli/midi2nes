# #41 — NH-11: note_to_timer range guard contradicts the channel ranges it serves

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

## Description
`note_to_timer` raises for `midi_note >= 96` ("out of NES range (24-95)"), but `CHANNEL_RANGES`/`channel_ranges` allow pulse up to MIDI 108 and the note table is generated for the full 0–127. The guard is inconsistent with the rest of the module (which clamps rather than raises) and would reject legal pulse notes 96–108 if used. It appears unused on the live path but is a correctness/consistency trap.

## Evidence
`if midi_note < 24 or midi_note >= 96: raise ValueError(... "(24-95)")` (pitch_table.py:133-134) vs `channel_ranges["pulse1"] = (24, 108)` (line 68). Confirmed in current tree.

## Impact
None today (unused); a foot-gun if adopted.

## Hardware ref
`docs/APU_PITCH_TABLE_REFERENCE.md` §2 (full 0–127 MIDI indexing).

## Related
NH-06 (clamp policy).

## Suggested Fix
Align the guard with the 11-bit/`t>=8` clamp policy (clamp, don't raise), or remove the dead method.

## Completeness Checks
- [ ] **RANGE**: Guard matches the 11-bit/`t>=8` clamp policy used elsewhere; legal pulse notes 96–108 not rejected
- [ ] **CHANNEL**: Channel ranges consistent across the module
- [ ] **TESTS**: A regression test pins that pulse note 108 is accepted (or method removed)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #75 — D-12: length_reg = (size-1)//16 floors — non-16k+1 samples under-read their tail

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`_place_sample` computes `dpcm_length_val = (sample['size'] - 1) // 16`. The DMC plays back `(length_reg*16)+1` bytes. For a `size` not of the form `16k+1`, the floor discards up to 15 trailing bytes (e.g. a 1024-byte sample → `length_reg=63` → 1009 bytes played, 15 lost). This is correct *clamping* (never over-reads), but it silently truncates the tail of most samples by a fraction of a frame.

## Location
`dpcm_sampler/dpcm_packer.py:66`

## Evidence
`dpcm_packer.py:66`; computed: `size=1024 → length_reg=63 → 1009 bytes` (15 lost); `size=2049 → 2049` (exact).

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §2/§4 — length formula `(L*16)+1`, 16-byte alignment.

## Impact
Sub-millisecond tail loss per sample; rarely audible. The packer does *not* pad `.dmc` data up to a `16k+1` boundary, so the quantization is lossy by design.

## Suggested Fix
Pad/round sample data up to the next `16k+1` length (with silence) rather than flooring, so the full sample plays.

## Completeness Checks
- [ ] **RANGE**: length_reg stays within `L<=255` after rounding up
- [ ] **TESTS**: A regression test pins this specific fix
