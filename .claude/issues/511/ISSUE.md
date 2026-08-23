# EXP-2026-08-23-4: Multi-song bank-overflow error still loses which song failed

**Severity:** LOW · **Domain:** exporters
**Source:** AUDIT_EXPORTERS_2026-08-23.md (carried from EXP-2026-08-07-4 / EXP-2026-08-21-6, never previously filed)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/511

## Description
A bank-budget overflow raises `ValueError` naming only the channel, not the song, so
users must bisect the bank. The recent `#505`/`#506` refactor leaves `prefix` and a
running `songs_consumed` index already in scope in the loop, making a fix cheap.

## Evidence
`exporter/exporter_ca65.py:1556-1562` (error names channel/bank only);
`:1810-1820` (per-song loop has no try/except around `_build_song_bytecode`).

## Impact
Correct failure, poor diagnostics only.

## Related
EXP-2026-08-07-4, EXP-2026-08-21-6 (identical prior reports, never filed); #505/#506;
#508, #509, #510, #512 (same audit).

## Suggested Fix
Wrap the `_build_song_bytecode` call: `try/except ValueError as e: raise
ValueError(f"song index {songs_consumed} ('{prefix.rstrip('_')}'): {e}") from e`.
