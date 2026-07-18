# DP-DPCM-03
**Filed as:** #342

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-18.md

## Description
`dpcm_converter.py` is not referenced anywhere in the codebase (grep for `dpcm_converter` / `convert_wav_to_dmc` finds only the module itself and its `__main__`); `generate_dpcm_index` scans pre-made `.dmc` files directly. Bit packing (`byte |= bits[i+j] << j`, LSB-first) and polarity (`1`=level-up) both match `docs/APU_DMC_REFERENCE.md` §1/§3, so the encoder is correct in isolation. However, two assumptions would produce wrong output if the tool were ever wired in: (a) it resamples to a fixed `sample_rate=8000` Hz (`dpcm_converter.py:5,67`) independent of the playback rate index, while the packer defaults `pitch_rate=15` (NTSC rate index 15 ≈ 33144 Hz), so a sample encoded at 8 kHz played at rate 15 runs ~4× fast (pitched up ~2 octaves); (b) `delta_encode` assumes a reconstruction start level of `prev=0x40` (64) (`:34`), but the hardware output level starts at `$00` (the engine's `$4011` silence init), producing a startup DC ramp on every sample.

## Evidence
`dpcm_converter.py:5` `sample_rate=8000`; `:34` `prev = 0x40`; `dpcm_packer.add_sample` `pitch_rate=15` default; `docs/APU_DMC_REFERENCE.md` §2 (rate index) / §3 (output level start); grep shows zero non-self callers.

## Impact
Currently none (dead tool). Latent: anyone using it to regenerate the `.dmc` catalog would get pitch-shifted samples and an attack transient.

## Related
DP-DPCM-02; overlaps the test-coverage gap tracked as REG-18 (converter is untested).

## Suggested Fix
If keeping the converter, derive its target sample rate from the intended DMC rate index (or write a matching `pitch` into the index), and start `delta_encode` at 0 to match the `$4011`-init playback level. Otherwise mark it clearly experimental / remove it.

## Completeness Checks
- [ ] **RANGE**: encoded output stays within DMC level range and the 4081-byte cap
- [ ] **TESTS**: if kept, a test pins the rate/start-level assumptions against the packer's rate index (ties to REG-18)
- [ ] **DOC**: converter marked experimental or its rate contract documented