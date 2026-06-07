# NES APU Envelope Generator Reference

This document details the hardware behavior of the NES APU Envelope Generator. The envelope generator controls the volume output of the Pulse 1, Pulse 2, and Noise channels. The Triangle and DMC channels do not use this envelope unit.

## 1. Hardware Architecture

Each volume envelope unit can operate in one of two modes:
1.  **Hardware Decay:** Generates a decreasing saw-tooth envelope (a linear volume decay from 15 down to 0).
2.  **Constant Volume:** Bypasses the decay and outputs a static 4-bit volume value.

The unit contains a start flag, a divider, and a decay level counter.

**Signal Flow:**
```text
                                   Loop flag
                                        |
               Start flag  +--------.   |   Constant volume
                           |        |   |        flag
                           v        v   v          |
Quarter frame clock --> Divider --> Decay --> |    | 
                           ^        level     |    v
                           |                  | Select --> Envelope output
                           |                  |
        Envelope parameter +----------------> |                   
```

---

## 2. Register Map (Write-Only)

| Register | Channel | Bitfield      | Description |
| :---     | :---    | :---          | :--- |
| `$4000`  | Pulse 1 | `ddLC.VVVV`   | **L**: Envelope loop / Length counter halt<br>**C**: Constant volume flag (1 = Constant, 0 = Hardware Envelope)<br>**V**: Volume level OR Envelope divider period |
| `$4004`  | Pulse 2 | `ddLC.VVVV`   | *(Same as Pulse 1)* |
| `$400C`  | Noise   | `--LC.VVVV`   | *(Same as Pulse 1)* |

### ⚠️ Trigger Registers
Writing to the Timer High / Length Counter registers triggers the envelope to restart.
*   `$4003` (Pulse 1)
*   `$4007` (Pulse 2)
*   `$400F` (Noise)

**Side effect:** Writing to these registers sets the Envelope **Start Flag**.

---

## 3. Clocking Behavior

The envelope generator is clocked by the **Quarter Frame Clock** (driven by the APU Frame Counter at `$4017`).

When a quarter frame clock occurs:
1.  **If the Start Flag is SET:**
    *   The Start Flag is cleared.
    *   The Decay Level counter is loaded with `15`.
    *   The Divider's period is immediately reloaded with `V` (so the period becomes `V + 1` quarter frames).
2.  **If the Start Flag is CLEAR:**
    *   The Divider is clocked.
    *   When the Divider clocks at `0`, it is reloaded with `V` and it clocks the Decay Level counter.
        *   If the Decay Level is `> 0`, it is decremented.
        *   If the Decay Level is `0` AND the Loop Flag (`L`) is set, the Decay Level is reloaded with `15` (creating a looping saw wave).

---

## 4. Constant Volume Output

The envelope unit's final volume output depends entirely on the **Constant Volume Flag (`C`)**:
*   If `C = 1`: The 4-bit `V` parameter directly sets the volume output (0-15).
*   If `C = 0`: The current Decay Level counter sets the volume output.

*Note: Even when Constant Volume is selected, the internal Decay Level counter is still continually updated by the quarter frame clocks in the background.*

---

## 5. Engine Implementation Notes (midi2nes)

*   **Bypassing the Hardware:** To achieve high-quality, custom ADSR envelopes (like the "Tim Follin" style), our `midi2nes` 6502 audio engine will **always set `C = 1`**.
*   **Software Macros:** Instead of relying on the hardware's fixed linear decay, our Python pipeline will generate Volume Macros (streams of 4-bit values). Our NMI audio update loop (running at 60Hz) will manually write these values into the `V` bits of `$4000`, `$4004`, and `$400C` frame-by-frame.
*   **Independence from `$4017`:** Because we use Constant Volume, we do not need to worry about synchronizing the APU Frame Counter (`$4017`) for volume purposes. We can set `$4017` to `$40` (Mode 1, disable interrupts) on startup and let our NMI dictate the volume timing perfectly.