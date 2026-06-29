# TD-07: Duplicated MIDI-note→note-name converters across exporter.py and exporter_famistudio.py

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
`midi_note_to_ft` and `midi_note_to_famistudio` are near-identical MIDI-note→note-name converters (`octave = (note // 12) - 1`, index a 12-name table), each with its own inline note-name array. They differ only in formatting (`C` vs `C-`), so the shared octave/index logic is duplicated and the two name tables can drift independently.

**Location:** `exporter/exporter.py:7-13` (`NOTE_TABLE`/`midi_note_to_ft`) and `exporter/exporter_famistudio.py:158-163` (`midi_note_to_famistudio`)

## Evidence
`exporter/exporter.py:7-13` vs `exporter/exporter_famistudio.py:158-163` — same formula, two separate note-name literals.

## Impact
Cosmetic export drift only (FamiTracker/FamiStudio text), not ROM output.

## Suggested Fix
Factor a shared `midi_note_to_name(note, sep)` helper in a common exporter util and pass the separator.

## Related
TD-01 (#89 — the same duplicate-formula pattern on the pitch path).

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters)
- [ ] **TESTS**: A regression test pins this specific fix
