# EXP-2026-07-19-2: FamiStudio export uses direct event[...] subscripts where the CA65 path uses defensive .get()

**Issue:** #370
**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-19.md
**Labels:** low, exporters, bug

**Dimension:** D7 Cross-Exporter Consistency
**Location:** `exporter/exporter_famistudio.py:105-107`

## Description
For `pulse1/pulse2/triangle` frames the FamiStudio emitter reads `event['note']` and `event['volume']` via direct subscript. The CA65 emitter reads the same fields defensively (`frame_data.get('note', 0)`, `frame_data.get('volume', 0)`), and the DPCM branch here was already hardened to `.get()` in #82. A frame dict missing `note` or `volume` (which the CA65 path tolerates) raises `KeyError` from the FamiStudio path.

## Evidence
`note = midi_note_to_famistudio(event['note'])` and `volume = min(15, event['volume'])` (`:105-107`) vs. `frame_data.get('pitch', 0)` / `.get('note', 0)` / `.get('volume', 0)` in `exporter_ca65.py:334-341`.

## Impact
Low and non-default: `generate_famistudio_txt` is not wired to any CLI subcommand, and `NESEmulatorCore` always populates `note`/`volume`, so no current pipeline input hits the `KeyError`. Latent robustness/consistency gap.

## Related
#82 (dpcm branch hardening in the same function), D7.

## Suggested Fix
Switch the tone-channel reads to `event.get('note', 0)` / `event.get('volume', 0)` to match the CA65 path's tolerance.

## Status as filed
NEW, CONFIRMED against current code (direct subscripts at exporter_famistudio.py:105-106; CA65 .get() at exporter_ca65.py:334-341).
