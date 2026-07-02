# PL-05: A validation-failed (unbootable) ROM is left at the output path — always for the `compile` subcommand, and on the default path whenever no backup existed

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
`compile_rom` copies the linked ROM to the user's output path, then `validate_rom` runs.
If validation reports a boot-fatal defect, both callers `sys.exit(1)` — but the freshly
written unbootable `.nes` stays at the output path. On the default path the `finally`
restore repairs this only if the output existed before the run (backup taken at
`main.py:432-437`); a first-time build leaves the bad ROM behind. `run_compile` never
creates a backup at all, so it both (a) overwrites a pre-existing good ROM with no restore
path (a parity break with the default path's backup contract) and (b) always leaves the
failed ROM on disk.

## Location
`main.py:191-213` (`run_compile`: no backup, no cleanup on validation failure),
`main.py:679-683` (`finally` restore is a no-op when `backup_path is None`),
`compiler/compiler.py:144` (ROM copied to the output path before validation runs).

## Evidence
`run_compile` body (`main.py:197-213`) contains no `backup`/`unlink` logic;
`_restore_backup` (`main.py:140-145`) is a no-op for `backup_path=None`.

## Impact
The cardinal fail-fast rule ("no broken `.nes` left where the user expects a good one") is
violated in the artifact sense: the failure is loudly reported with a nonzero exit, but a
known-unbootable ROM persists at the destination — a later `ls`-and-flash, or any workflow
ignoring exit codes, ships it. Workaround exists (heed the error).

## Related
Closed #26 (restore unification), #15 (`compile` subcommand); PL-04.

## Suggested Fix
On validation failure with no backup, rename the bad ROM to `<name>.nes.failed` (or delete
it) before exiting; give `run_compile` the same backup-create/restore/cleanup contract as
the default path (factor the default path's backup block into a helper both use).

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
