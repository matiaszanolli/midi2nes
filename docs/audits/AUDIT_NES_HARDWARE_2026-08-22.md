# NES Hardware Correctness Audit — 2026-08-22

Scope: the boundary where Python/asm numbers become APU register writes —
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, `exporter/exporter_ca65.py` (plus the `main.asm`
template in `nes/project_builder.py` and the arranger front-end where its
frame contract touches these files) — re-derived from the working tree at
`59b8a45`, one day after `AUDIT_NES_HARDWARE_2026-08-21.md` (audited at
`949f0c6`).

All 6 findings from the 2026-08-21 report were filed and fixed in this
window: #429 (32-instrument ceiling), #430 (last-frame drop), #431
(arranger sub-C1 triangle detune), #432 (uninitialized `last_*_note`),
#433 (jukebox one-frame-late transition), #434 (dead arranger `0x81`
triangle control byte), plus the pipeline-audit twin #426 (8-bit
`song_table` stride). Each fix was re-read against the live code (not
assumed from the commit message) — see "Verified still clean" below.
This pass's own new findings are a verify-the-fix regression it directly
introduced (#432's sentinel choice, Dimension 9/1) and one pre-existing,
previously-unflagged root cause discovered while re-deriving Dimension 1's
retrigger/phase-reset guarantees end-to-end (Dimension 1/8).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 1 |
| LOW      | 0 |
| **Total**| **2** |

**Highest-risk finding:** two genuinely distinct MIDI note-on events at the
*same pitch* with no intervening rest frame (a common pattern: repeated
staccato notes, gated pulse ostinatos, drum-machine-style constant-pitch
hits — exactly the material this compiler targets) serialize, on **both**
the direct-export and bytecode paths, into a single continuous sustained
note with **no retrigger at all** — not even a volume step when the two
source notes share a velocity. The second note-on is silently absorbed;
nothing distinguishes the output from one long tone (NH-HW-2026-08-22-1,
HIGH).

**Verified still clean (verify-the-fix pass):**
- **D1**: duty 2-bit / volume 4-bit / control byte `0x30` (constant-volume
  + length-halt) unchanged at `nes/envelope_processor.py:163-176`. The
  32-instrument ceiling fix (#429) is in place and correctly derived:
  `exporter/exporter_ca65.py:_register_instrument` raises above `0x1F`,
  matching the engine's 8-bit `current_inst * 8` addressing
  (`nes/audio_engine.asm`). The 32-frame held-note tie fix (#439, landed
  the same day, outside the 2026-08-21 report but re-verified here since
  it touches this dimension directly) is correct for the case it targets:
  `@is_note`'s `cmp current_note, x` / `beq @is_note_tie` skips the macro/
  phase reset only when two adjacent same-note stream bytes are, by the
  exporter's own event-boundary construction, one held event's own
  32-frame chunk split — confirmed by re-reading `_build_song_bytecode`'s
  frame loop (`exporter/exporter_ca65.py:1297-1352`): a `Length`-chunked
  split of ONE `current_event` never changes `note`, so the tie branch is
  reachable only there. Finding 1 below shows a *different*, upstream
  place (frame generation, not bytecode chunking) where two independent
  events collapse before either export path ever sees two note bytes —
  #439's invariant is not violated, it just doesn't cover this case
  because the case never reaches the engine as two bytes in the first
  place.
- **D2**: triangle invariant holds. `arranger/pipeline_integration.py`'s
  triangle conversion (`:355-368`) now emits no `control` key at all
  (#434 fix confirmed in place), matching `process_all_tracks`'
  `default_duty=None` contract (`nes/emulator_core.py:133`). No volume/
  duty reaches `$4008-$400B` on either front-end
  (`docs/APU_TRIANGLE_REFERENCE.md` §1/§4/§5).
- **D5**: the arranger sub-C1 detune fix (#431) is in place —
  `midi_note_to_nes_pitch` (`arranger/pipeline_integration.py:450-455`)
  now clamps to `CHANNEL_RANGES[channel]` *before* the table lookup,
  matching `PitchProcessor.get_channel_pitch` and the serializer's
  floor-24 base-timer assumption exactly.
- **D6**: `velocity_to_volume` (`nes/envelope_processor.py:4-15`) is the
  single shared curve (survived the #460 dual-key consolidation refactor
  unchanged in behavior — that refactor only touched the
  `velocity`/`volume` key-selection helper, `core/events.py`, not the
  curve itself); clamped 0-15 at every site, `min(15, round(...))` cannot
  tip to 16 (both factors ≤ 15).
- **D8**: the direct-export last-frame off-by-one fix (#430) is in place
  and correct — both the `play_music_frame` range guard and the loop-reset
  compare against `frame_count = max_frame + 1` (exclusive upper bound),
  not `max_frame` itself (`exporter/exporter_ca65.py:855-889`); index
  `max_frame` now plays before any reset can fire.
- **D9**: `APU_*` register constants (`exporter/exporter_ca65.py:6-29`)
  all land in `$4000-$4015` on the correct channel/function; no new write
  outside the documented window found in this pass.
- **D10**: the 32-instrument and 51-song ceilings (#429/#426) both raise
  `ValueError` at export time now rather than silently wrapping — re-read
  both guards line-by-line, derivations check out (`(255-4)//5+1 = 51`
  songs, `0x1F` = 31 → ids `0-31` = 32 instruments).
- **D11**: the jukebox `song_table` 8-bit-stride fix (#426) is in place —
  `export_song_bank_bytecode` (`exporter/exporter_ca65.py:1645-1652`)
  raises above 51 songs, matching the engine's `current_song*5+channel`
  8-bit addressing (`nes/audio_engine.asm`) exactly.
- **D7**: envelope scaffolding still inert as documented (#166) —
  `grep -rn "envelope_type" --include="*.py" .` outside `tests/` shows
  only the one dead-parameter read in `nes/emulator_core.py:104`; no
  pipeline stage sets it.

---

## Findings

### NH-HW-2026-08-22-1: Same-pitch note-on retriggers with no gap frame are silently absorbed into the previous note — no phase reset, no volume step, no distinguishable output
- **Severity**: HIGH
- **Dimension**: 1 (pulse phase-reset/retrigger correctness) / 8 (frame model) — root cause is frame generation, shared by both export paths
- **Location**: `nes/emulator_core.py:52-126` (`compile_channel_to_frames` — the frame dict carries only a raw `note` value per frame, with no way to mark "this frame begins a new attack" vs. "this frame continues the previous one"); consumed identically by `exporter/exporter_ca65.py:1297` (`_build_song_bytecode`'s `if note != current_note` event-boundary test) and by direct-export's `play_pulse1`/`play_pulse2` `cmp last_pulse1_note` / `beq @sustain` guard (`exporter/exporter_ca65.py:341-360`)
- **Status**: NEW (searched `docs/audits/` and `/tmp/audit/issues_all.json` for "retrigger", "articulation", "same pitch/note", "phase reset", "sustain merge" — the only near-hits are #34/NH-08, a dead-expression bug in the same function unrelated to event boundaries, and #296/#449, both arranger-only note-*loss* bugs at the MIDI-pairing stage, explicitly distinguished from the legacy front-end in #449's own writeup: "the legacy front-end does not share the defect" — that statement is true for total note loss, but this is a different bug, one level downstream, that the legacy front-end *does* share)
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §3 "Critical Side Effects" — "Writing to `$4003`/`$4007` immediately restarts the sequencer at the first step of the sequence... This phase reset is what causes an audible click... if done continuously" — i.e. the phase-reset write is the mechanism a genuine new attack is *supposed* to use to read as distinct from a held note; `docs/APU_ENVELOPE_REFERENCE.md` §4/§5 (constant-volume output — this engine has no hardware envelope decay to fall back on for articulation, so the phase-reset write and/or a volume step are the *only* two channels through which a retrigger can become audible at all)
- **Description**: `compile_channel_to_frames` builds its `frames` dict purely from a per-frame `note` value; it has no onset marker. When two real, independent MIDI note-on events land on the same pitch with the second's start frame equal to the first's end frame (a common shape: a note-off paired to the next note-on's frame, or two notes with no rest between them — routine for repeated/staccato notes and gated ostinatos), the two events produce **adjacent frames carrying the identical `note` value with no frame gap**. Both downstream consumers key their retrigger logic on "did `note` change since the last frame/byte": `_build_song_bytecode`'s `if note != current_note` treats the whole span as one macro event (no `Length`/note byte boundary is ever emitted at the join), and direct-export's `cmp last_pulse1_note` / `beq @sustain` suppresses the $4003 rewrite the same way. If the two source notes also share a velocity (identical or velocity-to-volume-bucket-equal — routine for mechanically quantized/drum-pattern MIDI), the volume macro/control byte is flat across the join too, so **literally nothing** in the emitted ROM distinguishes two attacks from one long sustain.
- **Evidence**: Reproduced against the live pipeline (no mocks) — two MIDI note-on events at pitch 60, velocities 100/100, note-off of the first exactly at the second's onset frame (frame 10):
  ```python
  events = [
      {'frame': 0, 'note': 60, 'velocity': 100},
      {'frame': 10, 'note': 60, 'velocity': 0},    # note-off, event 1
      {'frame': 10, 'note': 60, 'velocity': 100},  # note-on, event 2 (genuine retrigger)
      {'frame': 20, 'note': 60, 'velocity': 0},
  ]
  frames = NESEmulatorCore().compile_channel_to_frames(events, channel_type='pulse1', default_duty=2)
  # frame 9:  {'note': 60, 'control': 0x30|..., ...}
  # frame 10: {'note': 60, 'control': 0x30|..., ...}   <- identical to frame 9, no marker
  ```
  Feeding those frames through `CA65Exporter._build_song_bytecode` (bytecode/patterned path):
  ```
  pulse1_sequence:
      .byte $80, $01 ; CMD_INSTRUMENT
      .byte $73, $3C ; Length 20, Note 60      <- ONE event, not two
      .byte $FF
  ```
  One `Length 20, Note 60` — the engine's `@is_note` is invoked exactly once for the whole 20-frame span; there is no second note byte for it to tie-break or reset against. Direct-export produces the equivalent: `play_pulse1`'s per-frame `note`/`control`/`timer_lo`/`timer_hi` tables are byte-identical across the frame-9/frame-10 join, so `cmp last_pulse1_note` stays equal for all 20 frames and $4000-$4003 are written once, at frame 0, never again.
- **Impact**: Every pipeline configuration (default, `--arranger`, `--no-patterns`) on any MIDI content with back-to-back same-pitch note-ons and no rest gap. The two source notes play as audibly indistinguishable from one sustained note whenever their velocities also match (drum-machine-style constant-velocity patterns, quantized MIDI, many chiptune-style repeated-note passages — exactly the material this compiler targets); when velocities differ, a volume step is still audible at the join (a partial cue), but the phase-reset "attack" transient `docs/APU_PULSE_REFERENCE.md` §3 documents is never produced either way. This changes the song's rhythm/articulation on realistic input with no warning — "wrong output under realistic input" per `_audit-severity.md`'s HIGH bucket.
- **Related**: #439/EXP-2026-08-21-1 (a different, correctly-scoped fix one layer downstream — its own comment's "by construction" claim about repeated note bytes only covers the 32-frame chunk-split case, and remains true for that case; this finding is the upstream case where two real onsets never even become two note bytes for `@is_note` to see). #449/ARR-2026-08-21-2, #296/ARR-NEW-4 (arranger-only note-*loss* bugs at MIDI note-pairing — distinct bug, same neighborhood: repeated/overlapping same-pitch notes losing information somewhere in the pipeline).
- **Suggested Fix**: Give `compile_channel_to_frames` a way to mark a frame as a genuine new onset even when the pitch is unchanged from the previous frame — e.g. an explicit `retrigger: True` key on the first frame of each source event, threaded through to `_build_song_bytecode`'s `if note != current_note` test (treat `retrigger` as equivalent to a note change for event-boundary purposes) and to direct-export's `last_pulse1_note` comparison (force the rewrite when `retrigger` is set even if the note value is unchanged, mirroring how #439 already forces `last_written_hi = $FF` on a genuine new note). This is a frame-schema addition, not a change to the existing note-equality fast path, so it should not disturb #439's or #161/NH-18's held-note behavior.

### NH-HW-2026-08-22-2: `last_dpcm_note`'s `$FF` "impossible value" sentinel (#432) is a real, reachable DPCM note in direct-export — a song's first drum trigger can be silently skipped
- **Severity**: MEDIUM
- **Dimension**: 1 (register-write gating) / 9 (register-write correctness) — same class of bug the fix this regresses was written to close
- **Location**: `exporter/exporter_ca65.py:813-825` (`reset` proc: `lda #$FF` / `sta last_pulse1_note` / `...last_pulse2_note` / `...last_triangle_note` / `...last_dpcm_note`), `:992-995` (non-standalone `init_music`, same four `sta`s), vs. `nes/emulator_core.py:235` (`"note": min(255, dense_id + 1)`) and `exporter/exporter_ca65.py:335` (`d_note.append(f'${fd.get("note", 0) & 0xFF:02X}')`)
- **Status**: NEW (the flag bug on these same four variables was #107/NH-14, fixed; the missing-init bug the `$FF` seed itself fixes was #432/NH-HW-2026-08-21-5, fixed correctly for the three tone channels — this is a narrower defect in that same fix, specific to the fourth variable it also seeded)
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §6 "255-Distinct-Sample Ceiling Per Song" — direct-export (`--no-patterns`) has no note-range limit below 255 and "can use the full 255"; contrast the bytecode/patterned path, which raises `ValueError` above note `$5F` (95) at export time (#369/EXP-2026-07-19-1) and is therefore **not** affected by this finding
- **Description**: #432's fix seeded all four `last_*_note` BSS bytes with `$FF`, reasoning (correctly, for three of the four) that MIDI notes are 0-127 so `$FF` can never collide with a legitimate first note. That reasoning does not hold for `last_dpcm_note`: the DPCM channel's "note" is not a MIDI pitch but `min(255, dense_id + 1)` — a dense, song-local sample index — and direct-export explicitly supports the full `0-255` range (`docs/APU_DMC_REFERENCE.md` §6, "`--no-patterns` ... has no such limit and can use the full 255"). A song that references ≥254 distinct DPCM samples has a legitimate `note = 255` (`$FF`) value. If the sample encoded as (or collapsed to) `dense_id = 254` happens to be the **first** DPCM trigger the song plays, `play_dpcm`'s `cmp last_dpcm_note` (`exporter/exporter_ca65.py:555`) reads `$FF == $FF` and takes the `@done` branch — the exact bug #432 was written to eliminate, reintroduced for this one channel by the sentinel choice itself.
- **Evidence**: `nes/emulator_core.py:235`, `"note": min(255, dense_id + 1)` — confirmed `255` is reachable, not merely a theoretical byte-range argument. `exporter/exporter_ca65.py:335`, `d_note.append(f'${fd.get("note", 0) & 0xFF:02X}')` — the raw note value is emitted straight into the `dpcm_note` table with no re-mapping, so a genuine `255` becomes byte `$FF` in the table the engine reads. `play_dpcm`'s guard at `:555-556` (`cmp last_dpcm_note` / `beq @done`) has no channel-specific carve-out for this case. By contrast, `last_pulse1_note`/`last_pulse2_note`/`last_triangle_note` are safe: their table values come straight from `frame_data.get('note', 0)` (`:271`), which is a MIDI note number, inherently ≤ 127 (`$7F`) — well clear of `$FF`.
- **Impact**: Direct-export (`--no-patterns`) ROMs only, and only for songs referencing ≥254 distinct DPCM samples — an extreme sample count for a single song, so this is a narrow edge case in practice, but fully deterministic and silent once triggered (unlike the RAM-garbage class #432 was defending against, this doesn't need real hardware or unusual power-on state to fire — it fires on every playthrough of the affected ROM if the song's very first DPCM hit lands on that sample id). Workaround: keep a song under 255 distinct DPCM samples, which `docs/APU_DMC_REFERENCE.md` §6 already recommends for the unrelated #343/DP-DPCM-04 aliasing reason.
- **Related**: #432/NH-HW-2026-08-21-5 (the fix this narrows), #343/DP-DPCM-04 (the other consequence of the same 255-sample ceiling), #369/EXP-2026-07-19-1 (why the bytecode/patterned path is immune — its own, tighter 95-sample ceiling means `note` never reaches 255 there).
- **Suggested Fix**: Seed `last_dpcm_note` with a value outside `0-255` is impossible (it's a single byte) — instead seed it with `$00` (the documented rest/no-trigger sentinel, `docs/AUDIO_BYTECODE_SPEC.md` / `_emit_dpcm_table`'s own `$00` = "empty frame") and let the existing `cmp #0` / `beq @done` "rest, nothing to trigger" branch (the one #107/NH-14 fixed to actually re-test) do double duty: it already treats a `last_dpcm_note` of `$00` as "no sample currently playing," which is true at power-on, and `$00` cannot collide with any real triggered sample since `note=0` is reserved as the rest sentinel on this channel specifically (unlike the tone channels, where note `0` is a valid-looking-but-unused value and `$FF` was the correct choice).

---

## Notes on scope boundaries

- Finding 1's root cause sits in `nes/emulator_core.py`, the shared frame
  generator both front-ends' hardware output ultimately derives from; the
  arranger's own note-pairing bugs (#296, #449) are a related but distinct
  failure mode one stage upstream (MIDI event → `NoteInfo`, not frame →
  bytecode/register-write), and are out of this audit's file scope
  (`/audit-arranger`'s territory) — cross-referenced, not re-litigated.
- Both findings concern *silent* behavior (no exception, no warning
  printed, ROM builds and boots normally) — neither is a compile-time or
  boot-time failure, which is why neither reaches CRITICAL under
  `_audit-severity.md`'s decision tree (no crash, no PRG overrun, no
  claimed-lossless compression producing different output than what it
  compressed).
- The skill's own preamble (`.claude/commands/audit-nes-hardware/SKILL.md`)
  still lists NH-14 (#107) and NH-25 (#167) as the "still open" set; both
  are confirmed CLOSED in `/tmp/audit/issues_all.json` and their fixes
  hold in the code read for this pass (already flagged as skill-prose
  staleness in the 2026-08-21 report's own scope notes — not re-filed
  here, `/audit-sync`'s territory).

## Suggested next step

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-08-22.md
```
