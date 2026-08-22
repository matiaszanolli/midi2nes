# NES Hardware Correctness Audit — 2026-08-21

Scope: the boundary where Python/asm numbers become APU register writes —
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, `exporter/exporter_ca65.py` (plus the `main.asm`
template in `nes/project_builder.py`) — all eleven dimensions of
`.claude/commands/audit-nes-hardware/SKILL.md`, re-derived from the working
tree at `949f0c6`. Dimension 11 (jukebox `.ifdef JUKEBOX_BUILD` paths) was
audited as new code per the skill's instruction; the 1-song `song build`
link failure found on 2026-08-07 is confirmed **fixed** by `8ea7ac3`
(`JUKEBOX_BUILD` gate now `song_count is not None`, per-song `CODE_8000`
reset in `_build_song_bytecode`).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 5 |
| LOW      | 2 |
| **Total**| **8** |

6 findings are NEW; 2 are carry-overs from AUDIT_NES_HARDWARE_2026-08-07
that were never filed as issues and remain unfixed.

**Headline — the highest-risk divergence is wrong on every bytecode ROM
whose song is rich enough:** the macro-bytecode engine can only address
**32 instruments** (`current_inst * 8` computed in 8-bit via three `asl`s,
then indexed through 8-bit `Y`), but the serializer's guard
(`_register_instrument`) allows **256** — instrument ids ≥ 32 are emitted
silently and the engine reads instrument `id % 32`'s macro pointers
instead. Reproduced with a modest 2-channel test song (40 melody notes +
60 drum hits with velocity variety → 39 unique instruments, ids 32–38
emitted with no warning); the repo's own `input.mid` already produces 22
unique instruments, so real material sits near the cliff. Wrong
volume/pitch/duty macros on the affected notes, silently (NH-HW-2026-08-21-1,
HIGH).

