# NES APU Frame Counter Reference

This document details the hardware behavior of the NES APU Frame Counter (also known as the Frame Sequencer). 

Despite its name, the frame counter is completely independent of the PPU (video) frame rate. It generates low-frequency internal clocks (Quarter Frame and Half Frame signals) that drive the APU's hardware envelopes, sweeps, length counters, and the triangle channel's linear counter. It can also optionally trigger CPU Interrupts (IRQs).

## 1. Hardware Architecture

The frame counter consists of a divider, a looping clock sequencer, and a frame interrupt flag. It runs automatically, clocking every other CPU cycle (1 APU cycle = 2 CPU cycles).

### What the Clocks Control
*   **Quarter Frame:** Clocks the hardware Envelopes and the Triangle channel's Linear Counter.
*   **Half Frame:** Clocks the Length Counters and Sweep units (and also triggers a Quarter Frame clock simultaneously).

---

## 2. Register Map (Write-Only)

| Register | Bitfield      | Description |
| :---     | :---          | :--- |
| `$4017`  | `MI--.----`   | **M**: Sequencer Mode (0 = 4-step, 1 = 5-step)<br>**I**: Interrupt Inhibit Flag (1 = Disable frame interrupts) |

### ⚠️ Critical Side Effects
*   **Timer Reset:** Writing to `$4017` resets the internal sequence timer after a delay of 3 or 4 CPU cycles.
*   **Immediate Clock:** If the Mode flag (`M`) is set (1), the sequencer immediately generates both a Quarter Frame and Half Frame clock.

---

## 3. Sequencer Modes

### Mode 0: 4-Step Sequence (`M = 0`)
In this mode, the sequence is 4 steps long, looping at approximately 240 Hz (NTSC) / 200 Hz (PAL).

| Step | Action |
| :--- | :--- |
| **1** | Quarter Frame |
| **2** | Quarter Frame + Half Frame |
| **3** | Quarter Frame |
| **4** | Quarter Frame + Half Frame + **Set Interrupt Flag** |

*Note: The Interrupt Flag is only set if the Interrupt Inhibit flag (`I`) is clear (0). If set, it triggers an IRQ to the CPU.*

### Mode 1: 5-Step Sequence (`M = 1`)
In this mode, the sequence is 5 steps long, looping at approximately 192 Hz (NTSC) / 160 Hz (PAL) with uneven timing. 

| Step | Action |
| :--- | :--- |
| **1** | Quarter Frame |
| **2** | Quarter Frame + Half Frame |
| **3** | Quarter Frame |
| **4** | *(Nothing)* |
| **5** | Quarter Frame + Half Frame |

*Note: In 5-step mode, the frame interrupt flag is **never** set.*

---

## 4. Engine Implementation Notes (midi2nes)

Since `midi2nes` relies on the PPU's Non-Maskable Interrupt (NMI) to drive our 60Hz Macro Engine, we intentionally bypass most of the APU Frame Counter's automated features. 

*   **Disabling IRQs:** It is **critical** that our audio engine initialization routine writes to `$4017` with the Interrupt Inhibit flag set (`I = 1`). Failure to do so will cause the APU to constantly fire IRQs in Mode 0, which can crash the NES if an IRQ handler isn't defined.
    *   Writing `$40` (`%01000000`) sets 4-step mode, IRQ disabled.
    *   Writing `$C0` (`%11000000`) sets 5-step mode, IRQ disabled, and triggers an immediate clock.
*   **The Triangle Note-Off Delay:** As noted in the Triangle Reference, we use the Triangle's Linear Counter (`$4008`) to safely silence the channel and avoid popping. Because the Linear Counter is clocked by the Frame Counter's Quarter Frame signals, there can be up to a ~4ms (1/4 of a frame) delay between our NMI writing a Note-Off command and the Triangle channel actually going silent. This is normal and acceptable NES hardware behavior.
*   **No Hardware Envelopes/Sweeps:** Because we set the Constant Volume flag (`C=1`) on the Pulse and Noise channels and manually write pitch changes, the Frame Counter's background clocking of Envelopes and Sweeps will have no audible effect on our sound output.