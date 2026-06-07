# NES APU Length Counter Reference

This document details the hardware behavior of the NES APU Length Counter. The length counter provides automatic duration control for the Pulse, Triangle, and Noise channels. When it reaches zero, it silences the corresponding channel.

## 1. Hardware Architecture

Each of the waveform channels (except DMC) has its own length counter. It can be enabled/disabled globally, halted, or loaded with specific duration values from a built-in lookup table.

---

## 2. Register Map (Write-Only)

| Register | Channel | Bitfield | Description |
| :--- | :--- | :--- | :--- |
| `$4015` | Global | `---d.nt21` | Enable flags for DMC, Noise, Triangle, Pulse 2, Pulse 1. Writing 0 forces the channel's length counter to 0. |
| `$4000` | Pulse 1 | `ssHc.vvvv` | **H**: Halt length counter (Bit 5). Also acts as Envelope Loop. |
| `$4004` | Pulse 2 | `ssHc.vvvv` | **H**: Halt length counter (Bit 5). |
| `$4008` | Triangle | `Hlll.llll` | **H**: Halt length counter (Bit 7). Also acts as Linear Counter control. |
| `$400C` | Noise | `--Hc.vvvv` | **H**: Halt length counter (Bit 5). |
| `$4003`, `$4007`, `$400B`, `$400F` | All | `LLLL.Lttt` | **L**: Length counter load index (Bits 7-3). |

### ⚠️ Critical Triggers
*   If a channel is disabled via `$4015`, its length counter is immediately forced to 0 (silencing it) and ignores any loads.
*   Writing to the high timer registers (`$4003`, `$4007`, `$400B`, `$400F`) loads the length counter with a value from the lookup table, provided the channel is enabled in `$4015`.

---

## 3. Clocking Behavior

The length counter is clocked by the **Half Frame Clock** (driven by the Frame Counter at `$4017`).

When the half-frame clock ticks, the length counter is decremented **UNLESS**:
1.  The length counter is already 0.
2.  The Halt flag (`H`) is set.

---

## 4. The Length Lookup Table

The 5-bit load index (`L`) does not represent a direct frame duration. Instead, it addresses a hardcoded 32-byte lookup table inside the APU.

The table contains a mix of linear durations and musical note lengths (based on specific BPMs). 
*   **Odd indices** (`L` bit 0 is 1): Provide linear length values (e.g., 2, 4, 6, 8... up to 30, plus 254).
*   **Even indices** (`L` bit 0 is 0): Provide musical note lengths. 
    *   If `L` bit 4 is 1: Base length 12 (4/4 at 75 BPM). Contains values for whole notes, half notes, triplets, etc.
    *   If `L` bit 4 is 0: Base length 10 (4/4 at 90 BPM). 

---

## 5. Engine Implementation Notes (midi2nes)

*   **Bypassing the Hardware Length Counter:** The hardware length counter is highly restrictive (limited to the 32 specific values in the lookup table and clocked at a low 120Hz/96Hz rate). To achieve precise, tracker-like note durations, our 60Hz Macro Sequencer will **bypass the hardware length counter entirely**.
*   **Halt Flags Always Set:** To prevent the APU from prematurely silencing our notes, we will always set the Halt flag (`H=1`) when writing to `$4000`, `$4004`, `$4008`, and `$400C`. 
    *   *Note:* This aligns perfectly with our Envelope generator strategy, where setting the Constant Volume flag / Envelope Loop effectively halts the length counter as well!
*   **Global Enable:** Our initialization routine must write `%00001111` (`$0F`) to `$4015` at startup to enable the Pulse, Triangle, and Noise channels, otherwise they will remain permanently silenced at 0 length.
*   **Software Note-Off:** Instead of relying on this lookup table, the 6502 sequencer will count frames in software based on our custom Length Commands (`$60 - $7F`). When a note expires, the sequencer will manually write a volume of 0 to the channel's control register (or `$80` to `$4008` for the Triangle).