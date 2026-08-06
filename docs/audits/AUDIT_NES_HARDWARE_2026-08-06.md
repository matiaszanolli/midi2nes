# NES Hardware Correctness Audit — 2026-08-06

Scope: the boundary where Python numbers become APU register writes — the four
tone channels (Pulse1/Pulse2/Triangle/Noise) + DPCM. Hot files:
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, `exporter/exporter_ca65.py`. Cross-checked against
`arranger/voice_allocator.py`, `arranger/gm_instruments.py`, and
`arranger/pipeline_integration.py` for the arranger-side noise-mode producer.

Dedup source: `/tmp/audit/issues.json` (19 open issues, `gh issue list` default
scope) + `docs/audits/` history — in particular the previous NES-hardware pass
(`docs/audits/AUDIT_NES-HARDWARE_2026-08-05.md`) and its predecessor
(`docs/audits/AUDIT_NES-HARDWARE_2026-07-19.md`).

Current branch under audit: `fix/issues-136-137-167-202` (HEAD `20f627e`).
Commits merged into `master`/this branch since the last pass:
`24e51d2` (#348/#355/#366/#367/#394 — DMC DAC zero, drum-scan dedupe, partial
DPCM-miss warning), `e639395`→PR #398 (#391 — noise strike re-trigger
detection), `06e1e04`, `90b4582`, `20f627e` (#136/#137/#167/#202 — direct-export
emitter extraction, DPCM `use_advanced` threading; verified byte-for-byte
identical output via the commit's own golden-file diff and this audit's
independent re-read of the full diff).

**One commit exists but was never merged**: `bbcd32b` on the orphan branch
`fix/issue-392-arranger-noise-mode-bit` implements the fix for #392
(`--arranger` noise mode bit). GitHub issue #392 is marked **CLOSED**
(2026-08-06T01:07:17Z) but `gh pr list` shows no PR was ever opened for that
branch and `git merge-base --is-ancestor bbcd32b HEAD` / `...master` both
return false — the fix is not present in the code actually shipping. This is
this audit's headline finding (NH-HW-2026-08-06-1).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total**| **2** |

New: 1 (comment doc-rot) · Existing, prematurely closed / still broken: 1 (#392)

**Headline: the NES-hardware subsystem's actual register-write logic remains
clean — no value-range violation, no Triangle volume/duty leak, no dropped
$4011/$4015/$4017 init, no register written outside $4000–$4017, no dead-code
regression.** All ten dimensions were re-derived from the current working tree
(not copied from the prior report) and every previously-tracked fix
(NH-01..NH-11, NH-15..NH-25, NH-HW-04) still holds, including the length-counter
halt bit (`0x30`), the triangle no-volume/no-duty invariant, the 11-bit timer
clamps floored at 8 on both pitch tables, the `$4017`/`$4015`/sweep init
sequence (now verified present at all three init sites, in the correct
zero-before-enable order), and the bytecode engine's phase-reset guard
(`last_written_hi`).

The one **process-level regression** this pass surfaces is not a code defect
in the traditional sense but a tracking/merge gap with a real user-facing
consequence: **#392 was closed as fixed, but its fix commit lives only on an
unmerged branch — every `--arranger` build shipped from `master` or this
branch still renders hi-hats and cowbell as generic long-mode noise**,
exactly the bug #392 was filed against. Re-filed as still-open (MEDIUM,
unchanged from the original assessment — this is unchanged runtime behavior,
not a new hardware defect).

The one **new LOW** finding is a stale/incorrect inline comment in
`nes/audio_engine.asm` that mislabels a length-counter-*load* write as a
length-counter-*halt* write, in a way that is inconsistent with the correct
terminology used at the analogous site in `exporter/exporter_ca65.py`.

---

## Findings

### NH-HW-2026-08-06-1: `--arranger` still cannot emit the noise mode bit — #392's fix was never merged
- **Severity**: MEDIUM
- **Dimension**: 3 (Noise — period table & mode flag)
- **Location**: `arranger/gm_instruments.py:1191-1198` (`DrumMapping`, no
  `periodic`/mode field), `arranger/voice_allocator.py:37` (`FrameAllocation.
  noise: Optional[Tuple[int, int]]`), `:323-350` (`_allocate_noise`, returns a
  2-tuple `(noise_period, note.velocity)`), `:465-469` (`process_song`'s noise
  frame dict — `"period"`/`"volume"` only, no `"mode"` key),
  `arranger/pipeline_integration.py:329-336` (`mode = data.get('mode', 0) & 1`
  — the key this dict never sets)
