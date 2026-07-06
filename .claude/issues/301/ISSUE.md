# #301 — MAP-2026-07-06-2: capacity pre-flight undercounts DPCM .align 64 padding

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-06.md · **Status:** NEW

## Description
`estimate_segment_sizes` (`main.py:148-166`) scores a `.incbin "…", 0, N` as `N` (or the file size) and ignores the `.align 64` directive that precedes each packed DPCM sample (`dpcm_sampler/dpcm_packer.py:98-108`), so a `DPCM_NN` segment's estimated size is short of its real ROM footprint by up to 63 bytes per sample. A heuristic that can *under*-count and let an oversized bank pass the capacity pre-flight into a raw `ld65` region overflow is, in principle, a Dimension-4 concern.

In practice this is unreachable through the normal pipeline: `DpcmPacker` packs by `aligned_size = ceil(size/64)*64` and enforces `bank_total ≤ BANK_SIZE (8192)` at pack time (`dpcm_packer.py:38,60-64`), so a packer-produced `DPCM_NN` bank's real (aligned) size never exceeds 8 KB. The undercount matters only for a hand-edited `music.asm` whose per-bank aligned total sits in the ≤63-byte-per-sample window between the estimate and 8192 — and even then `ld65` errors cleanly on the region overflow.

## Evidence
`estimate_segment_sizes` (`main.py:153-164`) has no `.align` branch; `dpcm_packer.py:100` unconditionally emits `.align 64` inside each `DPCM_NN` segment, while `dpcm_packer.py:60-64` already caps each bank's *aligned* total at `BANK_SIZE`. Read-only confirmation; no repro needed (the packer prevents the trigger).

## Impact
A marginally-oversized *hand-edited* DPCM bank could print "✓ fits" from the pre-flight and then fail at `ld65` with a region-overflow instead of a clean pre-flight message. No effect on packer-produced ROMs. Cosmetic defense-in-depth accuracy gap.

## Suggested Fix
In `estimate_segment_sizes`, round each `.incbin` contribution up to the next `.align` boundary when a preceding `.align N` is active (or add the alignment slack once per aligned block), so the pre-flight's `DPCM_NN` totals match the packer's `aligned_size`. Low priority given the packer already guarantees the invariant.

## Completeness Checks
- [ ] **SIBLING**: the pre-flight estimate matches the packer's `aligned_size` for MMC3 and MMC1 DPCM banks
- [ ] **TESTS**: a test asserts `estimate_segment_sizes` accounts for `.align 64` padding
