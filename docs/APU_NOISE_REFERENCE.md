# NES APU Noise Channel Reference

This document details the hardware behavior of the NES APU Noise channel. The noise channel generates pseudo-random 1-bit noise at 16 different frequencies and is primarily used for percussion (hi-hats, snares, crashes) and sound effects.

## 1. Hardware Architecture

The noise channel contains an envelope generator, a timer, a Linear Feedback Shift Register (LFSR), and a length counter.

**Signal Flow:**
```text
   Timer --> Shift Register   Length Counter
                   |                |
                   v                v
Envelope -------> Gate ----------> Gate --> (to mixer)
```

---

## 2. Register Map (Write-Only)

| Register | Bitfield      | Description |
| :---     | :---          | :--- |
| `$400C`  | `--lc.vvvv`   | **l**: Length counter halt / Envelope loop<br>**c**: Constant volume flag<br>**v**: Volume / Envelope divider period |
| `$400E`  | `M---.PPPP`   | **M**: Mode flag (changes noise timbre)<br>**P**: Period index (0-15) |
| `$400F`  | `llll.l---`   | **l**: Length counter load<br>*Side effect: Restarts the hardware envelope* |

---

## 3. Timer & Frequencies

The timer period is determined by the 4-bit value `P` written to `$400E`. This selects a period from a hardcoded lookup table, dictating how many CPU cycles occur between shift register clocks.

**NTSC Period Lookup Table:**
| Index (`P`) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | A | B | C | D | E | F |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Period** | 4 | 8 | 16 | 32 | 64 | 96 | 128 | 160 | 202 | 254 | 380 | 508 | 762 | 1016 | 2034 | 4068 |

*(Note: Early Famicom/Vs. System revisions had a lowest rate of 2046 instead of 4068).*

---

## 4. The Shift Register (LFSR) & Mode Flag

The core of the noise channel is a 15-bit shift register. On power-up, it is initialized to 1. When clocked by the timer, it calculates a feedback bit, shifts right by one, and inserts the feedback into bit 14.

The **Mode flag (`M` in `$400E`)** changes which bits are used for the feedback calculation (XOR of bit 0 and another bit):
*   **Mode 0 (White Noise):** Uses bit 1. The resulting sequence is 32,767 steps long, producing standard white noise (static, hisses, snares).
*   **Mode 1 (Periodic Noise):** Uses bit 6. The sequence is drastically shortened to 93 or 31 steps. This produces a harsh, metallic buzzing tone with a discernible pitch. 
    *   *The specific pitch of the 93-step sequence ranges roughly from D5 down to D1, depending on the period index `P`.*

---

## 5. Mixer Output Conditions

The noise channel sends its current volume (0-15 from the envelope or constant volume) to the APU mixer unless one of the following is true (in which case it outputs 0):
1.  **Bit 0 of the shift register is 1.** (This is what creates the "random" audio waveform).
2.  **The length counter is 0.**

*(Note: Within the APU mixer, the current level of the DMC channel has a noticeable effect on the final amplitude of the Noise channel.)*

---

## 6. Engine Implementation Notes (midi2nes)

*   **Software Envelopes:** Like the Pulse channels, we will set the Constant Volume flag (`c=1` in `$400C`) so our macro engine can stream rapid custom volume envelopes. Snare drums and hi-hats rely heavily on very sharp, exponential volume decays.
*   **Drum Mapping:** `midi2nes` maps specific MIDI percussion notes to the Noise channel. Our bytecode will need to trigger specific "Noise Instruments" that dictate the Period (`P`), Mode (`M`), and a rapid volume macro to simulate percussion strikes.
*   **Periodic Noise Instruments:** We can treat Mode 1 (`M=1`) as a unique set of pitched instruments. Since the pitches are somewhat fixed and approximately 50 cents sharp from standard A440 tuning, they are excellent for robotic sound effects or metallic percussion (like cowbells or tonal hi-hats), but difficult to use for standard melodic lines.
*   **No Phase Resets:** Unlike the Pulse channels, writing to `$400F` does not reset the phase of the waveform, it only restarts the hardware envelope and length counter. Since we bypass both, we can safely write to any Noise register on any frame without popping artifacts.