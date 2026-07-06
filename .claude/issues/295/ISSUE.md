# #295 — DP-01: length_reg floors — non-16k+1 DPCM samples under-read their tail (regression of #75)

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-06.md · **Regression of #75** (closed 2026-07-04; fix not present on `master`)

## Description
`dpcm_sampler/dpcm_packer.py:79` computes `dpcm_length_val = (sample['size'] - 1) // 16`. Per `docs/APU_DMC_REFERENCE.md` (`$4013`: sample length = `(L * 16) + 1` bytes), the DMC engine reads exactly `(length_reg * 16) + 1` bytes at playback. Flooring `(size-1)//16` makes the engine read `floor((size-1)/16)*16 + 1 ≤ size` bytes — under-reading up to 15 bytes of the sample tail for any `size` not exactly `16k+1`.

This is the exact bug closed as #75, but the closing fix is not on the current working tree — the code path is verifiably unchanged and still floors.

## Evidence
```
size = 100 → length_reg = 99 // 16 = 6 → engine reads 6*16+1 = 97 bytes; final 3 bytes (24 output deltas) never play.
```
The value flows into `dpcm_len_table` and is loaded into `$4013` by the generated `play_dpcm` trigger (`exporter/exporter_ca65.py:820-821`). The `.align 64` padding (`dpcm_packer.py:100`) means the extra bytes a `ceil` would read are zero-pad, not neighbouring sample data. Max in-range value stays safe: `(4081-1)//16 = 255`, fits the 8-bit register.

## Impact
Every packed sample whose byte length is not `≡ 1 (mod 16)` loses up to 15 bytes (~120 DMC output samples, ~15 ms at rate index 15) off its tail — an audible tail clip on short percussive samples. Blast radius: every drummed song whose `.dmc` files aren't coincidentally `16k+1` bytes.

## Suggested Fix
Use ceiling division: `dpcm_length_val = max(0, (size + 14) // 16)` (i.e. `ceil((size-1)/16)`, guarded for `size==0`), clamped to `min(255, …)` so the engine reads at least the whole sample. Land or re-apply the #75 fix on `master` and confirm it isn't reverting again.

## Completeness Checks
- [ ] **RANGE**: `length_reg` stays within the 8-bit `$4013` register (clamp `min(255, …)`)
- [ ] **SIBLING**: both packer call sites (`main.py:588-590`, `:953-956`) and any other `$4013` writer use the corrected length
- [ ] **TESTS**: a regression test pins a non-`16k+1` sample size to the correct `length_reg` (this is the second time #75 has regressed — the test must actually run on `master`)
- [ ] **DOC**: behavior matches `docs/APU_DMC_REFERENCE.md` §2/§4 `$4013` length formula
