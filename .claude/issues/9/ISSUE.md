# NH-01: Noise and DPCM channels never reach their APU registers (all percussion/samples silent)

**Severity:** CRITICAL · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

process_all_tracks builds noise frames as {noise_mode, volume} and dpcm as {sample_id,
volume} — no note/period/dmc_level. Direct export iterates only pulse/triangle; bytecode
reads note=0 → silence. Every ROM with drums/samples is silent.

## Suggested Fix
Carry period(0-15)/mode into noise frames and dmc_level/trigger into dpcm frames; add
noise/DPCM emission to both exporter paths.
