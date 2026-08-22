# DPCM-2026-08-21-4: @write_dpcm's $00-length placeholder sentinel also suppresses genuine length_reg=0 samples — 2 catalog entries can never play

**GitHub Issue:** #447
**Source Report:** docs/audits/AUDIT_DPCM_2026-08-21.md
**Severity:** LOW · **Domain:** dpcm
**Filed:** 2026-08-21

**Status:** NEW (residual edge of closed #367/DP-DPCM-05).

## Description
Per `docs/APU_DMC_REFERENCE.md` §2, `$4013 = 0` is the *valid* encoding for a real 1-byte sample (`(0*16)+1 = 1`). The #367 fix reuses `len_table == $00` as the "never packed / file missing" sentinel, so a genuinely packed 0/1-byte sample is indistinguishable from a placeholder and is silently skipped at trigger time. The shipped catalog contains two such entries: id 1103 `click (2)` (1 byte) and id 1452 `mute` (0 bytes). A MIDI hit resolving to either is packed, warned about by nobody, and never fires.

Verified in current code:
- `nes/audio_engine.asm:669-680` (`@write_dpcm`): `lda dpcm_len_table, y` / `bne @sample_ready` / `jmp @next_channel` — L=0 unconditionally skips the trigger.
- `dpcm_sampler/dpcm_packer.py:88`: `dpcm_length_val = max(0, (sample['size'] + 14) // 16)` — for `size=0`: `(0+14)//16=0`; for `size=1`: `(1+14)//16=0`. Both real sizes compute `length_reg=0`, identical to the unpacked-placeholder sentinel.
- `dpcm_sampler/dpcm_packer.py:141-145`: the `$00` placeholder scheme for un-indexed dense ids.
- Catalog re-verified directly: `dmc/click (2).dmc` is 1 byte, `dmc/mute.dmc` is 0 bytes, both present in `dpcm_index.json` at ids 1103 and 1452 respectively (exact byte sizes confirmed on disk during this validation pass).

## Evidence
`lda dpcm_len_table, y / bne @sample_ready / jmp @next_channel` treats L=0 as "unpacked"; catalog scan found exactly the two entries above (`dmc/click (2).dmc` = 1 byte, `dmc/mute.dmc` = 0 bytes, verified via `ls -la`).

## Impact
Negligible audio loss (a 1-byte sample is 8 delta bits ≈ 0.24 ms; `mute` being skipped is arguably the intent). Worth documenting so a future catalog with meaningful tiny samples doesn't hit it blind.

## Related
#367/DP-DPCM-05, #295/DP-01.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §2 (`(L*16)+1` — L=0 is a 1-byte sample, not "no sample").

## Suggested Fix
Either floor packed `length_reg` at 1 for any real sample (reads 17 bytes of its 64-byte block — harmless zero-pad) or warn at pack time when a real sample's `length_reg` computes to 0.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **TESTS**: A regression test pins this specific fix
