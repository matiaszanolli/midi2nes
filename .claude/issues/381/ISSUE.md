# SAFE-2026-07-19-1: Full pipeline hard-requires dpcm_index.json in legacy mode; missing index aborts the whole run

**Issue:** #381
**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-19.md
**Labels:** low, safety, bug
**Dimension:** D2 (Malformed-Input Resilience) / D8 (Partial-Output)
**Status as filed:** NEW (Related: closed #256/D-18)

## Description
In legacy mode the full pipeline calls `assign_tracks_to_nes_channels(midi_data["events"], 'dpcm_index.json')` with a hard-coded path and no existence check. When `dpcm_index.json` is absent, `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py:231`) raises `FileNotFoundError`, which the pipeline's outer `except Exception` (`main.py:1167`) relays as a clean error line and `sys.exit(1)`. Asymmetric with run_map's guard (main.py:125-128) and step 5.5's optional-index posture (main.py:1078).

## Location
`main.py:869-870` (run_full_pipeline legacy mapping) vs `main.py:125-128` (run_map guard) and `main.py:1043-1078` (DPCM-packing step 5.5)

## Suggested Fix
Add the same `Path('dpcm_index.json').exists()` guard before the legacy mapping call in run_full_pipeline, or skip drum→DPCM mapping (map drums to noise) with a warning when the index is absent.

## Related
#256/D-18 (run_map guard, closed); #340 DP-DPCM-01 (percussion role gaps).
