# NH-03: Two divergent NTSC pitch tables (pitch_table.py vs exporter) an octave apart

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #16

## Description
`process_all_tracks` writes `pitch` from pitch_table.py (`fCPU/16` → A4=253). The bytecode exporter recomputes a base timer from its own `NOTE_TABLE_NTSC` (A4=127) and forms a pitch offset `pitch_val - base_timer` (exporter_ca65.py:819,834). The ~2x table difference makes the offset ≈ the base period (253−127=126), clamped to ±127, corrupting played pitch.

## Evidence
pitch_table A4=253 / exporter A4=127; pitch_table C4=426 / exporter C4=214 (verified by running tables). Offsets at exporter_ca65.py:819,834.

## Impact
Bytecode (pattern) mode pitch offset is garbage on every note. Affects every ROM built with patterns enabled (default).

## Hardware ref
`docs/APU_PITCH_TABLE_REFERENCE.md` §1–§3.

## Related
NH-02.

## Suggested Fix
Single source of truth — derive both Python `pitch` and exporter base table from the same per-channel formula, or have the exporter consume the frame `pitch` directly.
