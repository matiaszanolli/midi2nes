# EXP-2026-08-23-3: AUDIO_BYTECODE_SPEC.md still doesn't document the jukebox song_table format

**Severity:** LOW · **Domain:** exporters
**Source:** AUDIT_EXPORTERS_2026-08-23.md (carried from EXP-2026-08-07-3 / EXP-2026-08-21-5, never previously filed)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/510

## Description
The `song_index*5 + channel` parallel-array layout and per-song instrument-pointer
table are documented only in code docstrings, not in the spec. `docs/AUDIO_BYTECODE_SPEC.md`
has zero mentions of `song_table`/`song_count`/`song_instrument_ptr`/`jukebox`.

## Evidence
`exporter/exporter_ca65.py:1816-1852` emits the jukebox symbols; grep of the spec doc
(153 lines) returns nothing for them.

## Impact
Doc-rot / drift risk only — exporter and engine independently re-confirmed consistent
across three audit cycles.

## Related
EXP-2026-08-07-3, EXP-2026-08-21-5 (identical prior reports, never filed); #83/EXP-07;
#508, #509, #511, #512 (same audit).

## Suggested Fix
Add a §2 subsection documenting the five jukebox symbols, the `*5` stride, and channel
order.
