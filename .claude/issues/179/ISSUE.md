# PL-06: `--version` combined with other arguments is swallowed and a full build runs instead

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
`python main.py --version` alone prints the version (special-cased at argv length 2). But
`python main.py --version song.mid` takes the manual default-path loop, which files
`--version` into `global_args` where nothing consumes it — the full pipeline runs (parse ->
… -> compile), overwriting/creating `song.nes`, and the version is never printed. An
argparse-handled flag would have printed-and-exited regardless of other args.

## Location
`main.py:828-830` (bare `--version` special case), `main.py:864-866` (manual loop collects
`--version` into `global_args`), `main.py:896-905` (`SimpleArgs` never reads it).

## Evidence
Live at HEAD: `python main.py --version missing.mid` prints `[ERROR] Input MIDI file not
found` — the pipeline path was reached; no version output.

## Impact
Surprising side effect (an unrequested build, possibly minutes of CC65 work and an
output-file overwrite — mitigated by the backup contract) for a query-only flag. Low
realism, no data corruption.

## Related
PL-01/PL-02 (manual-dispatch flag handling).

## Suggested Fix
In the manual loop, treat `--version` like argparse does: print `MIDI2NES {__version__}` and `sys.exit(0)` immediately.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
