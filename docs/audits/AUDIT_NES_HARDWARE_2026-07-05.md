# NES Hardware Correctness Audit — 2026-07-05 (full pass, all 10 dimensions)

Audit of the boundary where Python numeric values become APU register writes, at
HEAD `bcc0395` (branch `fix/regression-rom-validation-128-129`, identical to
`master`/`origin/master` at this commit). Hot files: `nes/emulator_core.py`,
`nes/pitch_table.py`, `nes/envelope_processor.py`, `exporter/exporter_ca65.py`,
`nes/audio_engine.asm`, plus `arranger/voice_allocator.py` /
`arranger/pipeline_integration.py` as the second producer of the same control bytes.

**Relationship to the prior pass.** `docs/audits/AUDIT_NES-HARDWARE_2026-07-05.md`
(note the hyphen in the filename — a distinct report generated earlier today at the
now-superseded HEAD `a7de0d4`) already covers most of this ground and found one NEW
MEDIUM (NH-30). Three merges have landed since `a7de0d4`: `26fc30a` (#165/#166
cleanup — NH-23 dead tables actually removed, NH-24 re-documented as intentionally
inert, not changed), `f5905dd`+`d098dee` (patterns-only), and `2823594`+`a6854d1`
(import cleanup, verified no logic changes to `nes/`/`exporter/`/`mappers/`/
`arranger/`). None of these change any APU-register-write path. This pass re-verifies
the full open set at current HEAD, corrects the record on three issues GitHub shows
CLOSED whose fixes never actually reached `master`, and answers the specific question
of whether `exporter/exporter_ca65.py`'s new `_emit_safe_beq` helper (from PR #270,
`fix/dpcm-oversized-id-guard-and-mmc1-bank-switching-254-255`, commit `8c2f8aa` —
already merged into `master` via `d25df0c`, contrary to this task's framing of it as
"pushed but not merged") introduces any new register-write correctness bug.

**Dedup sources:** `/tmp/audit/issues.json` (33 open issues, default `gh issue list`
per protocol), cross-checked against `gh issue view` for specific closed issues where
code inspection raised doubt, and every `docs/audits/AUDIT_*NES*HARDWARE*.md` /
`AUDIT_ARRANGER_*.md` report on disk.

## Summary

| Severity | Count (NEW) |
|----------|------:|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 0 |
| LOW      | 2 |
| **Total NEW** | **3** |

Plus 6 existing open findings re-verified unchanged (not re-counted): #107/NH-14,
#166/NH-24, #167/NH-25, #203/NH-28, #204/NH-29, #268/NH-30.

### Highest-risk hardware divergence

