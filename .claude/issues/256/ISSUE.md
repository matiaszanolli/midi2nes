**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-05.md

## Description
`run_map` guards its *input* JSON via `load_json_stage` but passes a default `'dpcm_index.json'` into `assign_tracks_to_nes_channels`. If that index file is absent, `_load_sample_index` raises an uncaught `FileNotFoundError` and the standalone `map` subcommand exits with a raw traceback — in contrast to the DPCM *packer* path (`run_export` / `run_full_pipeline`), which handles a missing index gracefully ("No dpcm_index.json found, skipping"), and to every other step-by-step guard in `main.py` (`load_json_stage`, #120).

## Location
`main.py:96-104` (`run_map`) → `assign_tracks_to_nes_channels(..., 'dpcm_index.json')` → `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py`) raises `FileNotFoundError`.

Verified against current code: `run_map` resolves `dpcm_index_path = getattr(args, 'dpcm_index', None) or 'dpcm_index.json'` and calls `assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)` with no try/except around it.

## Evidence
`main.py` (`run_map`) has no try/except around `assign_tracks_to_nes_channels`; the packer call sites explicitly catch/skip a missing index.

## Impact
Low — the index ships with the repo, so this only bites a user who deletes or relocates it while using the step-by-step `map` subcommand. Cosmetic UX asymmetry (raw traceback vs. clean degrade), not a data-loss path.

## Related
#120 (step-by-step JSON guards); Dimension 8 of the audit-dpcm skill; D-17.

## Suggested Fix
Wrap the mapper call in `run_map` to catch a missing index and either emit a clean `[ERROR]` message or degrade to a drumless map (parity with the packer path).

## Completeness Checks
- [ ] **SIBLING**: The missing-index handling matches the packer path's graceful degrade / clean-error behavior
- [ ] **TESTS**: A regression test runs the `map` subcommand with `dpcm_index.json` absent and asserts a clean error (not a raw traceback)