- **Status**: Existing: #392 (GitHub state: **CLOSED**, 2026-08-06T01:07:17Z)
  — **regression of the closure, not of the code**: the fix commit
  (`bbcd32b`, "fix: --arranger now sets the noise mode bit for hi-hats and
  cowbell (#392)") exists only on the orphan local/remote branch
  `fix/issue-392-arranger-noise-mode-bit`. `git merge-base --is-ancestor
  bbcd32b HEAD` and `... bbcd32b master` both fail; `gh pr list --repo
  matiaszanolli/midi2nes --state all` has no PR referencing that branch or
  `#392`. The issue was closed without the fix ever landing on a branch that
  ships. Runtime behavior is **unchanged** from the previous audit's
  NH-HW-2026-08-05-1 finding — re-reported under a new ID because the prior
  ID is attached to a now-closed (but factually unresolved) issue.
- **Description**: `docs/APU_NOISE_REFERENCE.md` §6 recommends Mode 1
  (periodic/short-LFSR, "a harsh, metallic buzzing tone with a discernible
  pitch") for hi-hats and cowbells. The legacy front-end implements this
  deterministically: `dpcm_sampler/enhanced_drum_mapper.py`'s
  `_noise_mode_for_note` returns mode 1 for any GM note in
  `METALLIC_NOISE_ROLES` (`hihat_closed`/`hihat_open`/`hihat_pedal`/
  `cowbell`), threading a real `noise_mode` key through
  `nes/emulator_core.py:164` (`e.get('noise_mode', 0) & 1`) into `$400E` bit 7
  via both exporters. The `--arranger` front-end's data model has **no
  equivalent field anywhere**: `DrumMapping` carries only `channel`,
  `play_style`, `priority`, and `noise_period`; `_allocate_noise` returns a
  bare `(period, velocity)` pair; `process_song`'s per-frame noise dict never
  sets a `"mode"` key; `arrange_for_nes`'s noise-conversion step reads
  `data.get('mode', 0) & 1`, whose default (`0`) is therefore the only value
  that can ever reach `$400E` bit 7 on this front-end. Every `--arranger`
  percussion track renders exclusively as long-mode noise, regardless of GM
  drum role — unchanged from the code shape both this and the prior two
  audits examined.
- **Evidence**:
  ```
  $ git log --oneline --all --grep="noise mode" -i
  bbcd32b fix: --arranger now sets the noise mode bit for hi-hats and cowbell (#392)
  $ git branch --contains bbcd32b
    fix/issue-392-arranger-noise-mode-bit
  $ git merge-base --is-ancestor bbcd32b HEAD && echo YES || echo NOT ancestor
  NOT ancestor
  $ git merge-base --is-ancestor bbcd32b master && echo YES || echo NOT ancestor
  NOT ancestor
  $ gh pr list --repo matiaszanolli/midi2nes --state all --limit 100 \
      --json number,headRefName | grep -i 392
  (no output)
  $ gh issue view 392 --json state,closedAt
  {"state":"CLOSED","closedAt":"2026-08-06T01:07:17Z"}
  ```
  ```python
  # arranger/voice_allocator.py:464-469 — live on HEAD, unchanged
  if allocation.noise:
      period, vel = allocation.noise      # still a 2-tuple
      frames["noise"][frame] = {
          "period": period,
          "volume": max(1, vel // 8),
          # no "mode" key
      }
  ```
- **Impact**: Every song run through `--arranger` with GM hi-hats or a cowbell
  still loses the intended metallic/periodic noise timbre on every ROM built
  from the current `master`/this branch, unchanged from the last two audits.
  Not a hardware-range violation (mode 0 is a legal value) and a workaround
  exists (use the legacy/non-arranger pipeline), so severity stays MEDIUM —
  the *impact* hasn't changed, only the tracking state has, and severity is
  about impact not process. Flagging as a distinct finding because the closed
  GitHub issue will otherwise read as resolved to anyone triaging by issue
  state, when the shipped behavior is identical to before #392 was filed.
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §6 (periodic/metallic mode
  recommendation for hi-hat/cowbell-type percussion); §4 (mode bit is `$400E`
  bit 7).
- **Related**: #204/NH-29 (legacy producer this still fails to mirror); #392
  (closed prematurely — recommend reopening or re-filing, and merging
  `fix/issue-392-arranger-noise-mode-bit` / cherry-picking `bbcd32b`);
  `docs/audits/AUDIT_NES-HARDWARE_2026-08-05.md` NH-HW-2026-08-05-1 (same
  underlying gap, first reported there).
- **Suggested Fix**: Merge (or cherry-pick) `bbcd32b` from
  `fix/issue-392-arranger-noise-mode-bit` into `master` via a real PR, then
  reopen #392 until that PR lands and CI/tests confirm it on the mainline
  branch — closing an issue on the strength of a commit that only exists on
  an unmerged branch should be treated as a process gap worth a checklist
  item (e.g. "verify `gh pr list` shows a merged PR before closing").

### NH-HW-2026-08-06-2: Misleading "Length counter halt" comment on a `$4003`/`$4007`/`$400B` length-*load* write
- **Severity**: LOW
- **Dimension**: 1 (Pulse — control byte) / cross-refs Dimension 5 (pitch add)
- **Location**: `nes/audio_engine.asm:411` (`ora #$08      ; Length counter halt`)
- **Status**: NEW
- **Description**: `docs/APU_PULSE_REFERENCE.md` documents `$4003`/`$4007` as
  `llll.lHHH` — **l**: length counter *load* (5 bits, bits 3-7), **H**: timer
  high (3 bits, bits 0-2); there is no halt bit in this register.
  `docs/APU_LENGTH_COUNTER_REFERENCE.md` documents the halt flag (`H`) as
  living in `$4000`/`$4004`/`$4008`/`$400C` bit 5 (bit 7 for `$4008`) — a
  completely different register from the one this line writes. The `ora
  #$08` at `audio_engine.asm:411` sets bit 3 of the value about to be
  written to `$4003` (i.e. the low bit of the 5-bit length-load field, an
  arbitrary reload-table index), not any halt flag; the actual halt bit for
  this channel is set unconditionally elsewhere via the `0x30` control byte
  (`envelope_processor.py`, `envelope_bits = 0x30`, already covered by
  NH-25/#167). Five structurally identical `ora #$08` sites exist in this
  same file (pulse1 fast-path `:402`, pulse2 `:443`/`:452`, triangle
  `:475`/`:485`) and none of the other five carries this comment — only line
  411 mislabels it. The analogous line in `exporter/exporter_ca65.py`'s
  extracted `_emit_pulse1_proc` correctly calls the same operation `; Set
  length reload for new notes`, so the codebase already has the accurate
  wording elsewhere and this one site has drifted from it.
- **Evidence**:
  ```
  # docs/APU_PULSE_REFERENCE.md:34
  | `$4003` | `$4007` | `llll.lHHH`   | **l**: Length counter load<br>**H**: Timer High 3 bits |
  # docs/APU_LENGTH_COUNTER_REFERENCE.md:16-17
  | `$4000` | Pulse 1 | `ssHc.vvvv` | **H**: Halt length counter (Bit 5). ... |
  | `$4004` | Pulse 2 | `ssHc.vvvv` | **H**: Halt length counter (Bit 5). |
  ```
  ```asm
  ; nes/audio_engine.asm:408-411 (pitch-bend branch, pulse1)
      sta $4002
      lda ntsc_period_high, y
      adc temp_pitch_hi
      ora #$08      ; Length counter halt        <-- WRONG: this is $4003's
                                                       length-load field, not a halt bit
  ```
  ```python
  # exporter/exporter_ca65.py — correct wording for the equivalent operation
  '    ora #$08               ; Set length reload for new notes',
  ```
- **Impact**: No functional effect — the byte value and behavior are
  unaffected by the comment. Risk is purely to future maintainers: a reader
  who trusts this comment could conclude removing/changing this `ora` toggles
  the length-counter halt, and could "fix" it by touching the wrong register
  (`$4003` instead of `$4000`), or conversely leave a genuine `$4000`
  halt-flag bug in place because they believe halt is already handled here.
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` (register map table,
  `$4003`/`$4007` `llll.lHHH` layout); `docs/APU_LENGTH_COUNTER_REFERENCE.md`
  §Register Map (halt flag location per channel).
- **Related**: NH-25/#167 (the real halt-bit fix, `0x30` in
  `envelope_processor.py`) — this finding does not affect that fix's
  correctness, only a comment three registers away from it.
- **Suggested Fix**: Reword `nes/audio_engine.asm:411` to match the other
  five `ora #$08` sites and the exporter's own wording, e.g. `; length
  counter load (harmless: halted via $4000/$08=0x30 control byte)`.

---

## Dimensions verified clean (re-confirmed, no finding)

- **Dim 1 (Pulse duty/vol/timer/sweep)**: duty masked `(duty & 0x03) << 6`;
  `envelope_bits = 0x30` (const-vol + halt) unchanged in
  `nes/envelope_processor.py:174`; volume `& 0x0F`; sweep disabled at all
  three init sites (`reset`, `init_music`, `audio_engine.asm`) with `$08`,
  never re-enabled; bytecode `$4003`/`$4007` phase-reset guard
  (`last_written_hi`) unchanged and still gated correctly. `PULSE_DUTY_CYCLES`
  confirmed still absent from the codebase. See NH-HW-2026-08-06-2 for a
  comment-only nit adjacent to this dimension.
- **Dim 2 (Triangle invariant)**: `process_all_tracks` still routes triangle
  through the non-pulse branch (`default_duty=None`, `nes/emulator_core.py`);
  the newly-extracted `_emit_pulse_or_triangle_table` in
  `exporter/exporter_ca65.py` (from the #136 refactor) reproduces the exact
  same triangle-control derivation byte-for-byte (`TRIANGLE_CONTROL_ON` =
  `0xFF` when audible, `0x00` when silent) — confirmed via full diff read of
  commit `20f627e`, which shows the removed inline code and the added method
  body are textually identical modulo indentation. No `$30`-style pulse byte
  leaks into `$4008` on any path.
- **Dim 3 (Noise, legacy front-end)**: `get_noise_period` remains the single
  source of truth; the 6-frame software decay ramp
  (`NOISE_DECAY_FRAMES`/`noise_strike_decay_volume`) unchanged; the mode bit
  is still live end-to-end on the **legacy** front-end only
  (`enhanced_drum_mapper._noise_mode_for_note` → `emulator_core.py:164` →
  exporter `$400E` bit 7). The re-trigger-detection fix for #391
  (`arranger/voice_allocator.py:519-522`, requiring matching raw volume in
  addition to period/contiguity before extending a noise strike) is
  confirmed merged and present, and preserves the `"mode"`/other dict keys
  verbatim through `entry = dict(noise_frames[start + offset])` — so *if*
  #392's fix is ever merged, the decay helper will not need further changes
  to carry the mode key through. The `--arranger`-side mode-bit gap itself is
  NH-HW-2026-08-06-1 above.
- **Dim 4 (DPCM/DMC)**: `dpcm` branch still emits `volume:15` as a trigger
  gate, not a level. **#348 fix independently re-verified as fully merged and
  correctly ordered**: all three init sites (`exporter_ca65.py`'s standalone
  `reset` at `:784-792`, non-standalone `init_music` at `:944-953`, and
  `nes/audio_engine.asm`'s `audio_init` at `:131-146`) now zero `$4011`
  *before* `$4015` re-enables channels — verified read-through of all three
  in program order, not just presence-grep. The `@cmd_dmc_level` handler and
  `CMD_DMC_LEVEL`/`$87` opcode remain fully absent from both engine and
  exporter (consistent with `tests/test_ca65_export.py::
  test_dmc_level_command_path_removed`, re-run and passing). Sample residency
  (`dpcm_packer.py`, 64-byte alignment from `$C000`) unchanged.
- **Dim 5 (Per-channel pitch tables + 11-bit clamp)**: `generate_note_table`
  still parameterized by `divider` (pulse `/16`, triangle `/32`); every table
  entry floored at 8, clamped to `0x7FF`; `get_channel_pitch` and
  `midi_note_to_timer_value` both still branch on `channel == 'triangle'`.
  The newly-extracted `_emit_pulse_or_triangle_table` re-asserts the
  audible-range floor (`pitch = max(8, min(pitch, 0x07FF))` when `pitch` is
  nonzero) identically to the pre-refactor inline code — confirmed via the
  commit diff. The unclamped pitch-macro `adc`/`adc` in
  `nes/audio_engine.asm` is unchanged; re-verified the same worst-case
  producer (pulse notes ~96-108 differenced against a base clamped to 95)
  stays comfortably inside `8..0x7FF` — no new producer widens this delta.
- **Dim 6 (Velocity→volume)**: `velocity_to_volume`
  (`max(1, int(15 * pow(v/127, 1.5)))`) unchanged, clamped 0-15; envelope
  combine step (`min(15, round((envelope_volume * midi_volume)/15.0))`)
  unchanged and still cannot reach 16.
- **Dim 7 (Envelope)**: `compile_channel_to_frames` still hardcodes
  `effects=None`; no producer outside `tests/` sets `envelope_type`; constant
  volume flag (`0x30`) unconditional. The percussion divide-by-zero shape in
  `get_envelope_value` remains unreachable (still no `envelope_type=
  "percussion"` producer).
- **Dim 8 (60Hz/frame counter)**: all three init sites write `$4017 = $40`
  (4-step mode 0, IRQ inhibit) with comments correctly reading "mode 0" —
  re-verified against `docs/APU_FRAME_COUNTER_REFERENCE.md` §2-§3; frame
  model iterates integer frames throughout.
- **Dim 9 (Register addresses / $4015)**: every `sta $40xx` in both
  `exporter/exporter_ca65.py` and `nes/audio_engine.asm` programmatically
  extracted and diffed against the `$4000-$4017` window — identical address
  sets on both engines (`$4000-$4008,$400A-$400C,$400E,$400F,$4010-$4013,
  $4015,$4017`), all in range, all on the correct channel's register. Init
  enables `$4015 = $0F`, DMC bit 4 only set to `$1F` on sample trigger.
- **Dim 10 (Value-range clamping)**: timers floored-8/clamped-`$7FF`;
  volume `& 0x0F` at every write site; duty structurally 0-3 by construction;
  noise index `& 0x0F`; DMC "level" remains a trigger gate. The unclamped
  pitch-macro add re-verified in-range (Dim 5); the unclamped arp add
  (`clc; lda current_note,x; adc temp_arp`) still fed only the neutral
  `_encode_macro_offset(0)` — no live nonzero `arp` producer exists anywhere
  in the pipeline (`grep -rn "'arp'" exporter/ arranger/ nes/ tracker/`
  outside the always-zero encode call returns no hits) — still HIGH the
  moment a nonzero producer appears without a guard, unchanged from prior
  audits.

---

## Notes on scope boundaries

- The `#136` direct-export emitter extraction (`exporter/exporter_ca65.py`,
  commit `20f627e`) touches every hot file this audit cares about, so it
  received a full line-by-line diff read (not a summary trust) — confirmed
  the removed and added code are byte-identical modulo method boundaries,
  consistent with the commit's own claim of a golden-file-diff-verified,
  behavior-preserving refactor. `tests/test_ca65_export.py`,
  `tests/test_core.py`, and `tests/test_envelope.py` (94 tests) all pass
  against the current tree.
- The mapper auto-select/capacity work in prior commits and `run_full_pipeline`
  splitting (#406, still open) are out of this audit's territory — left to
  the mapper/pipeline audits.
- NH-HW-2026-08-06-1 sits on the same Dimension-3/arranger boundary as its
  predecessor NH-HW-2026-08-05-1 — filed here again because the underlying
  runtime behavior (not just the GitHub bookkeeping) is this skill's concern,
  and the closed-issue state is itself worth flagging so it isn't mistaken
  for done. Consider cross-filing under the `arranger` label as well as
  `nes-hardware`.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-08-06.md
```
