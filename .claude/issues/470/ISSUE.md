# TD-37: _build_song_bytecode is the largest method in exporter_ca65.py and grew again

- **Issue**: #470

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** Carried from 2026-08-07 (TD-37) — observational, never filed as a GitHub issue — filing now.

## Description
`_build_song_bytecode` (`exporter/exporter_ca65.py:1102-1446`, ~345 lines; was ~330 on 2026-08-07) is the largest method in `exporter_ca65.py` and grew again, via `8ea7ac3`'s per-song `CODE_8000` segment resets. It serializes instruments, macros, and all five channel sequence streams with inline bank-overflow bookkeeping. The #136 lesson (per-channel emitters) applies directly: a per-channel sequence-stream emitter plus an instrument/macro-table emitter would mirror the direct-frames split that worked.

## Evidence
`exporter/exporter_ca65.py:1102` (`def _build_song_bytecode(self, frames, label_prefix='', start_bank=0):`) through `:1446` (return statement, next method `export_tables_with_patterns` begins after). `wc -l exporter/exporter_ca65.py` = 1685 (confirms TD-43's corrected count).

## Impact
Change amplification on the highest-traffic export path (both single-song bytecode and jukebox builds flow through it).

## Suggested Fix
When next touched for a functional change, extract per-channel stream emission and table emission; verify with the same golden-file diff harness #136 used. Not worth a standalone refactor commit before then.

## Related
#136/TD-11 (the successful sibling extraction), TD-31 (same file, preamble duplication), EXP-2026-08-21-6 (bank-overflow message quality — easier to fix per-emitter, if/when filed).

## Completeness Checks
- [ ] **SIBLING**: Any extraction mirrors the #136 per-channel emitter pattern already used by `export_direct_frames`
- [ ] **TESTS**: A golden-file diff across the existing bytecode-path test configs confirms zero output-byte change from the refactor
