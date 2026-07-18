# NH-29: noise_mode has no producer anywhere in the pipeline

**Severity:** LOW · **Domain:** nes-hardware

## Description
The engine and both exporter paths correctly thread a `noise_mode` bit from event → frame `control` (bit 6) → `$400E` bit 7 (`nes/emulator_core.py:184`, `exporter/exporter_ca65.py:248-249`, `nes/audio_engine.asm:495-503`). But no producer sets it: `tracker/track_mapper.py`'s drum-fallback path (`dpcm_sampler/enhanced_drum_mapper.py`) never sets it, and no GM-drum-to-noise-mode mapping exists. Every noise hit plays NES noise Mode 0 (long/hiss); Mode 1 (Metallic/short — snare/hat-appropriate) is unreachable.

## Location
`nes/emulator_core.py:166` (`mode = e.get('noise_mode', 0) & 1`, always defaults to 0); no producer found in `tracker/`, `arranger/`, or `dpcm_sampler/`.

## Suggested Fix
Low priority — have the drum mapper set `noise_mode: 1` for metallic-appropriate GM percussion (hi-hats/snares) using its existing note→sample classification, or leave as documented future work.

## Completeness Checks
- [ ] CHANNEL: Triangle has no volume/duty; per-channel pitch table correct
- [ ] TESTS: regression test pins this fix
- [ ] DOC: doc corrected if contradicted
