# PIPE-2026-07-19-1: Wrong-stage JSON passes the [] required-keys guard and yields silent empty output

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-19.md

## Description
`run_frames`, `run_export`, and `run_detect_patterns` call `load_json_stage(args.input, [], 'map'/'frames')` with an **empty `required_keys` list** because the mapped/frames channel dict has no fixed key. The guard (`main.py:99-103`) therefore only catches missing/corrupt/non-object files, not a structurally-valid file from the *wrong* stage. If a user hands `parse`-stage JSON (`{"events":[...], "metadata":...}`) to `frames`, `process_all_tracks` iterates its keys, matches none of `pulse1/pulse2/triangle/noise/dpcm` (there is no `else` branch), and returns an empty `processed` dict. The pipeline then writes an empty frames file and continues with no warning.

## Evidence
- Empty `required_keys` at the three debug-path call sites:
  - `main.py:137` (`run_frames`) — `load_json_stage(args.input, [], 'map')`
  - `main.py:565` (`run_export`) — `load_json_stage(args.input, [], 'frames')`
  - `main.py:673` (`run_detect_patterns`) — `load_json_stage(args.input, [], 'frames')`
- `nes/emulator_core.py:124-243` `process_all_tracks` has only `if/elif` arms for the five known channels and ends with `return processed`. An unrecognized key is silently skipped — no `else`, no diagnostic.
- The guard's missing-key check (`main.py:99-103`) is a no-op when `required_keys == []`.

## Impact
Debug-path ergonomics only. A mistyped stage produces an empty/near-empty ROM with zero diagnostics instead of a clear "wrong stage" error. The correct producer (`map`) always emits recognized channel keys, so no happy-path breakage; not reachable from the default `run_full_pipeline`.

## Related
SAFE-01/#120 (the guard this extends); Dimension 1 open question in the pipeline audit skill.

## Suggested Fix
In `run_frames`/`run_export`/`run_detect_patterns`, after load, assert the dict contains at least one recognized channel key (intersect keys with the known channel set `{pulse1, pulse2, triangle, noise, dpcm}`) and exit 1 with a "does not look like `<stage>` output" message when it does not.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same `[]`-guard weakness checked across all three subcommands (`run_frames`/`run_export`/`run_detect_patterns`)
- [ ] **TESTS**: A regression test pins the wrong-stage-input rejection
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
