# EXP-06: FamiTracker export declares 5 channels but writes one column; negative octaves
Severity: MEDIUM · Domain: exporters · Source: AUDIT_EXPORTERS_2026-06-29.md

generate_famitracker_txt_with_patterns declares COLUMNS 1 1 1 1 1 (5 ch) but emits one
note vol cell per row (mono). midi_note_to_ft octave=(note//12)-1 -> negative octaves
(MIDI 0-11 -> -1) FamiTracker rejects.
Location: exporter/exporter.py:26, :33-40, :9-12.
SIBLING exporter_famistudio.py:161 (same neg octave), :104 event['sample_id'] KeyError
(CA65 path uses 'note' not 'sample_id').
Fix: one cell per declared channel OR COLUMNS match; clamp octave 0-7; align dpcm field.
