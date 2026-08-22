# TD-31: Duplicated music.asm preamble between export_tables_with_patterns and export_song_bank_bytecode

- **Issue**: #466

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** Carried from 2026-08-07 (TD-31) — unfixed, never filed as a GitHub issue — filing now.

## Description
The ~15-line header block (`.importzp` line, DPCM `$C000` segment banner + `.align 64`, `CODE_8000` segment banner) is emitted verbatim by both bytecode exporters (`export_tables_with_patterns` and `export_song_bank_bytecode`). Verified still duplicated this cycle; the single-song copy additionally carries the #137 explanatory comment the jukebox copy lacks.

## Evidence
`exporter/exporter_ca65.py:1463-1492` vs `:1576-1592` — side-by-side read confirms both blocks emit the identical `.importzp ptr1, temp1, temp2, frame_counter`, `.segment "DPCM"` / `.align 64`, and `.segment "CODE_8000"` sequence.

## Impact
A future segment/preamble change (e.g. a new `.importzp` symbol) applied to one path silently skews the other; single-song vs jukebox `music.asm` drift.

## Suggested Fix
Extract a `_emit_bytecode_preamble(lines, jukebox=False)` helper used by both methods.

## Related
TD-37 (same file); EXP-2026-08-21-4 (jukebox-path guard asymmetry — a sibling symptom of the two paths not sharing code).

## Completeness Checks
- [ ] **SIBLING**: Both the single-song (`export_tables_with_patterns`) and jukebox (`export_song_bank_bytecode`) paths are verified to emit byte-identical preamble output after extraction
- [ ] **TESTS**: A golden-file diff (per the #136 methodology) confirms no `music.asm` byte change from the refactor
