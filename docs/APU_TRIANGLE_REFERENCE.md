# NES APU Triangle Channel Reference

This document details the hardware behavior of the NES APU Triangle channel. The triangle channel generates a pseudo-triangle wave and is typically used for basslines or tom-tom drum simulation. 

Unlike the Pulse and Noise channels, the Triangle channel **has no volume control**. It is either playing at full volume or halted.

## 1. Hardware Architecture

The triangle channel features a high-accuracy duration timer (Linear Counter) in addition to the standard Length Counter.

**Signal Flow:**
```text
      Linear Counter   Length Counter
            |                |
            v                v
Timer ---> Gate ----------> Gate ---> Sequencer ---> (to mixer)
```

---

## 2. Register Map (Write-Only)

| Register | Bitfield      | Description |
| :---     | :---          | :--- |
| `$4008`  | `CRRR.RRRR`   | **C**: Control flag / Length counter halt<br>**R**: Linear counter reload value |
| `$400A`  | `LLLL.LLLL`   | Timer Low 8 bits |
| `$400B`  | `llll.lHHH`   | **l**: Length counter load<br>**H**: Timer High 3 bits<br>*Side effect: Sets the linear counter reload flag* |

---

## 3. Sequencer & Timer Behavior

Unlike the pulse channels, the triangle channel's timer is clocked at the full CPU clock rate (`fCPU`), not CPU/2. 

*   **Formula:** `f = fCPU / (32 * (tval + 1))`
*   **Timer Range:** The triangle channel supports frequencies up to ~55.9 kHz (NTSC), which is far above human hearing. 
*   **Waveform:** The sequencer sends a 32-step sequence to the mixer: 
    `15, 14, ..., 0, 0, 1, ..., 15`
*   **Phase:** There is no way to reset the Triangle channel's phase. Writing to `$400B` does not cause the "phase click" associated with the Pulse channels.

---

## 4. The Linear Counter

The Linear Counter provides higher resolution duration control than the standard Length Counter. It is clocked by the APU Frame Counter.

When the frame counter generates a clock tick:
1.  If the *reload flag* is set, the linear counter is loaded with the value `R` (from `$4008`).
2.  Otherwise, if the linear counter is non-zero, it is decremented.
3.  If the *control flag* (`C`) is clear (0), the *reload flag* is cleared.

*(Note: The reload flag is set by writing to `$400B`.)*

---

## 5. Silencing the Triangle (The Popping Problem)

Because the triangle channel has no volume control, silencing it requires stopping the sequencer. Depending on the method used, this can cause an audible "pop" because the waveform halts at its current amplitude (0-15) rather than returning to 0.

### Method 1: Linear Counter Halt (Recommended)
*   Write `$80` to `$4008`. This sets `C=1` and `R=0`. 
*   On the next frame counter tick, the linear counter reloads to 0, halting the channel in its current position.
*   *Pros:* Safest method to avoid hard pops.
*   *Cons:* Can have up to a 1/4 frame delay before silencing.

### Method 2: Ultrasonic Pitch (The Mega Man Method)
*   Write a period value of `0` or `1` to `$400A`/`$400B`.
*   The channel outputs an extremely high frequency. The console's lowpass filter averages this to a steady value of `~7.5`.
*   *Pros:* Instant silence.
*   *Cons:* Causes a noticeable, hard popping noise when transitioning to/from this state (e.g., *Mega Man 2*).

### Method 3: Status Register ($4015)
*   Clear the triangle bit in `$4015`.
*   *Pros:* Instant stop.
*   *Cons:* Dangerous when using DPCM samples, as writing to `$4015` can interfere with active DPCM playback if not handled perfectly.

---

## 6. Engine Implementation Notes (midi2nes)

*   **Note Off Handling:** Our macro engine's sequencer should use **Method 1** (writing `$80` to `$4008`) to execute a "Note Off" command for the Triangle channel to minimize popping. To resume a note, we simply write `$FF` (or the desired control value) back to `$4008`.
*   **Volume Envelopes:** Since there is no hardware volume control, any Software Volume Envelopes defined in our Instruments will be ignored by the Triangle channel. We may choose to route volume macros to control the Linear Counter duration instead (pseudo-envelopes), or just treat it as a binary ON/OFF.
*   **DMC Interference:** The mixer documentation notes that the DMC level has a noticeable effect on the triangle's level. We do not need to correct this in software, but it is an authentic NES hardware quirk that will naturally color our drum-heavy tracks.
*   **Pitch Slides:** Because writing `$400B` does not reset the phase, we can freely slide the pitch using both the high and low timer registers if our pitch macros exceed the 8-bit boundary of `$400A`, without fearing the phase reset click of the pulse channels.