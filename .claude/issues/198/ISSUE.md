# EXP-10: Tone-channel note clamps in the exporter have no log/counter — silent pitch change on out-of-range notes

**Severity:** MEDIUM · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-03.md

**Status:** NEW

**Spec ref:** `docs/AUDIO_BYTECODE_SPEC.md` §3 "Note Range ($00-$5F)" — the note byte is
hard-capped at 95 by the bytecode format itself (values $60+ are Length/other commands), so
*some* clamp is mandatory and correct; the gap is the missing diagnostic, not the clamp
itself.

## Description
Per the SKILL's own verification note on the #158/NH-16 fix, a clamped note should be "at
least logged/counted somewhere upstream." It is not. Neither `exporter_ca65.py` nor any
upstream stage (`nes/emulator_core.py`, `arranger/pipeline_integration.py`,
`tracker/track_mapper.py`) counts, logs, or warns when a note gets clamped at either
boundary. A melodic line that goes above MIDI note 95 (B6) or, for tone channels, below 24
(C1) is silently re-pitched with zero indication to the user — the ROM plays a different
note than the MIDI file specified, and nothing in the CLI output, `--verbose` trace, or any
diagnostic tool (`debug/rom_diagnostics.py`, `debug/check_rom.py`) surfaces it.

## Location
`exporter/exporter_ca65.py:987-997` (`elif note > 95: note = 95` /
`elif channel != 'noise' and 0 < note < 24: note = 24`)

## Evidence
```python
elif note > 95:
    note = 95
elif channel != 'noise' and 0 < note < 24:
    note = 24
```
`grep -rn "out of range\|clamped\|clamp_count\|notes_clamped" nes/ exporter/ arranger/
tracker/ main.py` turns up no counter/log tied to this clamp (the only other clamp-like
logging is unrelated velocity clamping in `nes/emulator_core.py`).

## Impact
Any song with content above B6 (fairly common for piccolo/flute/high lead lines, or a track
transposed up) or, for tone channels, below C1 plays wrong, unannounced notes — a "MEDIUM,
silent, no workaround without inspecting output audio" case per the severity rubric's
clamp-diagnostics guidance. Not CRITICAL because the clamp is bytecode-format-mandated
(there is no valid alternative encoding to fall back to) and it does not corrupt other
channels/data — it only mis-pitches the affected notes.

## Related
#158/NH-16 (the low-end clamp's *value* was fixed there; this finding is about the *lack of
any diagnostic* on both clamp directions, which was out of scope for that fix). #41/NH-11 (a
different, unused method's inconsistent range guard — not the same code path).

## Suggested Fix
Have `export_tables_with_patterns` accumulate a per-song count of clamped notes (both
directions) and print a one-line summary (e.g. "12 notes clamped to NES tone range (24-95);
pitch may differ from the MIDI file") at the end of export, similar to how other lossy
pipeline steps already report their own stats.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
