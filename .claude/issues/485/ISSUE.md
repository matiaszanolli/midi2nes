# PIPE-2026-08-22-1: Wrong-stage JSON still silently yields empty output on the step-by-step path

**Filed:** https://github.com/matiaszanolli/midi2nes/issues/485
**Severity:** HIGH · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-22.md

## Description
`load_json_stage` with `required_keys=[]` accepts any JSON object, and `process_all_tracks` silently ignores unknown top-level keys (no `else` branch on its channel-name dispatch), so feeding a *parse*-stage file to the `frames` subcommand produces an empty `{}` frames dict with exit 0. The empty output flows onward unchallenged: `export` happily writes a valid-looking `music.asm` with zero channels and exit 0.

Regression of #377 (closed as "Fixed in c4894d2", but that commit was never merged to master).

## Location
`main.py` (`run_frames`/`run_export`/`run_detect_patterns`, all use `load_json_stage(..., [], ...)`); `nes/emulator_core.py` (`process_all_tracks` — `if/elif` over the five channel names, no `else`).

## Related
#377/PIPE-2026-07-19-1 (regression of), #120/SAFE-01, orphaned branch `fix/issue-377-wrong-stage-json-guard` (commit `c4894d2`).

## Suggested Fix
Re-land `c4894d2`'s guard (or re-implement fresh): reject a JSON object containing none of the five channel keys, with the parse-stage `events` key called out specifically in the error message.
