# REG-18
**Filed as:** #337

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-07-18.md

## Description
The module that turns a WAV into NES DMC sample data (`dpcm_sampler/dpcm_converter.py`: `convert_wav_to_unsigned_pcm`, `delta_encode`, `dpcm_compress`, `convert_wav_to_dmc`) has **zero** test references and 0% coverage. Its output is raw DMC bytes consumed by the DPCM channel. The encoding is non-trivial DSP: `delta_encode` produces reconstructed 7-bit values clamped to `[0,127]` with ±1 steps, then `dpcm_compress` re-derives 1-bit deltas from consecutive comparisons and truncates at `dmc_bytes[:4081]`. A silent bug here (off-by-one in the bit-packing `byte |= (bits[i+j] << j)`, wrong mid-range start `0x40`, or the `4081` cap) produces a wrong-sounding or truncated drum sample with no test to catch it.

## Evidence
`grep -rn --include="*.py" "dpcm_converter|convert_wav_to_dmc|dpcm_compress"` returns only the module itself — no importer in the pipeline and no test. Coverage run: `dpcm_sampler/dpcm_converter.py 57 57 0% 1-85`.

## Impact
Blast radius is reduced because the module is a **standalone asset-prep CLI**, not wired into the automated MIDI→ROM pipeline (checked-in `.dmc` files + `dpcm_index.json` are what the pipeline consumes). But it is the only path that produces those bytes, so a regression is silently-wrong drum audio for anyone rebuilding samples.

## Related
`dpcm_index.json`, `generate_dpcm_index.py` (REG-19).

## Suggested Fix
Add `tests/test_dpcm_converter.py`. Concrete inputs: (a) a synthetic 8-bit mono WAV written with `wave` in a `tmp_path` fixture → assert `convert_wav_to_unsigned_pcm` length/dtype/range; (b) a known ramp array → assert exact `delta_encode` output and that `dpcm_compress` packs 8 bits/byte LSB-first with correct padding; (c) assert `convert_wav_to_dmc` never emits more than 4081 bytes and returns the written length.

## Completeness Checks
- [ ] **RANGE**: the test asserts DMC bytes stay within the encoder's documented range and the 4081-byte cap
- [ ] **TESTS**: a regression test pins `delta_encode`/`dpcm_compress` exact byte output