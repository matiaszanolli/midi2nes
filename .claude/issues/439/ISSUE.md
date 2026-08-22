# EXP-2026-08-21-1: Bytecode path retriggers held notes at every 32-frame boundary (forced $4003/$4007 phase-reset + macro restart)

GitHub: https://github.com/matiaszanolli/midi2nes/issues/439

**Severity:** MEDIUM · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-08-21.md

## Description
An event with `dur > 32` cannot be expressed as one note in the bytecode format, so the exporter emits repeated `($6X, note)` pairs. The engine has no concept of "same note continued": every note byte is a full onset — macro step indices reset to 0 and `last_written_hi` is set to `$FF` so the next `$4003`/`$4007` write always happens. Writing `$4003`/`$4007` restarts the pulse duty-sequencer phase (the engine's own #161/NH-18 comment: "otherwise a held note re-clicks every frame"), so a held pulse note gets an audible re-click every 32 frames (~533 ms). The macro restart additionally replays each macro's first entries: inaudible today only because every live producer emits per-event-constant volume/pitch (the `envelope_type` scaffolding is inert, #166), but it silently corrupts the exact per-frame vibrato/slide/envelope feature `docs/MACRO_USAGE_GUIDE.md` §1/§3 advertises the moment any producer emits one — frames 33+ of a bent note would replay offsets 0-27 instead of 32-59. The direct path (`--no-patterns`) compares against `last_pulseN_note` and sustains without any register rewrite, so the two export paths audibly differ for the same frames input.

## Location
`exporter/exporter_ca65.py:1428-1434` (the `while rem_dur > 0: write_dur = min(rem_dur, 32)` split re-emits the same note byte per chunk); `nes/audio_engine.asm:445-465` (`@is_note` unconditionally resets `macro_steps_*` and forces `last_written_hi = $FF`, defeating the #161/NH-18 same-value write suppression at each chunk boundary)

## Spec ref
`docs/AUDIO_BYTECODE_SPEC.md` §3 Length Commands ($60–$7F cap at 32 frames; no tie/continuation opcode exists) and §3 Note Range ("Triggers the current instrument and resets all macro pointers"); consumer `nes/audio_engine.asm:445-465` (`@is_note`)

## Evidence
`exporter_ca65.py:1432` emits `.byte ${(write_dur-1)+0x60:02X}, ${note:02X}` once per 32-frame chunk of a single `current_event`; `audio_engine.asm:459-460` (`lda #$FF / sta last_written_hi, x`) then `:569-572` (`cmp last_written_hi+0 / beq @p1_skip_hi / sta $4003`) — with the sentinel, the `beq` never takes on the chunk-boundary frame, so `$4003` is written with an *unchanged* period, purely resetting phase.

## Impact
Default pipeline (`python main.py song.mid`) — every pulse1/pulse2 note held longer than 32 frames clicks periodically mid-note. Triangle/noise unaffected (no phase-reset semantics on their register writes). Workaround exists (`--no-patterns`), which keeps this MEDIUM rather than HIGH.

## Related
#161/NH-18 (the sustain-suppression this defeats at boundaries); #166 (inert envelope scaffolding is why macro-restart is currently inaudible); EXP-2026-08-21-5 (spec gap: no continuation opcode documented or implemented — not separately filed, see AUDIT_EXPORTERS_2026-08-21.md).

## Suggested Fix
Add a "tie/continue" encoding (e.g. emit only a Length command for continuation chunks, or a dedicated `CMD_TIE`) implemented on both sides simultaneously; short of a format change, `@is_note` could skip macro-reset and the `last_written_hi` sentinel when the incoming note equals `current_note, x` (making same-note bytes idempotent — semantically exactly what the exporter's split means).

## Completeness Checks
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **SIBLING**: Same pattern checked in related files (triangle/noise register-write paths already confirmed unaffected — no phase-reset semantics there)
- [ ] **TESTS**: A regression test pins this specific fix (e.g. assert no `$4003`/`$4007` rewrite mid-sustain for a >32-frame held note)
- [ ] **DOC**: `docs/AUDIO_BYTECODE_SPEC.md` §3 documents the tie/continuation behavior once fixed
