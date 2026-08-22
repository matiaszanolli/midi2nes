# Issues 430, 431, 432, 433

All from `AUDIT_NES_HARDWARE_2026-08-21.md`, domain: nes-hardware. Severity: MEDIUM (all four).

---

## #430 — NH-HW-2026-08-21-2: Direct-export playback never plays the final frame table entry

**Location:**
- `exporter/exporter_ca65.py:854-863` (`play_music_frame` range guard: `cmp #<{max_frame}` /
  `bcs @done` treats `frame_counter == max_frame` as out of range)
- `exporter/exporter_ca65.py:829-841` (standalone `nmi` loop reset fires at
  `frame_counter == max_frame`)
- `exporter/exporter_ca65.py:971-983` (non-standalone `update_music`, same reset)

Frame tables are emitted with `max_frame + 1` entries (indices `0..max_frame`). But
`play_music_frame` refuses to play when `frame_counter >= max_frame` (equality included), and
both loop-reset sites reset `frame_counter` to 0 as soon as it *reaches* `max_frame` — so index
`max_frame` (the final frame) is dead: never played, on every loop. A song whose only data is on
frame 0 (`max_frame = 0`) never plays anything at all.

**Suggested fix:** play while `frame_counter <= max_frame` (e.g. `beq @in_range` on the equal
case, or compare against `max_frame + 1`); reset the loop counter when it reaches `max_frame + 1`.

---

## #431 — NH-HW-2026-08-21-4: `--arranger` sub-C1 triangle notes serialize to a detuned pitch

**Location:**
- `arranger/pipeline_integration.py:351-380` (`midi_note_to_nes_pitch` clamps only to MIDI 0-127,
  then indexes the raw table — no channel-range clamp)
- `arranger/pipeline_integration.py:314-320` (triangle frames get `pitch = table[note]` for any
  note)
- vs. `exporter/exporter_ca65.py:1212-1220` (serializer floors the stream note at 24, assuming
  the frame pitch was already clamped to the same floor — true only for the legacy front-end's
  `PitchProcessor.get_channel_pitch`, which clamps triangle to 24-96)
- `exporter/exporter_ca65.py:84-99` (`_encode_macro_offset` clamps the oversized delta to +127)

A bass note 21 (A0) on triangle in arranger mode: frame `pitch = table[21] = 2032`, but the
serializer computes `base = table[24] = 1709` (floored note), raw offset = +323, clamped to +127
→ runtime timer = 1836. Neither the intended 2032 nor the clamp target 1709 — a detuned pitch.
Pulse channels are immune by luck (timers for notes ≤28 all clamp to `$7FF`).

**Suggested fix:** clamp the note to `CHANNEL_RANGES[channel]` inside
`arranger/pipeline_integration.py`'s `midi_note_to_nes_pitch`, matching
`PitchProcessor.get_channel_pitch`, so frame `pitch` and the serializer's floored note agree.

---

## #432 — NH-HW-2026-08-21-5: Direct-export `last_*_note` state never initialized

**Location:**
- `exporter/exporter_ca65.py:666-671` (BSS: `last_pulse1_note`/`last_pulse2_note`/
  `last_triangle_note`/`last_dpcm_note`, no initializer)
- `exporter/exporter_ca65.py:764-810` (standalone `reset` — no write to them)
- `exporter/exporter_ca65.py:940-959` (non-standalone `init_music` — likewise)
- `nes/project_builder.py:441-463` (`main.asm` reset template — no RAM-clear loop)

Direct-export playback gates register writes on `cmp last_<ch>_note` / `beq @sustain`. Nothing
initializes these four BSS bytes, so on real hardware (or randomized-RAM emulators) they hold
power-on garbage. If garbage == first note's value, the note-changed test fails on the first
frame and that channel's first note (or first DPCM trigger) is silently skipped until the next
note change.

**Suggested fix:** seed all four `last_*_note` bytes with `$FF` (impossible note value) in
`reset`/`init_music`, or add a RAM-clear loop, mirroring `audio_engine.asm`'s
`last_written_hi` init.

---

## #433 — NH-HW-2026-08-21-6: Jukebox auto-advance starts some/all channels one NMI frame late

**Location:** `nes/audio_engine.asm:733-762` (`@end_of_stream` `.ifdef JUKEBOX_BUILD` block)

When the last-finishing channel `k` triggers the all-5-`channel_ended` scan mid-way through
`audio_update`'s channel loop, `audio_advance_song` reloads all stream pointers and zeroes
`frame_wait`, but execution falls through to `@silence` for channel `k` and never re-visits
channels with index ≤ `k` this frame. Channels with index > `k` fetch the new song's first byte
the same frame; channels ≤ `k` start one 60Hz tick (~16.7ms) late. In the realistic case where
noise (index 3) is longest-ringing, all four audible channels restart late.

Carry-over of `AUDIT_NES_HARDWARE_2026-08-07` finding NH-HW-2026-08-07-2 (never filed as an
issue); code unchanged since then.

**Suggested fix:** after a successful advance, re-enter the frame's dispatch for the triggering
channel (reload `sequence_ptr`/`sequence_bank` from fresh `stream_*` and `jmp @fetch_byte`), or
have `audio_update` restart its channel loop from `x = 0` once when an advance occurred this
frame.
