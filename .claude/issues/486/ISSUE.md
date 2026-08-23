# PIPE-2026-08-22-2: run_song_build has no backup/restore contract, no exception safety net, ignores prepare_project's return value

**Filed:** https://github.com/matiaszanolli/midi2nes/issues/486
**Severity:** HIGH · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-22.md

## Description
`run_song_build` is the only one of the three ROM-build entry points without a backup/restore contract and typed-exception safety net. A re-run over a previously-good ROM that compiles but fails `validate_rom` leaves the broken ROM at the output path; any exception out of `prepare_project` surfaces as a raw traceback; `prepare_project`'s boolean return is also ignored.

## Location
`main.py` (`run_song_build`'s build tail): no `_backup_existing_rom`/`_restore_backup`, no `try`/`except`/`finally`, `prepare_project`'s return unchecked.

## Related
#467/TD-32 (open, tracks the code-duplication root cause — its own body explicitly anticipates this HIGH-severity companion finding), #26/F-11, #178/PL-05 (the same contract, already implemented on the other two build paths).

## Suggested Fix
Parameterize `build_and_validate_rom` to accept `song_count`/an already-exported `music_asm` path, and have `run_song_build` call it inside the same backup/restore/typed-exception wrapper the other two paths use.