**Verified still clean (verify-the-fix pass, all dimensions):**
- **D1**: duty is 2-bit (`(duty_cycle & 0x03) << 6`), volume 4-bit
  (`volume & 0x0F`), and the control byte carries `0x30`
  (constant-volume + length-halt) — `nes/envelope_processor.py:163-176`,
  pinned by `tests/test_core.py:156-161` / `tests/test_envelope.py:106`
  (#167/NH-25 holds). `PULSE_DUTY_CYCLES` still gone; no new duty producer
  emits outside 0–3 (arranger duty comes from the `DutyCycle` enum).
  Sweep disabled (`$08` → `$4001`/`$4005`) at all three init sites and no
  other code path writes those registers. `last_written_hi` phase-reset
  guard (#161/NH-18) intact, `$FF`-sentinel re-armed at note onset and by
  `audio_advance_song`.
- **D2**: triangle invariant holds — `process_all_tracks` routes triangle
  with `default_duty=None` through the non-pulse branch (frame dict has no
  `control`), direct export derives `$4008` solely from `volume`
  (`0x00`/`TRIANGLE_CONTROL_ON`=`0xFF`, `exporter/exporter_ca65.py:247-261`),
  bytecode engine writes fixed `$FF`/`$80` (`nes/audio_engine.asm:613-643`).
  No volume/duty ever reaches `$4008-$400B` (docs/APU_TRIANGLE_REFERENCE.md
  §1/§4/§5). One inert leak flagged LOW (finding 8).
- **D3**: `get_noise_period` single source of truth, delegation intact;
  mode bit reachable on both front-ends (`_noise_mode_for_note`/
  `METALLIC_NOISE_ROLES` legacy; `DrumMapping.periodic` →
  `_allocate_noise` 3-tuple → `mode << 6` arranger,
  `arranger/pipeline_integration.py:332-335`); shared decay helpers
  imported from `nes/envelope_processor.py` by both
  `nes/emulator_core.py` and `arranger/voice_allocator.py:15` (no drift).
- **D4**: all three init paths zero `$4011` *before* `$4015=$0F`
  (`nes/audio_engine.asm:196-207`; `exporter/exporter_ca65.py:783-792`
  standalone reset; `:943-952` direct init_music; bytecode init_music jmps
  to audio_init). `CMD_DMC_LEVEL` has neither producer nor consumer (the
  `@cmd_dmc_level` handler is gone from the engine) — only the spec doc is
  stale (finding 7).
- **D5**: per-channel tables from one `generate_note_table(divider)`
  (pulse /16, triangle /32); both frame-gen and exporter base-timer use the
  same table per channel; 11-bit clamp floored at 8 everywhere including
  `apply_pitch_bend` and the direct exporter's re-assert
  (`exporter/exporter_ca65.py:266-270`). The live pitch-macro add was
  re-verified numerically in-range: worst producible pulse case is note
  108 clamped to 95 → base 55, offset −30, runtime 25 (≥ 8, ≤ `$7FF`);
  triangle 96→95 → base 27, offset −2, runtime 25. Arranger high notes
  (to 127) floor at timer 8 → runtime ≥ 8. One arranger-only sub-C1
  triangle desync found (finding 4).
- **D6**: single `velocity_to_volume` power curve, clamped 0–15 at every
  site; `min(15, round(...))` in `get_envelope_control_byte` cannot tip to
  16 (both factors ≤ 15).
- **D7**: envelope scaffolding still inert as documented (#166) — no
  producer of `envelope_type`/`effects` outside tests; the percussion
  divide-by-zero remains unreachable; constant-volume bit unconditionally
  set.
- **D8**: `$4017 = $40` (4-step mode 0, IRQ inhibit) at all init sites
  with correct comments (docs/APU_FRAME_COUNTER_REFERENCE.md §2–§3);
  engine consumes integer frames only. One direct-export off-by-one found
  (finding 2), one jukebox transition artifact carried over (finding 6).
- **D9**: every emitted `sta $40xx` lands in `$4000–$4017` on the right
  channel register; `$4015=$0F` covers the four tone channels, DMC bit set
  on trigger (`$1F`) by both `@write_dpcm`/`@cmd_dpcm_play` and
  `play_dpcm`. One uninitialized-BSS gap found (finding 5).
- **D10**: clamps present for timer/volume/duty/noise-index; the arpeggio
  add is still fed only `_encode_macro_offset(0)` (no `arp` producer) —
  unchanged, would be HIGH the moment a live producer appears without an
  engine-side range guard.
- **D11**: `instrument_table_ptr` is loaded before any macro eval can run
  (reset → `init_music` → `audio_init_song` →
  `load_song_streams_indexed` precedes NMI enable in the `main.asm`
  template); the `song_table` stride/order (`song*5 + channel`,
  `SEQUENCE_CHANNELS`) matches producer and consumer; the auto-advance
  scan saves/restores `X`, fires at most once per frame, and
  `audio_advance_song` clears `channel_ended` so no double-advance; state
  reset covers `current_len`/`frame_wait`/`current_note`/`channel_ended`/
  `last_written_hi` (uncleared `macro_steps_*`/`current_inst` are benign:
  macros reset at `@is_note`, and every channel stream opens with
  `CMD_INSTRUMENT` since the serializer starts `current_inst = -1`);
  1-song wrap re-inits itself harmlessly; the Start-button poll runs after
  `update_music` returns, so it cannot interleave with channel writes.
  Two defects: the 8-bit song-index multiply (finding 3, NEW) and the
  one-frame-late restart (finding 6, carry-over).

---

## Findings

### NH-HW-2026-08-21-1: Bytecode engine addresses only 32 instruments but the exporter emits up to 256 — ids ≥ 32 silently alias mod 32
- **Severity**: HIGH
- **Dimension**: 1 (pulse duty/volume via instruments) / 10 (value-range) — root cause in the engine's macro addressing, shared by all four tone channels and both single-song and jukebox branches
- **Location**: `nes/audio_engine.asm:486-491` (`lda current_inst, x` / `asl` ×3 / `sta temp_inst_base` — 8-bit multiply), `:81-110` (`EVAL_MACRO`: `ldy temp_inst_base` then `lda instrument_table+inst_offset, y` non-jukebox, or `tya / adc #inst_offset / tay / lda (instrument_table_ptr), y` jukebox — 8-bit `Y` in both branches), vs. `exporter/exporter_ca65.py:1009-1028` (`_register_instrument`, which only raises above `0xFF`)
- **Status**: NEW (#80/EXP-04 covered only the >256 single-byte-operand ceiling; no prior issue or report covers the engine's 32-instrument addressing limit — checked `/tmp/audit/issues.json` and all `docs/audits/AUDIT_NES_HARDWARE_*` / `AUDIT_EXPORTERS_*`)
- **Hardware ref**: `docs/2A03_CPU_REFERENCE.md` §1 (6502 core: A/X/Y are 8-bit, so `asl`×3 and indexed addressing wrap at 256); `docs/AUDIO_BYTECODE_SPEC.md` §"instrument_table" and `$80`/`CMD_INSTRUMENT` (each instrument row is 4 `.word` pointers = 8 bytes, so id 32's row starts at byte offset 256 — beyond 8-bit reach)
- **Description**: Each instrument occupies 8 bytes of `instrument_table` (4 macro pointers). The engine computes the row offset as `current_inst * 8` with three `asl`s of the 8-bit accumulator and indexes with 8-bit `Y`, so the reachable window is exactly 32 instruments; for `inst_id >= 32` the offset wraps mod 256 and the engine reads instrument `inst_id % 32`'s volume/arp/pitch/duty macro pointers instead. The serializer's `_register_instrument` guard only rejects ids above 255, and `${inst_id:02X}` assembles cleanly for 32–255, so nothing on either side of the contract warns. Every note carrying an aliased `CMD_INSTRUMENT` plays with another instrument's macros — wrong volume envelope, wrong pitch-offset macro (audibly wrong pitch when the aliased pitch macro differs), wrong duty/noise-mode.
- **Evidence**: Reproduced against the live serializer (no mocks):
  ```
  # 40 pulse notes (varied velocities 40..127, some clamped high notes) +
  # 60 noise hits (varied velocities, decay spans 2..7) through
  # NESEmulatorCore.process_all_tracks -> _build_song_bytecode:
  unique instruments: 39
  max CMD_INSTRUMENT id: 38 | ids >= 32 emitted: 8
    id 32 -> engine reads instrument 0's macro pointers
    id 33 -> engine reads instrument 1's macro pointers  ...
  ```
  The repo's own `input.mid` (a real 4-channel song) already produces 22
  unique instruments through the default pipeline, so 32 is a realistic
  ceiling to cross, not a pathological one — noise-decay ramps alone
  contribute one distinct volume macro per (peak volume × decay span)
  combination.
- **Impact**: Bytecode-path (default pipeline and every `song build` ROM — the jukebox indirect branch has the identical 8-bit math) songs with ≥ 33 unique (vol, arp, pitch, duty) combinations silently play wrong macros on all notes using instruments 32+. No error, no warning, ROM links and boots. Under the severity doc's "silent contract corruption that changes the song" rule this arguably reads CRITICAL; rated HIGH because the direct-export path (`--no-patterns`) is a full-fidelity workaround and the practical corruption is per-note degradation (wrong loudness/pitch-offset/timbre) rather than structural garbage.
- **Related**: #80/EXP-04 (the >256 guard this slips under); docs/AUDIO_BYTECODE_SPEC.md documents no instrument-count limit either (secondary doc gap).
- **Suggested Fix**: Lower `_register_instrument`'s ceiling to 32 (`new_id > 0x1F` → raise with the same "reduce timbre variety or split the song" message), and state the limit in `docs/AUDIO_BYTECODE_SPEC.md`. Alternatively widen the engine (16-bit pointer math for the row offset), but the exporter-side guard is the 3-line fix that makes the contract honest today.

### NH-HW-2026-08-21-2: Direct-export playback never plays the final frame table entry — off-by-one in the range/loop guards; a 1-frame song is entirely silent
- **Severity**: MEDIUM
- **Dimension**: 8 (60Hz frame timing)
- **Location**: `exporter/exporter_ca65.py:854-863` (`play_music_frame` range guard: `cmp #<{max_frame}` / `bcs @done` treats `frame_counter == max_frame` as out of range), `:829-841` (standalone `nmi` loop reset fires at `frame_counter == max_frame`), `:971-983` (non-standalone `update_music`, same reset)
- **Status**: NEW (no prior issue or audit report covers it — searched `play_music_frame`, "off-by-one", "last frame" across `docs/audits/` and the issue list)
- **Hardware ref**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §4 (the engine's one-frame-entry-per-NMI-tick playback model); `.claude/commands/_audit-common.md` NES Hardware Constraints ("frame data is one entry per 1/60s tick")
- **Description**: The frame tables are emitted with `max_frame + 1` entries (indices `0..max_frame`, where `max_frame` is the last frame that has data — by construction always a populated entry). `play_music_frame` refuses to play when `frame_counter >= max_frame` (the `bcs @done` includes equality), and both loop checks reset `frame_counter` to 0 as soon as it *reaches* `max_frame` — so index `max_frame` is dead data: the final frame of the song is skipped on every loop iteration. Degenerate case: a song whose only data is on frame 0 (`max_frame = 0`) never plays anything at all (`cmp #<0` / `bcs @done` is always taken).
- **Evidence**: Emitted code (any direct export):
  ```asm
  .proc play_music_frame
      lda frame_counter+1
      cmp #>{max_frame}
      bcc @in_range
      bne @done
      lda frame_counter
      cmp #<{max_frame}
      bcs @done          ; == max_frame -> done: entry max_frame never plays
  @in_range: ...
  ```
  and the loop in `update_music`/`nmi` resets to 0 at `frame_counter == max_frame`, so no later tick can reach the entry either.
- **Impact**: Every `--no-patterns` / direct-export ROM (all mappers) drops the song's final 16.7 ms frame — usually the last sustain frame of the closing note (near-inaudible), but a 1-frame final event (a DPCM drum trigger or staccato note landing exactly on the global `max_frame`) is dropped entirely, and a 1-frame song produces a silent ROM. Bytecode path unaffected (stream-driven, `$FF`-terminated).
- **Related**: none open.
- **Suggested Fix**: Make the guards exclusive of the last entry correctly: play while `frame_counter <= max_frame` (i.e. `beq @in_range` on the equal case, or compare against `max_frame + 1`), and reset the loop counter when it reaches `max_frame + 1`.

### NH-HW-2026-08-21-3: Jukebox `current_song * 5` is 8-bit — banks of 52+ songs export cleanly but songs from index 51 read wrapped `song_table` entries
- **Severity**: MEDIUM
- **Dimension**: 11 (jukebox engine paths — song_table stride contract)
- **Location**: `nes/audio_engine.asm:267-286` (`load_song_streams_indexed`: `asl a / asl a / clc / adc current_song / tay` then `@copy_loop`'s `iny` — both the multiply and the running `Y` wrap at 256), vs. `exporter/exporter_ca65.py:1548-1685` (`export_song_bank_bytecode` — no cap on `len(songs)`) and `main.py:1014` (`run_song_build` passes `song_count=len(songs)` unguarded)
- **Status**: NEW
- **Hardware ref**: `docs/2A03_CPU_REFERENCE.md` §1 (8-bit A/Y — `current_song*5` and the per-channel `iny` wrap mod 256); the stride contract itself is defined by `export_song_bank_bytecode`'s docstring ("indexed `song_index*5 + channel`")
- **Description**: `song_table_ptr_lo/hi/bank` are indexed `song*5 + channel`. The engine computes the base in 8 bits and walks 5 entries with `iny`. Song index 51's channel 0 lands at entry 255; the following `iny` wraps `Y` to 0, so channels 1–4 load song 0's channel 0–3 stream pointers/banks. From index 52 up, the multiply itself wraps (52×5 = 260 → 4), mixing arbitrary songs' streams. Nothing guards this: the MMC3 bank budget (`SWAP_BANK_COUNT = 60`, each song starting a fresh bank) admits up to 60 songs, so a 52–60 song bank exports, links, and boots — then plays a silently-corrupted mix of stream pointers from song 52 onward (`song_instrument_ptr_*`, indexed by song alone, stays correct, compounding the mismatch: right instruments, wrong streams).
- **Evidence**: `load_song_streams_indexed`:
  ```asm
      lda current_song
      asl a
      asl a               ; A = current_song * 4  (carry out lost)
      clc
      adc current_song    ; A = current_song * 5  (mod 256)
      tay
  @copy_loop:
      lda song_table_ptr_lo, y   ; Y wraps 255 -> 0 mid-loop for song 51
      ...
      iny
  ```
  `export_song_bank_bytecode` and `run_song_build` contain no `len(songs)` check (grepped); the only ceiling that fires first is the 60-bank ValueError, at 61+ songs.
- **Impact**: Any `song build` bank with ≥ 52 songs: songs at index ≥ 51 play the wrong channels' bytecode (typically desyncing into `$FF`/garbage or another song's music), silently. Requires an unusually large bank, hence MEDIUM rather than HIGH — but it is silent corruption on an input the toolchain accepts without complaint.
- **Related**: #30/F-13 (feature); complements the producer-side checks in `/audit-exporters` Dimension 9.
- **Suggested Fix**: Raise in `export_song_bank_bytecode` when `len(songs) > 51` (the engine's real addressing limit), mirroring the bank-budget ValueError, and document the ceiling; alternatively widen the engine lookup to 16-bit pointer math.

### NH-HW-2026-08-21-4: `--arranger` sub-C1 triangle notes serialize to a detuned pitch — arranger pitch skips the channel-range clamp the serializer assumes
- **Severity**: MEDIUM
- **Dimension**: 5 (per-channel pitch-table correctness)
- **Location**: `arranger/pipeline_integration.py:351-380` (`midi_note_to_nes_pitch` clamps only to MIDI 0–127, then indexes the raw table) and `:314-320` (triangle frames get `pitch = table[note]` for any note), vs. `exporter/exporter_ca65.py:1212-1220` (serializer floors the stream note at 24 "to the same floor the frame pitch was already clamped to" — an assumption only the legacy front-end satisfies) and `:84-99` (`_encode_macro_offset` clamps the resulting oversized delta to +127)
- **Status**: NEW (#158/NH-16 fixed the base-timer side; #89/ARR-06 made the arranger use the shared tables but not the shared *range clamp* — neither covers this desync)
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §1 (base timer and pitch offset must be on the same scale/note); `docs/APU_TRIANGLE_REFERENCE.md` §3 (/32 divider — triangle timers for notes 21–23 are 1918–2032, genuinely representable within 11 bits, unlike pulse where they clamp to `$7FF`)
- **Description**: The legacy front-end's `get_channel_pitch` clamps the note to the channel range (triangle 24–96) before the table lookup, so for a sub-C1 note the frame `pitch` equals `table[24]` and the serializer's note-floor at 24 yields offset 0. The arranger's `midi_note_to_nes_pitch` performs no channel-range clamp: a bass note 21 (A0 — real low-piano/bass register) produces `pitch = NES_TRIANGLE_TABLE[21] = 2032` while the serializer computes `base = table[24] = 1709` from the floored note, giving a raw offset of +323 that `_encode_macro_offset` clamps to +127. The runtime period is 1709 + 127 = **1836** — neither the intended A0 (2032, which the hardware could actually play) nor the clamp-to-C1 (1709), but a detuned pitch roughly a quarter-tone below C1.
- **Evidence**: Reproduced end-to-end:
  ```
  arrange_for_nes({'bass': [note 21 @f0 vel100, ...]}) ->
  triangle frame0: {'note': 21, 'pitch': 2032, 'volume': 15, 'control': 129}
  serializer: base@24=1709, raw offset=+323, encoded(clamped)=+127,
  runtime timer=1836 (intended 1709 by clamp policy, 2032 by hardware ability)
  ```
  Pulse channels are immune only by luck: pulse timers for notes ≤ 28 all clamp to `$7FF`, so pitch and base coincide and the offset is 0.
- **Impact**: `--arranger` songs with bass below C1 (MIDI 21–23; also 0–23 generally) on the triangle play those notes at a wrong, detuned pitch on every ROM (bytecode path). Stays inside `$0–$7FF` (no hardware-range violation, no silence) — wrong-but-in-range, hence MEDIUM. Legacy front-end unaffected.
- **Related**: #158/NH-16, #89/ARR-06, #298/EXP-10 (the clamp-tally warning also under-reports here: the note *is* counted as clamped-low, but the played pitch isn't the clamp target).
- **Suggested Fix**: Clamp the note to `CHANNEL_RANGES[channel]` inside `arranger/pipeline_integration.py`'s `midi_note_to_nes_pitch` (matching `PitchProcessor.get_channel_pitch`), so frame `pitch` and the serializer's floored note agree. Longer-term, the serializer could trust the triangle's real representable range instead of hard-flooring at 24.

### NH-HW-2026-08-21-5: Direct-export `last_*_note` state is never initialized — power-on RAM garbage can swallow a channel's first note or first DPCM trigger
- **Severity**: MEDIUM
- **Dimension**: 9 (register-write correctness) / 10 (defense-in-depth)
- **Location**: `exporter/exporter_ca65.py:666-671` (BSS: `last_pulse1_note`/`last_pulse2_note`/`last_triangle_note`/`last_dpcm_note`, no initializer), `:764-810` (standalone `reset` — no write to them), `:940-959` (non-standalone `init_music` — likewise), `nes/project_builder.py:441-463` (`main.asm` reset template — no RAM-clear loop)
- **Status**: NEW (the *flag*-bug on these variables was #107/NH-14, fixed via the `cmp #0` re-test — confirmed in place at `:357`, `:414`, `:468`, `:561`; the missing initialization was never separately reported)
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §2 "Critical Side Effects" (the reason the same-note short-circuit exists: `$4003`/`$4007` writes reset phase) — and the bytecode engine's own practice: `nes/audio_engine.asm:240-241` deliberately seeds `last_written_hi, x` with the `$FF` sentinel at init precisely so stale compare-state cannot suppress the first genuine write (#161/NH-18)
- **Description**: The direct-export playback procs gate all register writes on `cmp last_<ch>_note` / `beq @sustain`. Neither the standalone `reset` proc nor `init_music` nor the generated `main.asm` clears RAM or seeds these four bytes, so on real hardware they hold power-on garbage. If a channel's garbage byte happens to equal that channel's first nonzero note value, the "note changed" test fails on every frame of that first note: control/timer are never written and the note is silent until the next note change (for `last_dpcm_note`, the first drum sample never triggers). Emulators that zero RAM mask the bug (first note ≠ 0 always differs); it is a real-hardware/randomized-RAM class of failure, the exact class the bytecode engine already defends against with its `$FF` sentinel.
- **Evidence**: `grep -n "last_pulse1_note" exporter/exporter_ca65.py` → definition `:667` and compares/stores only inside `play_pulse1`; no `lda #$xx / sta last_*` anywhere; `_generate_main_asm`'s reset does `sei/cld/txs`, mapper init, frame-counter zero, `jsr init_music`, NMI enable — no RAM clear (`nes/project_builder.py:441-463`).
- **Impact**: `--no-patterns` / direct-export ROMs on real hardware (or accuracy emulators with randomized RAM): per boot, per channel, a ~1/256 chance the first note (or first drum) of the song is skipped. Low probability, silent when it hits, and hardware-only — MEDIUM as a defense-in-depth gap at the register boundary.
- **Related**: #107/NH-14 (fixed flag bug on the same variables), #161/NH-18 (the bytecode engine's sentinel this path lacks).
- **Suggested Fix**: Seed all four `last_*_note` bytes with `$FF` (an impossible note value — notes are ≤ `$5F`/`$FF`-safe here since table notes are MIDI ≤ 127 and DPCM dense ids ≤ 255... use `$FF` for tone channels and add a standard reset RAM-clear loop, or an explicit 4-byte init in both `reset` and `init_music`), mirroring `audio_engine.asm`'s `last_written_hi` init.

### NH-HW-2026-08-21-6: Jukebox auto-advance still starts some/all channels one NMI frame late at a song transition
- **Severity**: MEDIUM
- **Dimension**: 8 (60Hz frame timing) / 11 (jukebox)
- **Location**: `nes/audio_engine.asm:733-762` (`@end_of_stream` `.ifdef JUKEBOX_BUILD` block — byte-identical to the code analyzed on 2026-08-07)
- **Status**: NEW as an issue — carry-over of AUDIT_NES_HARDWARE_2026-08-07 finding NH-HW-2026-08-07-2, which was never filed on GitHub (no matching issue in `/tmp/audit/issues.json`) and whose code is unchanged by `8ea7ac3`/`949f0c6`
- **Hardware ref**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §4 (NMI-driven 60Hz engine — one frame entry per tick, uniformly across channels)
- **Description**: When the last-finishing channel `k` triggers the all-5-`channel_ended` scan mid-way through `audio_update`'s channel loop, `audio_advance_song` reloads all stream pointers and zeroes `frame_wait`, but execution falls through to `@silence` for channel `k` and never re-visits channels with index ≤ `k` this frame. Channels with index > `k` fetch the new song's first byte the same frame; channels ≤ `k` (including `k`) start one 60Hz tick (~16.7 ms) later. Since DPCM (index 4) is always the trivially-ended `.byte $FF` stream in v1 jukebox builds, the triggering channel is always one of the four audible channels — in the realistic case where the longest-ringing channel is noise (index 3), all four audible channels restart late and only the silent DPCM slot starts on time. Manual Start-button skips are unaffected (called outside the channel loop).
- **Evidence**: See the 2026-08-07 report's full trace; re-verified the block is unchanged at HEAD (`@jukebox_scan_ended` → `jsr audio_advance_song` → `pla / tax` → `jmp @silence`, no re-entry to `@fetch_byte`).
- **Impact**: Multi-song jukebox ROMs only; a bounded, non-accumulating one-frame stagger/silence at each natural song transition.
- **Related**: #30/F-13; AUDIT_NES_HARDWARE_2026-08-07 NH-HW-2026-08-07-2.
- **Suggested Fix**: After a successful advance, re-enter the frame's dispatch for the triggering channel (reload `sequence_ptr`/`sequence_bank` from the fresh `stream_*` and `jmp @fetch_byte`), or have `audio_update` restart its channel loop from `x = 0` once when an advance occurred this frame.

### NH-HW-2026-08-21-7: `docs/AUDIO_BYTECODE_SPEC.md` still documents `$87`/`CMD_DMC_LEVEL` as a real, working opcode — regression of #83/EXP-07 persists
- **Severity**: LOW
- **Dimension**: 4 (DPCM/DMC)
- **Location**: `docs/AUDIO_BYTECODE_SPEC.md:106` (the `$87` opcode-table row) and `:95-99` (preamble calling `$87` "real, working")
- **Status**: Regression of #83/EXP-07 — carry-over of AUDIT_NES_HARDWARE_2026-08-07 finding NH-HW-2026-08-07-3, never filed, still present verbatim
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2–§3 (`$4011` direct DAC load — the register the deleted handler wrote)
- **Description**: The engine's `@cmd_dmc_level` consumer was deleted under #309; the current `nes/audio_engine.asm` dispatches only `$FE`/`$85`/`$80` and routes everything else to `@unknown_command` → `@end_of_stream`. A `$87` byte today would silently terminate the channel's stream — the opposite of what the spec promises. `grep -in dmc_level nes/audio_engine.asm exporter/exporter_ca65.py` → no matches (re-confirmed this pass).
- **Impact**: Documentation-only; no producer emits `$87` (pinned by `tests/test_ca65_export.py::test_dmc_level_command_path_removed`). Risk is a future contributor trusting the spec.
- **Related**: #83/EXP-07, #309, #72/D-09.
- **Suggested Fix**: Delete the `$87` row (or mark "removed, #309 — no longer decoded; falls to @unknown_command") and fix the preamble sentence.

### NH-HW-2026-08-21-8: Arranger emits a hardcoded pseudo-linear-counter `control: 0x81` on triangle frames that no consumer reads — dead data / latent trap
- **Severity**: LOW
- **Dimension**: 2 (triangle invariant)
- **Location**: `arranger/pipeline_integration.py:319` (`'control': 0x81,  # Triangle linear counter`)
- **Status**: NEW
- **Hardware ref**: `docs/APU_TRIANGLE_REFERENCE.md` §1/§4 (no volume/duty; `$4008` is control-flag + 7-bit reload — a real `$4008` byte would be `$FF`/`$80`/`$00` in this engine, never `$81`)
- **Description**: Both sinks ignore a triangle frame's `control` key: `export_direct_frames` derives the `$4008` byte solely from `volume` (`0x00`/`TRIANGLE_CONTROL_ON`), and `_build_song_bytecode` only extracts duty bits from it (`(0x81 >> 6) & 3 = 2`), which the engine then discards for channel 2 (`cpx #2 / beq @skip_duty`). So `0x81` is inert today — but it *looks* like a meaningful linear-counter reload (control flag + reload 1, i.e. a near-instant gate), the same latent-trap shape as the `volume * 7` reload retired under #364/NH-HW-04: a future consumer honoring it would nearly silence every arranger triangle note. The legacy front-end emits no `control` key for triangle at all, which is the honest shape.
- **Impact**: None at runtime today; maintainability/latent-trap only.
- **Related**: #364/NH-HW-04 (same class, exporter side, fixed).
- **Suggested Fix**: Drop the `control` key from arranger triangle frames (match `process_all_tracks`' triangle contract), or set it to the engine's real on-value constant with a comment that consumers must ignore it.

---

## Notes on scope boundaries

- Finding 4's root cause sits in `arranger/pipeline_integration.py`;
  included here because the corruption materializes at the pitch-macro
  serialization boundary this audit is chartered to cover (base-timer vs
  frame-pitch scale agreement, #16's territory). Cross-file under
  `/audit-arranger` if published.
- `export_direct_frames`' closing size print (`(max_frame+1) * 4 *
  len(all_channels)`) over-counts noise (3 tables) and DPCM (1 table) as 4
  each — cosmetic stat inaccuracy, left to `/audit-exporters` (its
  `estimate_direct_export_size` twin counts correctly).
- The skill's preamble still lists NH-14 (#107) as "open"; the fix
  (`cmp #0` re-test after `sta`) is verified in place at all four
  tone-channel procs plus `play_dpcm` — skill prose is one sprint stale
  there (for `/audit-sync`, not a code finding).

## Suggested next step

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
```
