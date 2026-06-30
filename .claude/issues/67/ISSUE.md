# D-04: Emulator clamps sample_id to 94 — high-id drums collapse to one wrong sample
Severity: HIGH · Domain: dpcm · Source: AUDIT_DPCM_2026-06-29.md

process_all_tracks stores note = min(95, sample_id+1) reusing the 0-95 MIDI-note
ceiling. sample_id is NOT a MIDI note. Any sample_id>=94 clamps to note 95 -> id 94.
Compounded by exporter_ca65.py:952-953 (if note>95: note=95).
Location: nes/emulator_core.py:124; exporter/exporter_ca65.py:952-953.
Fix: bound sample_id by real format/byte range, not 0-95 note ceiling; emulator_core
and bytecode exporter must agree. CONTRACT + SIBLING.
