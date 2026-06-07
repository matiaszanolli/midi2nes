# NES APU Pulse Channels Reference

This document details the specific hardware behavior of the NES APU Pulse (Square) channels (Pulse 1 and Pulse 2). These channels generate variable-duty pulse waves and form the melodic backbone of most NES audio.

## 1. Hardware Architecture

Each pulse channel is composed of the following internal units:
*   **Envelope Generator:** Controls the volume (either hardware decay or constant volume).
*   **Sweep Unit:** Can automatically sweep the pitch up or down over time.
*   **Timer:** An 11-bit divider that determines the wavelength (pitch).
*   **8-Step Sequencer:** Generates the actual waveform shape based on the duty cycle setting.
*   **Length Counter:** Can automatically silence the channel after a set duration.

**Signal Flow:**
```text
                 Sweep -----> Timer
                   |            |
                   |            v 
                   |        Sequencer   Length Counter
                   |            |             |
                   v            v             v
Envelope -------> Gate -----> Gate -------> Gate ---> (to mixer)
```

---

## 2. Register Map (Write-Only)

| Pulse 1 | Pulse 2 | Bitfield      | Description |
| :---    | :---    | :---          | :--- |
| `$4000` | `$4004` | `DDlc.vvvv`   | **D**: Duty Cycle<br>**l**: Length counter halt / Envelope loop<br>**c**: Constant volume flag<br>**v**: Volume / Envelope divider period |
| `$4001` | `$4005` | `EPPP.NSSS`   | Sweep unit control (Enable, Period, Negate, Shift) |
| `$4002` | `$4006` | `LLLL.LLLL`   | Timer Low 8 bits |
| `$4003` | `$4007` | `llll.lHHH`   | **l**: Length counter load<br>**H**: Timer High 3 bits |

### ⚠️ Critical Side Effects
*   Writing to `$4000`/`$4004` changes the duty cycle immediately, but **does not** reset the sequencer's current phase position.
*   Writing to `$4003`/`$4007` **immediately restarts the sequencer** at the first step of the sequence, and restarts the envelope. *This phase reset is what causes an audible "click" or "pop" if done continuously (e.g., during vibrato).*

---

## 3. Sequencer & Timer Behavior

The frequency of the pulse channel is derived from the CPU clock (`fCPU`) divided by the 11-bit timer value (`t`).

*   **Formula:** `fpulse = fCPU / (16 * (t + 1))`
    *   *NTSC fCPU:* 1.789773 MHz
    *   *PAL fCPU:* 1.662607 MHz
*   **Timer limit (`t < 8`):** If the 11-bit timer value is less than 8 (either explicitly written or caused by the sweep unit), the channel is **silenced**. This limits the maximum output frequency to ~12.4 kHz (NTSC).

---

## 4. Duty Cycles

The sequencer steps through an 8-step lookup table. Because the internal hardware counter initializes to 0 but counts *downward*, the waveform reads the table in reverse (0, 7, 6, 5, 4, 3, 2, 1).

| Duty Value | Bit Pattern (`DD`) | Output Waveform | Percentage |
| :---: | :---: | :--- | :--- |
| 0 | `%00` | `0 1 0 0 0 0 0 0` | 12.5% |
| 1 | `%01` | `0 1 1 0 0 0 0 0` | 25% |
| 2 | `%10` | `0 1 1 1 1 0 0 0` | 50% |
| 3 | `%11` | `1 0 0 1 1 1 1 1` | 25% negated (75%) |

*Note: Some Famiclone hardware swaps these duty cycles to 12.5%, 50%, 25%, and 25% negated.*

---

## 5. Mixer Output Conditions

The pulse channel sends its current volume (0-15) to the APU mixer **only** if all of the following are false. If any condition is met, the channel outputs 0 (silence):

1.  The 8-step sequencer output is 0.
2.  The sweep unit's adder overflows (sweeping to a frequency lower than the channel supports).
3.  The length counter is 0.
4.  The timer value is less than 8 (`t < 8`).

---

## 6. Differences Between Pulse 1 and Pulse 2

The hardware behavior for Pulse 1 and Pulse 2 is identical in every way **except** for how their Sweep units handle the Negate (`N`) flag:
*   **Pulse 1:** The negate mode uses one's complement.
*   **Pulse 2:** The negate mode uses two's complement.

---

## 7. Engine Implementation Notes (midi2nes)
*   **Vibrato/Portamento:** When sliding pitches in the macro engine, we must only write to `$4002`/`$4006` (Timer Low). Writing to `$4003`/`$4007` (Timer High) will reset the phase and cause popping. High byte writes should only happen on new note triggers or when crossing an 8-bit timer boundary.
*   **Software Envelopes:** We will set `DD11.vvvv` (Constant Volume flag set) to bypass the hardware envelope and length counter, allowing our 60Hz macro engine to stream custom volume values into the `vvvv` bits.
*   **Duty Cycle Sweeps:** Because writing `$4000`/`$4004` doesn't reset phase, we can safely animate the duty cycle (e.g., swapping rapidly between 25% and 50% duty) frame-by-frame without clicking.
*   **Safety Limits:** Our Python exporter and frequency tables must clamp timer values to `>= 8` to avoid unintended silencing of the channel.