# DPCM-2026-08-21-3: length_reg ceiling read overruns the 64-byte-aligned block by 1 byte for 2.3% of the catalog

**GitHub Issue:** #446
**Source Report:** docs/audits/AUDIT_DPCM_2026-08-21.md
**Severity:** LOW · **Domain:** dpcm
**Filed:** 2026-08-21

**Status:** NEW (residual edge of closed #295/DP-01; no prior report or issue covers the spill).

## Description
The engine reads `(length_reg*16)+1` bytes (`docs/APU_DMC_REFERENCE.md` §2, `$4013` formula). With `length_reg = (size+14)//16` (ceiling, correct per #295), the read length is `16*ceil((size-1)/16)+1`. The code comment asserts "the `.align 64` gap after each sample makes the few extra bytes safe zero-pad" — but when `size % 64` is 0 or in 50..63, the read length exceeds `aligned_size` by exactly 1 byte, and there *is* no gap: the next sample starts at the very next 64-aligned offset (`.align 64` inserts nothing when already aligned, and `_pack_samples` packs blocks contiguously by `aligned_size`). Measured against the real catalog (re-verified independently against the live `.dmc` files, not just the doc claim): **44 of 1941 samples (2.27%)** hit this window. Mid-bank, the DMC's last byte comes from the *next sample's first byte*; for a sample ending a full 8KB bank (`$C000+$2000`), the read lands at `$E000` — outside the swapped DPCM window, in the fixed PRG bank (arbitrary code bytes). This is *not* the `$FFFF`→`$8000` wrap quirk (max end address is `$E000`, far below `$FFFF`); the wrap remains impossible, as prior audits established.

Verified in current code: `dpcm_sampler/dpcm_packer.py:79-88` (`_place_sample` comment + `dpcm_length_val = max(0, (sample['size'] + 14) // 16)`), `:38` (`aligned_size = math.ceil(size_bytes / 64) * 64`), `:100-117` (`generate_assembly` places samples contiguously by `aligned_size` with a bare `.align 64` and no explicit padding to `length_reg*16+1`).

## Evidence
`size = 64` → `length_reg = (64+14)//16 = 4` → engine reads `4*16+1 = 65` bytes from a 64-byte aligned block; `size = 50..63` likewise read 65 bytes. Independent re-measurement against the shipped `.dmc` catalog (this validation pass): **44/1941 affected (2.27%)**, spill always exactly 1 byte — matches the audit report's figure exactly.

## Impact
8 garbage delta bits (±2 output-level nudges each, clamped 0–127 per doc §3) appended to the tail of an affected sample — ≈0.24 ms of wrong slope at rate 15; audibly negligible, never a crash or drop. Main cost is the false safety invariant in the comment, which a future packing change (e.g. removing `.align 64`, or tighter packing) could silently amplify.

## Related
#295/DP-01, #75.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §2 (`$4013` = `(L*16)+1` bytes), §4 (64-byte address alignment), §3 (±2 step, 0–127 clamp).

## Suggested Fix
Size each sample's block as `max(aligned_size, ceil((length_reg*16+1)/64)*64)` (one extra 64-byte row for the affected 2.3%), or pad the `.incbin` with explicit zero bytes up to `length_reg*16+1`; update the `_place_sample` comment either way.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
