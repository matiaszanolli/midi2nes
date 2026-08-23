# Audio Engine Bytecode & Macro Specification

This document defines the architecture and bytecode specification for the `midi2nes` 6502 audio driver. To achieve "Tim Follin grade" audio, we are moving from a literal frame-by-frame data dump to a **Macro-Driven Bytecode Interpreter**.

## 1. Engine Architecture

The audio driver runs during the NES NMI (60Hz NTSC) and consists of two main components:

1.  **The Sequencer:** Reads compressed streams of bytecode (patterns). Handles note triggers, rests, instrument changes, and control flow (loops, jumps).
2.  **The Macro Engine (Synthesizer):** Once a note triggers an "Instrument", the Macro Engine takes over. Every frame, it reads sequence tables (Macros) to apply Volume Envelopes, Pitch Slides (Vibrato/Portamento), Arpeggios, and Duty Cycle sweeps to the base note.

---

## 2. ROM Data Structures

The Python compiler will export assembly data in the following hierarchy:

### 2.1 The Song Header
Points to the initial bytecode streams for all 5 channels, plus the tempo configuration.
```ca65
song_00_header:
    .word sq1_stream, sq2_stream, tri_stream, noi_stream, dmc_stream
    .byte INITIAL_TEMPO
```

**Per-channel starting bank.** When a song's total sequence bytecode outgrows one 8&nbsp;KB
MMC3 swap bank, later channels' `*_sequence` labels are emitted into `BANK_01`+. A channel's
stream pointer alone is therefore not enough — the engine must also know which bank each
channel *starts* in (the within-stream `$FE CMD_BANK_JUMP` only updates the bank mid-stream).
The exporter emits a 5-byte `channel_start_banks` table (indices `0..4` =
pulse1/pulse2/triangle/noise/dpcm) into the fixed `CODE_8000` bank and `.export`s it;
`audio_init` seeds `stream_bank+0..+4` from it instead of assuming bank 0 (#328/EXP-13).
```ca65
channel_start_banks:
    .byte $00, $02, $02, $02, $02 ; pulse1, pulse2, triangle, noise, dpcm
```

### 2.2 Instruments
An instrument is simply a table of pointers to specific Macro streams.
```ca65
instrument_table:
    ;     Vol Macro,     Arp Macro,    Pitch Macro,   Duty Macro
    .word vol_fade_in,   arp_major,    pitch_vib_fast, duty_sweep
```
*(If an instrument doesn't use a specific macro, it points to a standard `macro_null` which applies 0 offset).*

**Instrument count is capped at 32** (ids `$00`-`$1F`). Each row is 8 bytes
(4 macro pointers), and the engine's `EVAL_MACRO` (`nes/audio_engine.asm`)
addresses `instrument_table` with `current_inst * 8` computed in an 8-bit
accumulator and indexed with 8-bit `Y` -- id 32 would alias to id 0's row,
33 to id 1's, and so on, with no error. The exporter's `_register_instrument`
enforces this limit at build time (#425/NH-HW-2026-08-21-1).

### 2.3 Macros
Macros are lists of offsets or absolute values evaluated frame-by-frame.
*   **Volume Macros:** Absolute values (0-15).
*   **Arpeggio Macros:** Half-step offsets from the base note (e.g., `0, 4, 7, 12`).
*   **Pitch Macros:** Fine-tuning offsets added to the raw APU timer value.
*   **Control Bytes in Macros:**
    *   `$FF`: End of macro (sustain last value). The only control byte the
        live evaluator (`EVAL_MACRO` in `nes/audio_engine.asm`) implements.
    *   `$FE, <offset>`: Loop macro back to offset. **Reserved for a future
        implementation, not currently functional** — `_compress_macro`
        (`exporter/exporter_ca65.py`) does not emit it, and `EVAL_MACRO` has
        no branch for it (a `$FE` byte would be misread as ordinary data,
        desyncing the stream). A prior version of the exporter did emit
        `$FE` when loop compression won on size, which the engine could not
        decode (#163/NH-21) — loop compression was removed rather than
        implementing the engine side, since no producer currently emits
        non-constant macros that would benefit from it.
*   **Reserved data values:** Because `$FF`/`$FE` are control bytes, signed
    pitch/arp *data* offsets may never encode to them (even though `$FE` is
    not currently emitted as a control byte, the reservation is kept so a
    future loop implementation doesn't have to re-derive this). The exporter
    snaps the two colliding offsets to the nearest non-reserved byte — `-1`
    (`$FF`) → `0` (`$00`) and `-2` (`$FE`) → `-3` (`$FD`) — so a small
    downward bend can never be misread as an end/loop command mid-macro. For
    pitch these are period-unit deltas, so the ≤1-unit nudge is sub-cent and
    inaudible. (#77)

### 2.4 Multi-Song Jukebox Tables

A `song build` (#30/F-13) ROM replaces the single-song `channel_start_banks`
table (§2.1) with a lookup keyed by song index, since a jukebox has more than
one set of five channel streams and instrument tables. The single-song and
jukebox tables are mutually exclusive — `nes/project_builder.py` selects
between them at build time via the `JUKEBOX_BUILD` symbol
(`song_count is not None`).

`CA65Exporter.export_song_bank_bytecode` (`exporter/exporter_ca65.py`) emits
one set of instrument/macro tables and sequence streams per song, with every
symbol a song defines prefixed `song{i}_` (`song0_instrument_table`,
`song0_pulse1_sequence`, etc. — no cross-song dedup). Two lookup tables tie
the per-song labels to a runtime song index:

**`song_table_ptr_lo` / `song_table_ptr_hi` / `song_table_bank`** — three
parallel byte arrays, one entry per `(song, channel)` pair, indexed
`song_index * 5 + channel` (channel order fixed by `SEQUENCE_CHANNELS`:
pulse1, pulse2, triangle, noise, dpcm). Emitted into the fixed `CODE_8000`
bank so they're readable without a bank swap regardless of which `BANK_NN`
each song's sequence data physically landed in.
```ca65
song_table_ptr_lo:
    .byte <song0_pulse1_sequence, <song0_pulse2_sequence, <song0_triangle_sequence, <song0_noise_sequence, <song0_dpcm_sequence, <song1_pulse1_sequence, ...
song_table_ptr_hi:
    .byte >song0_pulse1_sequence, >song0_pulse2_sequence, ...
song_table_bank:
    .byte $00, $00, $00, $00, $00, $01, ...  ; the BANK_NN each label landed in
song_count:
    .byte $02  ; total songs in this ROM
```
`song_count` is capped at **51** (`(255 - 4) // 5 + 1`): the engine's
`load_song_streams_indexed` computes `song_index * 5` on an 8-bit
accumulator with no native multiply (`current_song*4 + current_song`), so a
52nd song's index would silently wrap. `export_song_bank_bytecode` raises
`ValueError` before emitting a bank over this limit (#426).

**`song_instrument_ptr_lo` / `song_instrument_ptr_hi`** — one entry **per
song**, not per channel (unlike the three arrays above) — since
`EVAL_MACRO` indirects through a single `instrument_table_ptr` variable
rather than a fixed `instrument_table` label, and each song's instrument
table needs its own pointer regardless of channel.
```ca65
song_instrument_ptr_lo:
    .byte <song0_instrument_table, <song1_instrument_table
song_instrument_ptr_hi:
    .byte >song0_instrument_table, >song1_instrument_table
```

**Consumer**: `nes/audio_engine.asm`'s `load_song_streams_indexed`, called
from `audio_init_song` (cold boot, always song 0) and `audio_advance_song`
(end-of-song transition) whenever `current_song` changes. It seeds
`instrument_table_ptr` from `song_instrument_ptr_*` at index `current_song`
alone, then copies all five channels' `stream_ptr_lo/hi`/`stream_bank` from
`song_table_ptr_*`/`song_table_bank` starting at index `current_song * 5`.

---

## 3. Bytecode Specification (The Sequencer Stream)

To minimize ROM footprint, the sequence stream uses a tightly packed command format. Bytes are evaluated sequentially.

### Note Range ($00 - $5F)
Values `$00` through `$5F` (0-95) represent notes to be played. 
*   **$00:** Note Off (Rest/Release).
*   **$01 - $5F:** Notes (C-1 to B-7). Triggers the current instrument and resets all macro pointers to 0 — **unless the note byte is identical to the note already playing on this channel**, in which case it is a tie/continuation instead of a new onset: macro pointers keep running and the pulse channels' `$4003`/`$4007` phase-reset is skipped (only `frame_wait` reloads from the current `Note Length` state). There is no dedicated tie/continuation opcode; a same-value note byte *is* the tie encoding. This exists because the Length byte's 6-bit field caps a single note at 32 frames (see below) — the exporter (`exporter/exporter_ca65.py`'s `_build_song_bytecode`) chunks any longer held note into consecutive `(Length, Note)` pairs that repeat the same note value, and the engine (`nes/audio_engine.asm`'s `@is_note`) must treat those repeats as one continuous note rather than re-triggering every 32 frames (#439/EXP-2026-08-21-1).

*When a note is read, the engine waits for the duration specified by the current `Note Length` state before reading the next byte.*

### Length Commands ($60 - $7F)
Changes the default length of subsequent notes.
*   **$60 - $7F:** Sets the Note Length state to `value - $60 + 1` frames.
    *   *Example:* `$6F` sets the duration of all following notes to 16 frames.

### Engine Commands ($80 - $FF)
Control flow, instruments, and effects. These commands are processed instantly, and the sequencer continues reading the next byte on the same frame.

This table lists only what `nes/audio_engine.asm`'s sequencer dispatch actually
decodes (any other byte in this range falls through to `@unknown_command`,
which halts the sequence) — it previously listed several commands
(`CMD_TEMPO`, `CMD_CALL_PATTERN`, `CMD_RETURN`, `CMD_JUMP`, `CMD_SET_VOLUME`)
the engine never implemented, and once omitted `$FE`, a real, working opcode
(#83/EXP-07). `$87`/`CMD_DMC_LEVEL` was also real and working when #83 wrote
this table (2026-07-04) — its `@cmd_dmc_level` handler was later deleted as
unreachable dead code (#309, 2026-07-17; no producer had emitted `$87` since
#72 removed its only source), which silently made this table wrong again
until now (#508/EXP-2026-08-23-1). The row below reflects the current,
**not implemented** state.

| Byte | Command | Parameter(s) | Description |
| :--- | :--- | :--- | :--- |
| **$80** | `CMD_INSTRUMENT` | `[id]` | Sets the current instrument to `id`. |
| **$85** | `CMD_DPCM_PLAY` | `[sample_id]` | Triggers a DPCM sample from the index. Implemented in the engine; the Python exporter does not currently emit it (DPCM sample triggers are encoded as regular note bytes instead — see `arranger/pipeline_integration.py`'s DPCM frame conversion). |
| **$87** | `CMD_DMC_LEVEL` | `[level]` | **Not implemented.** Falls through to `@unknown_command` and halts the sequence like any other undecoded byte — the `@cmd_dmc_level` handler that once wrote a 7-bit DMC output level (`level & $7F`) to `$4011` was removed as dead code (#309); no exporter path emits `$87`. Restore the handler before ever emitting this byte, or continue treating it as reserved/unimplemented like the in-macro `$FE` loop byte (§2.3). |
| **$FE** | `CMD_BANK_JUMP` | `[bank, ptr_lo, ptr_hi]` | *Sequence-level*: switches the MMC3 swappable PRG bank and continues reading from the given pointer, for songs whose bytecode outgrows one 8KB bank. **Distinct from the in-macro `$FE, <offset>` loop control byte (§2.3)** — the two share a byte value but live in separate streams (sequence vs. macro), so there is no decoding ambiguity at runtime. |

---

## 4. Flow of Execution (NMI Loop)

1.  **Tick Channel Timers:** Decrement the `frame_wait` counter for each channel.
2.  **Sequencer Phase:** For each channel where `frame_wait == 0`:
    *   Fetch a byte from the stream.
    *   If it's a Command (`$80+`), execute it, fetch the next byte.
    *   If it's a Length (`$60-$7F`), update internal length state, fetch next byte.
    *   If it's a Note (`$00-$5F`), calculate base frequency, reset macro indices, set `frame_wait = current_length`. Stop fetching.
3.  **Synthesizer Phase (Macros):**
    *   Read `Volume Macro` at current index. Calculate final volume.
    *   Read `Arpeggio Macro` at current index. Add semitone offset to base note.
    *   Lookup the NTSC APU timer value for the new note.
    *   Read `Pitch Macro` at current index. Add/subtract from APU timer.
    *   Read `Duty Macro` at current index.
    *   Advance all macro indices.
4.  **Hardware Write:**
    *   Combine Volume + Duty into Control Register.
    *   Write safe timer changes to `apu_shadow` registers.
    *   Flush `apu_shadow` to `$4000-$4013`.

---

## 5. Implementation Roadmap

### Step 1: The Base Engine
*   Implement the 6502 sequencer to parse Notes, Rests, and Length commands.
*   Map MIDI values to the Note Frequency Table (NTSC).
*   Output static volumes (no macros yet).

### Step 2: The Macro System
*   Implement the Instrument definition structure.
*   Implement the Volume Envelope macro parser.
*   Implement the Arpeggio macro parser (bypassing the Python arpeggiator for hardware-level chord arps).

### Step 3: Pitch & DPCM
*   Add the pitch offset macro parser (for vibrato, pitch bends, kick drum slides).
*   Implement the `CMD_DPCM_PLAY` command and bank-switching logic for `$C000` samples.