**NH-31 (HIGH, this report) — a "fixed" bug is back in production because its fix
branch was never merged.** GitHub shows issue **#163 (NH-21)** — the exporter's
`_compress_macro` emitting an `$FE` macro-loop control byte the live
`EVAL_MACRO` bytecode evaluator cannot decode — **CLOSED** on 2026-07-03 by commit
`c8ae178` on branch `fix/macro-loop-control-byte-mismatch-frame-counter-comment-163-164`.
That commit is **not an ancestor of current HEAD** (`git merge-base --is-ancestor
c8ae178 HEAD` fails) — the fix exists only on its unmerged feature branch. The
exact bug the issue describes is verified still live in `master`: `_compress_macro`
(`exporter/exporter_ca65.py:936-969`) still considers `$FE` loop compression and
picks it whenever shorter, and `EVAL_MACRO` (`nes/audio_engine.asm:58-88`) still
only branches on `cmp #$FF` (`:72`) — a merged run of same-note frames with
alternating volumes (a 60Hz drum-roll/tremolo re-strike, not a contrived input)
still makes loop compression win and emits an undecodable `$FE` into a channel's
macro stream, which the engine reads as ordinary data, silently playing the wrong
volume/pitch/duty for the rest of that instrument's macro. Two smaller sibling
issues share the same fate (**#41/NH-11**, **#164/NH-22** — see NH-32/NH-33 below):
their fix branches (`32dc4b42`, and `c8ae178` again for #164) are likewise not
merged, so GitHub's closed/open state currently **overstates** how much of the
NES-hardware backlog is actually fixed in shippable code. This is a process
finding as much as a hardware one: **anyone using the issue tracker's CLOSED state
to decide what still needs auditing will silently skip live bugs.**

Everything else audited (Pulse/Triangle/Noise/DPCM register correctness, pitch
tables, velocity curve, envelope, 60Hz init, `$4015`/`$4017`) matches the prior
pass's clean bill of health, and the newly-merged MMC1 bank-switching control-flow
rewrite (`_emit_safe_beq`) was independently verified to introduce **no** new
register-write bug (see the dedicated section below) — it mechanically preserves
`beq`'s semantics via `bne`+`jmp` and only activates when a mapper's
`direct_export_bank_size()` is not `None` (currently MMC1 only), with the code
segment itself pinned to the mapper's fixed (non-bank-switched) PRG window
(`mappers/mmc1.py:102`, `CODE: load = PRGFIXED`), so the jump targets it emits are
never in a bank that could be switched out from under the running code.

---

## Findings

### NH-31: `$FE` macro-loop control byte is undecodable by the live engine — closed issue's fix was never merged
- **Severity**: HIGH
- **Dimension**: 1 (Pulse/Triangle/Noise macro-driven volume/pitch/duty — cross-channel; DPCM unaffected) / bytecode contract
- **Location**: `exporter/exporter_ca65.py:936-969` (`_compress_macro`, loop-compression branch, `MACRO_CTRL_LOOP = 0xFE` at `:64`); `nes/audio_engine.asm:58-88` (`EVAL_MACRO`, single `cmp #$FF` at `:72`)
- **Status**: Regression of #163 (issue is CLOSED, `stateReason: COMPLETED`, `closedAt: 2026-07-03T23:01:59Z`; its fix commit `c8ae1789cd09e43550b3359f3a38c93c3621ae18` on branch `fix/macro-loop-control-byte-mismatch-frame-counter-comment-163-164` is confirmed **not** an ancestor of current HEAD `bcc0395` via `git merge-base --is-ancestor`)
- **Description**: `docs/AUDIO_BYTECODE_SPEC.md` §2.3 defines two macro-stream control bytes: `$FF` (sustain/end) and `$FE, <offset>` (loop). `_compress_macro` implements and picks whichever is shorter for a given per-frame value sequence (volume, pitch-offset, or duty). The shipped `EVAL_MACRO` inline evaluator only recognizes `$FF` (`cmp #$FF` / `bne @not_end`) — there is no `$FE` branch at all. When the evaluator reads a stray `$FE` it falls into `@not_end`, treats `$FE` as an ordinary data byte to write to the channel parameter, then consumes the loop's `loop_start` operand byte as if it were the *next frame's* value, permanently desyncing that channel's macro stream from its intended sequence for the rest of playback. On typical constant-per-note macros, sustain compression (`[v, $FF]`) is always shorter than loop compression (`[v, $FE, offset]`) for a 2-value run, so `$FE` doesn't normally get chosen — but a merged run of same-note frames with an alternating-value pattern (the shape a 60Hz drum-roll re-strike or tremolo effect produces) makes loop compression win on size, emitting the byte the engine cannot read.
- **Evidence**: `_compress_macro`'s loop-compression loop (`exporter/exporter_ca65.py:938-967`) has no guard preventing it from ever being selected as `best_compression`; `EVAL_MACRO`'s only end-of-macro test is `cmp #$FF` / `bne @not_end` (`nes/audio_engine.asm:72-73`), with `@not_end` unconditionally treating the byte as data (`:83-85`). The already-merged fix for the *same* class of bug at the DPCM proc (`play_dpcm`, `exporter/exporter_ca65.py:784-793`, "STA does not affect Z ... re-test the note", `#66`) shows the team has fixed this shape of bug elsewhere in this file — but that discipline never reached the macro evaluator itself, and the branch that was supposed to fix *this* instance (`c8ae178`) never merged.
- **Impact**: On any exported song (patterns/MMC3-bytecode path only — `export_direct_frames` doesn't use macros) that contains a merged run of alternating same-note volume/pitch/duty values long enough for loop compression to beat sustain compression, that channel's macro stream desyncs from the byte the exporter intended forward for the rest of the instrument event — audibly wrong volume/pitch/duty, silently, with no build-time or runtime error. Blast radius: any tone channel driven by the MMC3 macro-bytecode exporter (`export_tables_with_patterns` with non-empty `patterns`), which is the pipeline's **default** path (patterns are only skipped with `--no-patterns`).
- **Related**: #66 (the DPCM re-test fix that shows the pattern being fixed elsewhere), #83 (bytecode spec doc-rot), original issue #163 body (severity there logged as MEDIUM; this audit assesses HIGH — see Suggested Fix note on why).
- **Hardware ref**: `docs/AUDIO_BYTECODE_SPEC.md` §2.3 (Macros: `$FF` end/sustain, `$FE, <offset>` loop — the contract the exporter and engine must agree on); `docs/APU_PULSE_REFERENCE.md` §1 (what a corrupted volume/duty nibble actually does at `$4000`/`$4004` once the desynced byte reaches a register write).
- **Suggested Fix**: Either implement `$FE` handling in `EVAL_MACRO` (mirror the already-written but unused `process_channel_macros` loop logic, or the DPCM proc's re-test pattern) or delete loop compression from `_compress_macro` entirely so the exporter can never emit a byte the engine can't decode — the unmerged branch `fix/macro-loop-control-byte-mismatch-frame-counter-comment-163-164` already contains a complete, tested version of the latter; it just needs to be merged. Independent of which fix direction is chosen, re-assessed severity here is HIGH (not the original MEDIUM) because this is a silent producer/consumer contract break on the pipeline's *default* export path, not a workaround-able cosmetic issue — matching the severity table's "pipeline stage hands the next stage data that means something else" HIGH-floor rule.

---

### NH-32: `$4017` init comment still says "mode 1" for the mode-0 byte `$40` — closed issue's fix was never merged
- **Severity**: LOW
- **Dimension**: 8 (60Hz frame timing & frame counter init)
- **Location**: `exporter/exporter_ca65.py:834`, `nes/audio_engine.asm:131`
- **Status**: Regression of #164 (CLOSED `2026-07-03T23:02:00Z`, same unmerged fix commit `c8ae178` as NH-31 above)
- **Description**: `$4017 = $40` is `%01000000` — Mode bit (bit 7) clear = 4-step sequencer mode ("mode 0"), Interrupt Inhibit (bit 6) set = frame IRQ disabled (`docs/APU_FRAME_COUNTER_REFERENCE.md` §3 Sequencer Modes). The byte value written is correct. Both live comments still read "Frame counter mode 1, disable frame IRQ" (`init_music`'s comment, and `audio_engine.asm`'s), which is off-by-one against the actual mode being selected. `nes/mmc3_init.asm`'s copy of this comment was previously scoped out as the sole site by an earlier report; this pass confirms it's not — the same wrong "mode 1" text is present in the two *live* init sites too.
- **Evidence**: `exporter/exporter_ca65.py:834`: `'    sta $4017  ; Frame counter mode 1, disable frame IRQ (NES_APU_REFERENCE 3.2)'`; `nes/audio_engine.asm:131`: `; $4017 = $40: frame counter mode 1, disable frame IRQ so it cannot`.
- **Impact**: Comment-only; no runtime effect, since the emitted byte (`$40`) is correct. A future maintainer reading the comment and "fixing" the byte to match a mistaken "mode 1" belief (`$C0` or `$80`) would introduce a real bug (5-step mode changes clocking and, depending on IRQ inhibit, can misbehave), so this is a real if currently-latent risk, not pure cosmetics.
- **Related**: NH-31 above (same unmerged fix commit).
- **Hardware ref**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §3 Sequencer Modes (mode 0 = 4-step, selected by bit 7 = 0).
- **Suggested Fix**: Correct both comments to "mode 0 (4-step)"; the unmerged branch already has this fix, merge it.

---

### NH-33: `note_to_timer`'s dead 24–95 range guard still contradicts `CHANNEL_RANGES` — closed issue's fix was never merged
- **Severity**: LOW (dead code — no production caller)
- **Dimension**: 5 (per-channel pitch-table correctness + 11-bit clamp)
- **Location**: `nes/pitch_table.py:133-139`
- **Status**: Regression of #41 (CLOSED `2026-07-04T22:13:54Z`; fix commit `32dc4b427923...` on branch `fix/pitch-timer-clamp-and-dpcm-length-reg-rounding-41-75` confirmed not an ancestor of current HEAD)
- **Description**: `PitchProcessor.note_to_timer` raises `ValueError` for any MIDI note outside 24–95, but `CHANNEL_RANGES["pulse1"]` (the range this same class treats as valid everywhere else, e.g. in `get_channel_pitch`) is 24–108. A pulse note of 96–108 is legal per the channel range table but would raise if routed through this specific method. Grep confirms (as in the prior pass) `note_to_timer` has **no production caller** — only `tests/test_pitch_table_integration.py` calls it directly — so this is a live contradiction in dead code, not a reachable production bug today.
- **Evidence**: `if midi_note < 24 or midi_note >= 96: raise ValueError(...)` vs. `channel_ranges["pulse1"] = (24, 108)` used elsewhere in the same module.
- **Impact**: None today (unreachable from any pipeline stage). Becomes a real bug the moment any future producer routes a legitimate 96–108 pulse note through this method instead of `get_channel_pitch`.
- **Related**: none beyond #41 itself.
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §4 Engine Implementation Notes (per-channel valid ranges).
- **Suggested Fix**: Merge the existing unmerged fix (clamp to `channel_ranges["pulse1"]` instead of raising for the narrower 24-95 window), or delete the dead method if nothing is ever expected to call it.

---

## Special-ask verification: does `_emit_safe_beq` introduce a new register-write bug?

**Verified: no.** `_emit_safe_beq` (`exporter/exporter_ca65.py:158-186`, from the now-merged
PR #270/`8c2f8aa`) is called at 9 sites: pulse1 `@sustain`/`@silence`, pulse2
`@sustain`/`@silence`, triangle `@sustain`/`@silence`, noise `@silence`, and DPCM
`@done` (twice, for the unchanged-note and rest cases). When `bank_size is None`
(every mapper except MMC1's direct-export path) it emits the original single `beq
target` byte-for-byte unchanged. When `bank_size` is set, it emits `bne
@skip_X` / `jmp target` / `@skip_X:` — this is a semantically exact translation of
`beq`'s branch-iff-Z=1 behavior into an unconditional jump reachable from any
distance, and neither `bne` nor `jmp` touch the processor flags, so:
- At every one of the 9 sites, the `cmp`/`lda` that sets the flag being tested is
  the instruction immediately preceding the `_emit_safe_beq` call in every case
  (no bank-switch code, which is only inserted by `_emit_table_read_lines` before
  a *different* table read, is ever interleaved between the flag-setting
  instruction and the branch that consumes it).
- The pre-existing "dead `@silence` beq" bug on pulse1/pulse2/triangle
  (**#107/NH-14**, open, re-verified — `sta last_pulseN_note` doesn't clear the
  carried-over Z flag from the earlier `cmp`, so the second `beq @silence` never
  fires) is reproduced **identically** in both the plain-`beq` and
  `bne`+`jmp` forms — `_emit_safe_beq` neither fixes nor worsens it, since it's a
  content-preserving translation of whatever branch condition it's given.
  Symmetrically, DPCM's already-correct explicit `cmp #0` re-test (`:788-790`,
  citing `#66`) is preserved correctly through the same translation.
- The jump targets (`@sustain`/`@silence`/`@done`) are labels within the same
  `.proc` as the branch, and that `.proc`'s `CODE` segment is declared
  `load = PRGFIXED` in `mappers/mmc1.py:102` (the mapper whose
  `direct_export_bank_size()` is the only non-`None` value, `mappers/mmc1.py:163-166`)
  — i.e. the code doing the bank-switching is never itself in the bank being
  switched, so a `jmp` across a bank-switch boundary can't land on now-unmapped
  memory.
- Generated `@skip_*` labels (`p1_sustain`, `p1_silence`, `p2_sustain`,
  `p2_silence`, `tri_sustain`, `tri_silence`, `noise_silence`, `dpcm_unchanged`,
  `dpcm_rest`) are all distinct — no label-collision risk that ca65 would catch at
  assemble time anyway.

No new finding filed for this — it is a correct, minimal, semantics-preserving
control-flow rewrite scoped precisely to the one mapper (MMC1) that needs it.

---

## Dimension coverage notes (re-verified clean at HEAD, no new findings beyond NH-31..33 above)

- **Dim 1** (Pulse): duty `(d & 0x03) << 6`, constant-volume `0x10` (bit 4), 4-bit
  volume mask all correct (`nes/envelope_processor.py:131-137`). Sweep disabled
  (`$08`) at both live init sites (`exporter/exporter_ca65.py:458-459,838-839`).
  `#167/NH-25` (length-counter halt bit never set on direct-export pulse control
  byte) still holds, open, unchanged.
- **Dim 2** (Triangle): non-pulse `process_all_tracks` branch carries no
  duty/volume control byte; direct-export derives `$4008` independently
  (`0x80 | vol*7`, or `0x00` when silent) — no pulse-style byte leaks in; `@silence_tri`
  in the bytecode engine writes `$80` (linear-counter halt, `docs/APU_TRIANGLE_REFERENCE.md`
  §5 Method 1).
- **Dim 3** (Noise): `get_noise_period`'s clamp+invert and `PitchProcessor._get_noise_period`'s
  delegation remain single-sourced; `noise_mode` reaches `$400E` bit 7 correctly
  but has no producer (`#204/NH-29`, holds); software decay ramp
  (`NOISE_DECAY_FRAMES = 6`) unchanged.
- **Dim 4** (DPCM): `$4011` zeroed only at the two live init sites; dense
  `sample_id` remap in `nes/emulator_core.py` (the mechanism the just-merged
  `8c2f8aa` DPCM-guard removal now solely relies on, per this task's framing)
  confirmed present and is the reason removing the old 254-ceiling guard in
  `dpcm_sampler/enhanced_drum_mapper.py` is safe; `@cmd_dmc_level` still has no
  producer (dead, `#165` cleanup already covered the sibling dead tables).
- **Dim 5/10** (Pitch tables / clamping): pulse `/16` vs. triangle `/32` tables
  distinct and single-sourced; both `max(8, min(t, 0x7FF))`.
  `midi_note_to_timer_value`'s 24–119 clamp holds. `note_to_timer`'s dead
  24–95 contradiction is NH-33 above. Engine pitch-macro/arpeggio adds remain
  structurally unclamped but inert (no producer of nonzero `pitch_seq`/`arp` —
  confirmed again post the #166 cleanup, which removed the *separate* dead
  `arpeggio`/`arp` key duplication without wiring up a real producer).
- **Dim 6** (Velocity→volume): legacy `emulator_core.py` path
  (`max(1, int(15 * math.pow(velocity/127.0, 1.5)))`) and
  `get_envelope_control_byte`'s combination step both stay in `0..15`.
  `#268/NH-30` (arranger `vel // 8` floors soft pulse notes to volume 0 with
  no `max(1, …)`) still open, re-verified present (now at
  `arranger/voice_allocator.py:412,420,435` — three call sites, line numbers
  shifted since the prior pass but the bug and its un-guarded form are
  unchanged).
- **Dim 7** (Envelope/ADSR): constant-volume bit unconditionally set;
  `#166/NH-24` re-verified: the just-merged cleanup only *documents* the
  envelope/effects scaffolding as intentionally inert and removes an unrelated
  dead `arpeggio` key duplication — it does not add an `envelope_type` producer,
  so the finding still holds as described (every real note plays the flat
  `default` envelope).
- **Dim 8** (60Hz timing / frame counter): both live init sites write
  `$4017 = $40` before playback; frame model is integer `range(start_frame,
  end_frame)`, no float drift in the engine. NH-32 above is the comment-only
  regression.
- **Dim 9** (Register addresses / `$4015`): every emitted `sta $40xx` in the
  audited procs lands in `$4000-$4017` on the correct channel's register;
  `$4015 = $0F` at init, `$1F` only when DPCM actually triggers (`play_dpcm` /
  `@write_dpcm`), matching both the legacy `export_direct_frames` procs
  (including the now-added MMC1 bank-switched forms) and the MMC3 bytecode path.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-07-05.md
```
