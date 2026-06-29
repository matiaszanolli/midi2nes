**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-29.md

## Description
Each direct-export (`export_direct_frames`, reachable via `--no-patterns`) tone-channel proc uses the same idiom:
```asm
cmp last_pulse1_note
beq @sustain              ; same note -> hold (Z used correctly here)
sta last_pulse1_note
beq @silence              ; "if note is 0, silence"  <-- DEAD
```
On a 6502, `STA` does **not** modify the Z flag. Control only reaches the `sta` when the preceding `cmp last_*_note` was *not* equal (otherwise the first `beq @sustain` is taken), so Z is **clear**. The second `beq @silence` therefore tests the stale `cmp` result and is **never** taken. On a note→silence transition the proc falls through and writes the silent frame's zero-valued `control`/`timer` tables to the channel registers, and the explicit `@silence` block never executes.

This is the same root-cause 6502 flag bug as #66 (D-03) in `play_dpcm`, replicated across the four tone channels.

## Location
- `exporter/exporter_ca65.py:419-423` (pulse1), `490-494` (pulse2), `559-563` (triangle), `625-628` (noise)
- Dead `@silence` labels at `461-465`, `532-535`, `601-604`, `653-655`.

## Evidence
Confirmed at HEAD: `sta last_pulse1_note` (line 420) → `beq @silence` (423); `sta last_pulse2_note` (491) → `beq @silence` (494); `sta last_triangle_note` (560) → `beq @silence` (563); `sta last_noise_note` (627) → `beq @silence` (628). For pulse the fallthrough writes `$4000=$00` (volume 0, *no* constant-volume flag) + `$4003` with `ora #$08` (length reload, phase reset); for triangle `$4008=$00`; for noise `$400C=$00` + `$400F` with `ora #$08`. The intended clean `$30` (constant-volume-0) write at the dead `@silence` labels is skipped.

## Impact
Channels still end up effectively silent because the zero data happens to mute them (pulse timer `$00` is `t<8`; triangle linear-counter `$00` halts; noise volume 0), so this is **not** a stuck-note bug. But every note-off **reloads the length counter and resets the pulse phase** (the `ora #$08` writes), reintroducing exactly the popping the `@sustain` short-circuit was added to avoid. Direct-export (`--no-patterns`) ROMs only; workaround: use the default pattern path.

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §2 (writing `$4003` restarts the sequencer → audible click), §5 cond. 4 (`t < 8` silences); `docs/APU_TRIANGLE_REFERENCE.md` §5 (linear-counter halt silence); `docs/APU_NOISE_REFERENCE.md` §2 (`$400C --lc.vvvv` constant-volume silence).

## Suggested Fix
Test the loaded note for zero with an instruction that sets Z (re-`lda`/`cmp #0`, or `tax`/`tay` on the note before `sta`) so `beq @silence` branches on `note == 0`. Then the existing `@silence` blocks run and the phase-reset is avoided. Fix all four channels (and align with the #66 fix in `play_dpcm`).

## Related
#66 (D-03, identical 6502 flag bug in `play_dpcm`, HIGH).

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same flag bug fixed across all four tone channels and `play_dpcm` (#66)
- [ ] **TESTS**: A regression test pins this specific fix (note→silence path)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
