# NH-HW-2026-08-21-5: Direct-export last_*_note state is never initialized — power-on RAM garbage can swallow a channel's first note or first DPCM trigger

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/432
**Severity:** MEDIUM
**Domain:** nes-hardware
**Source report:** docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
**Filed:** 2026-08-21

## Location
- `exporter/exporter_ca65.py:666-671` (BSS: `last_pulse1_note`/`last_pulse2_note`/
  `last_triangle_note`/`last_dpcm_note`, no initializer)
- `exporter/exporter_ca65.py:764-810` (standalone `reset` — no write to them)
- `exporter/exporter_ca65.py:940-959` (non-standalone `init_music` — likewise)
- `nes/project_builder.py:441-463` (`main.asm` reset template — no RAM-clear loop)

## Description
Direct-export playback gates register writes on `cmp last_<ch>_note` / `beq @sustain`. Nothing
clears RAM or seeds these four bytes, so on real hardware they hold power-on garbage. If a
channel's garbage byte equals the first note's value, that channel stays silent until the next
note change (or the first DPCM trigger never fires). Emulators that zero RAM mask this.

## Impact
`--no-patterns` / direct-export ROMs on real hardware: per boot, per channel, a ~1/256 chance the
first note (or first drum) is skipped. Low-probability, silent, hardware-only — MEDIUM
defense-in-depth gap.

## Suggested Fix
Seed all four `last_*_note` bytes with `$FF`, mirroring `audio_engine.asm`'s `last_written_hi`
sentinel init, either via a RAM-clear loop or explicit 4-byte init in `reset`/`init_music`.

## Related
#107/NH-14, #161/NH-18.

## Dedup check
Searched fresh `gh issue list --state open` snapshot (6 open issues at filing time) and audit
history — no match found.
