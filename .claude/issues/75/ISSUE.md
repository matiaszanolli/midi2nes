# D-12: length_reg = (size-1)//16 floors — non-16k+1 samples under-read their tail

Issue: #75 — https://github.com/matiaszanolli/midi2nes/issues/75
Labels: bug, low, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

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
