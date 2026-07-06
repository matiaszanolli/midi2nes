# #298 — EXP-10: tone-channel note clamps in CA65 macro path have no log/counter

**Severity:** MEDIUM · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-06.md · **Status:** Carried from prior audit reports (2026-07-03 / 07-05), never filed as a GitHub issue — filing now.

## Description
The CA65 macro path's tone-channel note clamps (`exporter/exporter_ca65.py:1072-1085`: `note > 95 → 95`, and `channel != 'noise' and 0 < note < 24 → 24`) are silent. Neither `exporter_ca65.py` nor any upstream stage (`nes/emulator_core.py`, `arranger/pipeline_integration.py`, `tracker/track_mapper.py`) counts, logs, or warns when a note is clamped. A melodic line above MIDI note 95 (B6) or, for tone channels, below 24 (C1) is silently re-pitched with zero indication — no CLI output, `--verbose` trace, or diagnostic tool surfaces it.

The clamp *itself* is correct and mandatory: per `docs/AUDIO_BYTECODE_SPEC.md` §3, the note byte is hard-capped at 95 ($5F) because $60+ are Length/other commands. The gap is the missing **diagnostic**, not the clamp.

## Evidence
```python
# exporter/exporter_ca65.py:1072-1085
if channel == 'dpcm':
    if note > 255:
        note = 255
elif note > 95:
    note = 95
elif channel != 'noise' and 0 < note < 24:
    note = 24
```
`grep -rn "clamp\|out of range\|notes_clamped\|warn" exporter/exporter_ca65.py` returns only explanatory comments — no counter or log tied to this clamp. The same information loss surfaces differently in the FamiStudio exporter, which clamps the *octave* (`exporter_famistudio.py:168`), so for a sub-C1 / above-B6 input the two exporters describe different pitches — a consequence of this same missing visibility, not an independent bug.

## Impact
Any song with content above B6 (piccolo/flute/high leads, or a transposed-up track) or, for tone channels, below C1 plays wrong, unannounced notes on the default (macro-bytecode) pipeline. No workaround short of inspecting the output audio.

## Suggested Fix
Have `export_tables_with_patterns` accumulate a per-song count of clamped notes (both directions) and print a one-line summary at end of export, e.g. `"⚠ 12 notes clamped to NES tone range (24-95); pitch may differ from the MIDI file"`, mirroring how other lossy steps report their stats.

## Completeness Checks
- [ ] **RANGE**: the clamp still bounds the note to the bytecode-legal `[24,95]` tone range (and `dpcm` to 255)
- [ ] **SIBLING**: the direct-frame path and the FamiStudio exporter report the same clamp/loss consistently
- [ ] **TESTS**: a test asserts the clamp count is reported for an out-of-range song
