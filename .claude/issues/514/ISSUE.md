# REG-37: run_song_build's catch-all exception handler, verbose-traceback, and backup cleanup remain untested

**Severity:** LOW · **Domain:** regression
**Source:** AUDIT_REGRESSION_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/514

## Description
`TestRunSongBuild` covers every named failure mode (capacity, prepare, compile,
validate) via typed `MIDI2NESError` subclasses, but three tail branches of
`main.py:1105-1121` remain unexercised: the `verbose=True` traceback-printing lines
(both except branches), the generic `except Exception` catch-all (no test raises a
non-`MIDI2NESError`), and the successful-rebuild `backup_path.unlink()` cleanup (no
test has both a pre-existing ROM and a successful build).

## Evidence
Scoped `--cov=main` on `-k RunSongBuild` reports `1108-1109, 1112-1116, 1121` missing.

## Impact
Low — defense-in-depth code, cosmetic leaked-backup-file risk only. But this is the
same control-flow area that broke before (#486/PIPE-2026-08-22-2).

## Related
REG-33 (2026-08-21, same location); #486/PIPE-2026-08-22-2; #515 (same audit).

## Suggested Fix
Add three tests: verbose-traceback assertion, a plain-`RuntimeError`-triggers-catch-all
test, and a successful-rebuild-removes-backup test.
