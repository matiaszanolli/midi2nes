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

### 2.2 Instruments
An instrument is simply a table of pointers to specific Macro streams.
```ca65
instrument_table:
    ;     Vol Macro,     Arp Macro,    Pitch Macro,   Duty Macro
    .word vol_fade_in,   arp_major,    pitch_vib_fast, duty_sweep
```
*(If an instrument doesn't use a specific macro, it points to a standard `macro_null` which applies 0 offset).*

### 2.3 Macros
Macros are lists of offsets or absolute values evaluated frame-by-frame.
*   **Volume Macros:** Absolute values (0-15).
*   **Arpeggio Macros:** Half-step offsets from the base note (e.g., `0, 4, 7, 12`).
*   **Pitch Macros:** Fine-tuning offsets added to the raw APU timer value.
*   **Control Bytes in Macros:**
    *   `$FF`: End of macro (sustain last value).
    *   `$FE, <offset>`: Loop macro back to offset.
*   **Reserved data values:** Because `$FF`/`$FE` are control bytes, signed
    pitch/arp *data* offsets may never encode to them. The exporter snaps the two
    colliding offsets to the nearest non-reserved byte — `-1` (`$FF`) → `0`
    (`$00`) and `-2` (`$FE`) → `-3` (`$FD`) — so a small downward bend can never
    be misread as an end/loop command mid-macro. For pitch these are period-unit
    deltas, so the ≤1-unit nudge is sub-cent and inaudible. (#77)

---

## 3. Bytecode Specification (The Sequencer Stream)

To minimize ROM footprint, the sequence stream uses a tightly packed command format. Bytes are evaluated sequentially.

### Note Range ($00 - $5F)
Values `$00` through `$5F` (0-95) represent notes to be played. 
*   **$00:** Note Off (Rest/Release).
*   **$01 - $5F:** Notes (C-1 to B-7). Triggers the current instrument and resets all macro pointers to 0.

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
the engine never implemented, and omitted `$87`/`$FE`, both real, working
opcodes (#83/EXP-07).

| Byte | Command | Parameter(s) | Description |
| :--- | :--- | :--- | :--- |
| **$80** | `CMD_INSTRUMENT` | `[id]` | Sets the current instrument to `id`. |
| **$85** | `CMD_DPCM_PLAY` | `[sample_id]` | Triggers a DPCM sample from the index. Implemented in the engine; the Python exporter does not currently emit it (DPCM sample triggers are encoded as regular note bytes instead — see `arranger/pipeline_integration.py`'s DPCM frame conversion). |
| **$87** | `CMD_DMC_LEVEL` | `[level]` | Writes a 7-bit DMC output level (`level & $7F`) directly to `$4011`. |
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