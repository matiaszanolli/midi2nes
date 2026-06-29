# NH-03: Two divergent NTSC pitch tables (pitch_table.py vs exporter) an octave apart

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

process_all_tracks writes frame pitch from pitch_table.py (fCPU/16, A4=253). The bytecode
exporter recomputes a base timer from its own NOTE_TABLE_NTSC (A4=127) and forms
pitch_val - base_timer; the ~2x scale gap makes the offset ≈ the base period, which clamps
to ±127 and corrupts the played pitch in bytecode (pattern) mode (the default).

## Suggested Fix
Single source of truth — derive base timer and runtime table from the same per-channel
formula, or have the exporter consume the frame pitch directly.
