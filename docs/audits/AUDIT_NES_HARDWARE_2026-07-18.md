# NES Hardware Correctness Audit — 2026-07-18

Scope: the boundary where Python numbers become APU register writes —
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, and the serializer `exporter/exporter_ca65.py`. All 10
dimensions swept. Primary task: verify the two files with uncommitted working-tree
changes (`arranger/voice_allocator.py`, `nes/envelope_processor.py`, branch
`fix/audit-167-88-91`) are correct and complete, then re-sweep for regressions/new
defects since `AUDIT_NES_HARDWARE_2026-07-17.md`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 1 (Regression of #309) |

**Headline:** The uncommitted `nes/envelope_processor.py` change correctly and
completely fixes NH-25 (#167) — the pulse control byte now always carries the
length-counter halt bit, matching `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 and
the bytecode engine's existing `ora #$30`. The uncommitted `arranger/voice_allocator.py`
change correctly fixes ARR-08 (#91, arp_speed=0 ZeroDivisionError) at every mutation
site; it has no APU-register surface, so it's out of this audit's primary dimensions
but was reviewed since it's in scope per the task. Full sweep of all 10 dimensions
found no new hardware-range, vector/init, or Triangle-invariant defects. One LOW
finding: `nes/audio_engine.asm` on this branch still carries the orphan
`@cmd_dmc_level` dead-code handler that issue #309 (closed) already fixed — that fix
lives on an unmerged sibling branch (`fix/audit-308-309`, commit `f78c618`) and hasn't
landed on `fix/audit-167-88-91`, so from this branch's working-tree state it's a
regression of a closed issue, not a new defect.

## Verification: uncommitted diff #1 — `nes/envelope_processor.py` (NH-25 / #167)

- **Change**: `get_envelope_control_byte`'s `envelope_bits` changed from `0x10`
  (constant-volume only) to `0x30` (constant-volume `0x10` **+** length-counter
  halt `0x20`).
- **Correctness**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 "Engine Implementation
  Notes" mandates the halt flag (`H=1`) always be set on `$4000/$4004/$4008/$400C`
  writes so the hardware length counter can never cut a note the 60Hz software
  engine is still holding. `envelope_bits = 0x30` sets bit 5 unconditionally,
  matching that requirement.
- **Completeness — call-site check**: `get_envelope_control_byte` has exactly one
  production caller, `nes/emulator_core.py:106` (`compile_channel_to_frames`'s pulse
  branch), which stores the byte as `frame["control"]`. That value flows
  unmodified into `exporter/exporter_ca65.py`'s direct-export `pulse{1,2}_control`
  table (`control = frame_data.get('control', 0)`, :349) and is written straight to
  `$4000`/`$4004` by `play_pulse1`/`play_pulse2` (`:613`, `:667`) — this is exactly
  the path NH-25 flagged as missing the halt bit. The fix closes it with a one-line
  change at the shared source instead of patching each write site.
- **No regression on the macro/bytecode path**: the pattern-compressed exporter
  (`export_tables_with_patterns`, `exporter/exporter_ca65.py:1066`) reads the same
  `frame_data['control']` value but only extracts the duty bits
  (`duty = (control >> 6) & 0x03`) — the envelope/halt bits are discarded and volume
  flows through a separate `vol_seq` macro, so the changed low bits are inert on
  that path. No double-application or byte-format drift.
- **Consistency check**: the direct-export `@silence` label (`exporter_ca65.py:684`,
  `lda #$30`) already wrote the halt bit for the note-off case; before this fix the
  new-note path (`0x10`-only) and the silence path (`0x30`) disagreed on the same
  register. The fix makes both paths consistent.
- **Test verification**: `tests/test_envelope.py`, `tests/test_core.py`, and
  `tests/test_ca65_export.py` (101 tests) pass against the current working tree,
  including an assertion added alongside this change
  (`tests/test_envelope.py`: `self.assertEqual(control_byte & 0x20, 0x20)`).
- **Verdict**: correct, complete. NH-25 (#167) is fixed in this working tree.

## Verification: uncommitted diff #2 — `arranger/voice_allocator.py` (ARR-08 / #91)

Out of the primary NES-hardware dimensions (no APU register touched — `arp_speed`
only gates `state.arp_frame % self.arp_speed` in the arranger's frame-allocation
loop), but reviewed per task scope since the branch groups it with the hardware fix:

- **Change**: `arp_speed` becomes a property; the setter clamps
  `self._arp_speed = max(1, int(value))`.
- **Completeness — mutation-site check**: grepped every `arp_speed` assignment.
  `__init__` (`:77`, `self.arp_speed = arp_speed`) and the standalone
  `allocate_with_arpeggiation` helper (`:483`, `processor.allocator.arp_speed =
  arp_speed`, the exact reassignment path #91 called out as bypassing `__init__`)
  both route through the property setter. No `self._arp_speed` direct write exists
  anywhere else in the file.
- **Test verification**: `tests/test_voice_allocator.py::TestArpSpeedValidation`
  (3 new tests: zero clamped on construction, zero clamped on reassignment, and an
  end-to-end `arrange_for_nes(events, arp_speed=0)` that previously raised
  `ZeroDivisionError`) all pass.
- **Verdict**: correct, complete. Not a hardware-register concern; no cross-effect
  on channel allocation semantics beyond preventing the crash.

## Dimension verification ledger (no finding unless noted)

- **Dim 1 — Pulse duty/vol/timer/sweep:** duty `(duty & 0x03) << 6` and volume
  `& 0x0F` unchanged and correct; constant-volume+halt now `0x30` (see above, fixed).
  Sweep still disabled (`lda #$08`) at both init sites
  (`exporter/exporter_ca65.py:471-473`, `:851-853`). Bytecode phase-reset guard
  (`last_written_hi`) intact (`nes/audio_engine.asm:419-423, 456-460`).
- **Dim 2 — Triangle no-volume/no-duty:** `emulator_core.py`'s non-pulse branch
  (`:107-126`) still never calls `get_envelope_control_byte`, so the fixed
  `envelope_bits` value cannot leak into a triangle frame — the triangle branch
  computes only `pitch`/`volume`/`note`. Direct-export triangle control still
  derived independently (`0x80 | (volume*7)` / `0x00`, `exporter_ca65.py:343-346`).
  No pulse control byte leaks into `$4008`.
- **Dim 3 — Noise:** `get_noise_period` (`pitch_table.py:62-75`) unchanged, single
  source of truth. Noise's own `$400C` control byte is built independently
  (`emulator_core.py:184`, `"control": mode << 6`, then
  `exporter_ca65.py:409` `0x30 | vol`) — already had the halt bit pre-fix and is
  untouched by this diff. `noise_mode` still has no producer — Existing #204/NH-29
  (open, unrelated to this diff — skipped per dedup).
- **Dim 4 — DPCM/DMC:** `dpcm` branch still emits `volume:15` as a trigger gate, not
  a level (`emulator_core.py:226-230`). `$4011` written only at init to zero the DAC
  (`nes/audio_engine.asm:128`, `:263`). See LOW finding below — the orphan
  `@cmd_dmc_level` consumer (`audio_engine.asm:222`, `:259-263`) is still present on
  this branch even though the matching issue is closed elsewhere.
- **Dim 5 — Per-channel pitch tables + 11-bit clamp:** `pitch_table.py` unchanged;
  `generate_note_table` clamp `max(8, min(timer, 0x7FF))` intact. Additive-pitch
  macro reconstruction (`audio_engine.asm`'s `adc temp_pitch`/`temp_pitch_hi`) is
  unaffected by either diff — neither touches the exporter's pitch-offset encoding.
- **Dim 6 — Velocity→4-bit volume:** `max(1, int(15*pow(v/127,1.5)))` unchanged in
  `emulator_core.py`'s two branches. `get_envelope_control_byte`'s volume-combine
  step (`min(15, round((envelope_volume * midi_volume) / 15.0))`) is untouched by
  this diff — only the `envelope_bits` OR'd in afterward changed. Output stays in
  `[0,15]` (`& 0x0F` still applied at the return statement).
- **Dim 7 — Envelope/ADSR:** still inert scaffolding — `effects` hardcoded `None`
  (`emulator_core.py:107`), no producer sets `envelope_type`. The percussion
  divide-by-zero shape in `get_envelope_value` (`envelope_processor.py:69`) is
  untouched by this diff and remains unreachable. Existing #166/NH-24
  (closed-as-documented, unaffected).
- **Dim 8 — 60Hz frame counter:** both init sites still write `lda #$40`/`sta
  $4017`; comments still correctly say "mode 0". Neither diff touches init code.
- **Dim 9 — Register addresses / `$4015`:** re-grepped every `sta $40xx` in
  `nes/audio_engine.asm` — all land in `$4000-$4017`; nothing new introduced by
  either diff (neither file emits assembly or register addresses directly).
- **Dim 10 — Value-range clamping sweep:** no new numeric producer introduced by
  either diff. `envelope_bits = 0x30` is a fixed constant OR'd into a byte that was
  already masked (`duty_bits | envelope_bits | (volume & 0x0F)`) — cannot itself
  push the result out of the `0x00-0xFF` control-byte range. `arp_speed`'s
  `max(1, int(value))` is the new clamp under audit and is verified above.

## Findings

### NH-HW-2026-07-18-1: Orphan `@cmd_dmc_level` handler still present on this branch (dead code)
- **Severity**: LOW
- **Dimension**: 4 (DPCM/DMC)
- **Location**: `nes/audio_engine.asm:221-222` (`cmp #$87` / `beq @cmd_dmc_level`
  dispatch), `:259-263` (`@cmd_dmc_level` handler)
- **Status**: Regression of #309 (closed) — the fix is not present in this branch's
  working tree
- **Description**: The `CMD_DMC_LEVEL` ($87) producer was removed under #72; the
  consumer dispatch branch and handler in `nes/audio_engine.asm` are unreachable
  dead code (`$87` can never appear in the emitted bytecode stream — confirmed by
  `tests/test_ca65_export.py::test_dmc_level_command_path_removed`, still present
  and passing). This exact defect was reported as
  `AUDIT_NES_HARDWARE_2026-07-17.md`'s LOW finding, filed as issue #309, and fixed
  by commit `f78c618` ("fix: remove orphan @cmd_dmc_level handler from the playback
  engine (#309)") — but that commit lives on branch `fix/audit-308-309`
  (`git merge-base --is-ancestor f78c618 HEAD` → not an ancestor), which has not
  been merged into `fix/audit-167-88-91`. `gh issue view 309` confirms the issue is
  `CLOSED`, but the code on *this* branch still has the handler at the same lines
  reported before.
- **Evidence**:
  ```
  $ grep -n "cmd_dmc_level" nes/audio_engine.asm
  222:    beq @cmd_dmc_level
  259:@cmd_dmc_level:
  260:    ; CMD_DMC_LEVEL ($87 followed by 1 parameter byte: 7-bit level)
  $ git merge-base --is-ancestor f78c618 HEAD; echo $?
  1
  ```
- **Impact**: None at runtime (still unreachable — `$87` has no producer). Pure
  maintenance/branch-hygiene: this branch will reintroduce the already-fixed dead
  code into `master` if merged before `fix/audit-308-309` (or a rebase/merge
  picking up its commit), and a reviewer diffing this branch against #309's closed
  state will see it as unresolved.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2-§3 (`$4011` is a one-shot 7-bit
  DAC load at init, not a per-note volume register — there's nothing for a runtime
  "DMC level" command to legitimately do).
- **Related**: #309 (closed, fix on unmerged branch `fix/audit-308-309`). Sibling
  dead-code items #203/NH-28, #204/NH-29, #107/NH-14 remain open and unrelated to
  this branch's diff — not re-derived here (unchanged since the 2026-07-17 audit).
- **Suggested Fix**: Merge or cherry-pick `f78c618` from `fix/audit-308-309` into
  `fix/audit-167-88-91` (or rebase onto a common point that includes it) before this
  branch lands, rather than re-deleting the handler independently and risking a
  conflicting duplicate fix.

---
Suggested next step:
```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-07-18.md
```
