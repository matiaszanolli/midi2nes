**Severity:** MEDIUM · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-06-29.md

FamiTracker text export declares 5 channels but writes a single note column; negative octaves on low notes.

## Description
`generate_famitracker_txt_with_patterns` declares five channels (`COLUMNS 1 1 1 1 1`) but each row emits exactly one `note vol` cell (`f"{row:02X} | {note_str} 00 {vol}"`), not five channel cells — the CA65 path's other four channels are silently dropped from the FamiTracker view of the same song. Separately, `midi_note_to_ft` computes `octave = (note // 12) - 1`, producing negative octaves (e.g. MIDI 0–11 → octave −1) that FamiTracker does not accept.

## Location
`exporter/exporter.py:26` (`COLUMNS 1 1 1 1 1`), `:33-40` (one `note_str`/`vol` per row), `:9-12` (`midi_note_to_ft`).

## Spec ref
Consistency with the CA65 macro path (`pulse1/pulse2/triangle/noise/dpcm`, `exporter/exporter_ca65.py`).

## Evidence
- `:40` builds a single-column row; `COLUMNS 1 1 1 1 1` at `:26` promises five.
- `:10-11` `octave = (note // 12) - 1` with no floor at 0.
- `exporter/exporter_famistudio.py:161` `midi_note_to_famistudio` has the identical negative-octave issue; `:104` `event['sample_id']` KeyError risk on the dpcm branch (the CA65 path uses `note`, not `sample_id`).

## Impact
FamiTracker export describes a different (mono, possibly negatively-octaved) song than the ROM. FamiTracker export is a secondary format and is not wired into `run_export` (only imported at `main.py:24`), so blast radius is contained — MEDIUM.

## Related
EXP-05 (NSF stub); `exporter/exporter_famistudio.py:104` (`event['sample_id']` KeyError risk).

## Suggested Fix
Emit one cell per declared channel per row (or set `COLUMNS` to match the single column written), and clamp/offset octaves into FamiTracker's valid 0–7 range. Align the dpcm field name with the frames dict the rest of the pipeline produces.

## Completeness Checks
- [ ] **RANGE**: Emitted octaves are clamped to FamiTracker's valid 0–7 range
- [ ] **CHANNEL**: One cell per declared channel; channel set matches the CA65 path
- [ ] **SIBLING**: Same pattern checked in `exporter_famistudio.py`
- [ ] **TESTS**: A regression test pins this specific fix
