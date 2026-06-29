# D-04: Emulator clamps sample_id to 94 — high-id drums collapse to one wrong sample

Issue: #67 — https://github.com/matiaszanolli/midi2nes/issues/67
Labels: bug, high, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** HIGH · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`process_all_tracks` stores the dpcm trigger as `note = min(95, sample_id + 1)`. The index ships 1923 samples (ids 0–1922), and the drum mapper can emit any allocated id. Any `sample_id >= 94` is silently clamped to note 95 → `sample_id = 94` in the engine. The bytecode path repeats the clamp (`if note > 95: note = 95`, line 952). The clamp was presumably borrowed from the tone-channel MIDI-note range (0–95), but a DPCM `sample_id` is **not** a MIDI note and has no such ceiling.

## Location
- `nes/emulator_core.py:124` (`"note": min(95, sample_id + 1)`)
- compounded by `exporter/exporter_ca65.py:952-953`

## Evidence
`emulator_core.py:124`; `dpcm_index.json` has 1923 entries; the manager can allocate up to `max_samples` (default 16) distinct ids but those ids still index a table built from the full index — see D-02.

## Impact
Any song using more than ~94 distinct DPCM samples (or, post-D-02-fix, any index id ≥ 94) silently maps every high-id hit to a single wrong sample. Audible drum substitution with no warning.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §2 — DPCM selection is by sample address/length tables, not a 7-bit note; there is no MIDI-note ceiling on a sample index.

## Related
D-02 (id-space mismatch).

## Suggested Fix
Don't reuse the 0–95 MIDI-note clamp for DPCM. Bound `sample_id` by the real packed-sample count (or use a 2-byte index), and route through the correct index id per D-02.

## Completeness Checks
- [ ] **RANGE**: sample index bounded by the real packed-sample count, not the 0–95 note range
- [ ] **CONTRACT**: emulator_core and bytecode exporter agree on the bound
- [ ] **SIBLING**: Same clamp checked in emulator_core and exporter_ca65
- [ ] **TESTS**: A regression test pins this specific fix
