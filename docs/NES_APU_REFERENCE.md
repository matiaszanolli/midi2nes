# NES APU Hardware Reference

This document serves as the hardware baseline for the `midi2nes` audio engine. It outlines the capabilities, registers, and specific quirks of the NES RP2A03/RP2A07 Audio Processing Unit (APU) that dictate how our driver must interface with the hardware.

## 1. APU Overview
The APU features five distinct channels mapped to CPU registers `$4000-$4013`. Global status and timing are controlled via `$4015` and `$4017`.

*   **Pulse 1 & 2:** Variable-width square waves with volume and frequency control.
*   **Triangle:** Quantized 4-bit triangle wave (one octave lower than pulse). No volume control.
*   **Noise:** Pseudo-random bit generator for percussion and effects.
*   **DMC (Delta Modulation Channel):** 7-bit DPCM sample playback.

---

## 2. Channel Specifications & Constraints

### 2.1 Pulse Channels ($4000–$4007)
*   **Duty Cycles:** 12.5%, 25%, 50%, and 25% negated (75%).
*   **Volume:** 4-bit value (0-15). The APU has hardware envelopes, but for a macro-driven engine, we must set the **Constant Volume flag (`C=1`)** and write volume changes manually per frame.
*   **Frequency:** 11-bit timer value.
    *   `f = fCPU / (16 * (t + 1))`
    *   If `t < 8`, the channel is silenced.
*   **⚠️ CRITICAL QUIRK - The Phase Reset Click:** 
    Writing to `$4003` or `$4007` (Timer High) restarts the phase of the pulse generator. Continuous writes to these registers (e.g., for vibrato or pitch slides) will cause an audible clicking/popping noise. 
    *   **Engine Implementation:** Our pitch macros (vibrato/portamento) must only manipulate `$4002`/`$4006` (Timer Low), unless a pitch slide crosses an 8-bit boundary, requiring a High byte update.

### 2.2 Triangle Channel ($4008–$400B)
*   **Pitch:** One octave below the pulse channels for an equivalent timer value.
*   **Volume:** None. The channel outputs a 32-step quantized 4-bit wave.
*   **⚠️ CRITICAL QUIRK - Silencing the Triangle:** 
    Silencing the Triangle channel merely halts it. It does not snap to 0, but outputs its last value. This can cause popping if mixed carelessly.
    *   **Engine Implementation:** To execute a "Note Off" for the Triangle, we write `$00` to `$4008` (Linear Counter) or set a frequency of `t < 8` to halt it safely.
*   **Phase:** There is no way to reset the Triangle channel's phase.

### 2.3 Noise Channel ($400C–$400F)
*   **Frequency:** Determined by a 4-bit index in `$400E` addressing a lookup table.
*   **Mode:** Bit 7 of `$400E` switches the generator from white noise to a short-period LFSR, producing a metallic buzzing tone.
*   **Volume:** Same as Pulse; we use Constant Volume (`C=1`) and drive it via software macros.

### 2.4 DMC / DPCM Channel ($4010–$4013)
Outputs a 7-bit PCM signal driven by 1-bit delta samples.
*   **⚠️ CRITICAL QUIRK - Memory Constraints:**
    DPCM samples **must** reside in the `$C000–$FFFF` memory range.
    *   Address calculation: `%11AAAAAA AA000000` (64-byte alignment).
    *   Length calculation: `%LLLL LLLL0001` (16-byte steps).
*   **Engine Implementation:** Because `midi2nes` supports massive drum kits (`dpcm_index.json`), our engine needs an intelligent bank-switching mapper (like MMC3 or specific MMC1 setups) to swap sample banks into the `$C000` window dynamically if the samples exceed the available PRG space.

---

## 3. Global Control

### 3.1 Status Register ($4015)
*   Controls which channels are enabled (`---D NT21`).
*   Writing `0` to a channel's bit silences it immediately and halts its length counter.

### 3.2 Frame Counter ($4017)
*   Controls the APU's internal sequencers (envelopes, length counters, sweep).
*   **Engine Implementation:** Since we are building a software macro engine, we will bypass the hardware envelopes entirely. However, we must initialize `$4017` to `$40` (Mode 1, 5-step, disable frame interrupt) to prevent the APU from interfering with our NMI-driven 60Hz audio updates.

---

## 4. Shadow APU Registers (Engine Design)
Because updating registers directly throughout the CPU frame can cause tearing or popping, our 6502 engine will use **Shadow Registers**. 
1. During the NMI, the sequencer and macro engine calculate all audio changes and write them to a block of RAM (`apu_shadow`).
2. At the end of the calculations, the entire `apu_shadow` block is blasted to `$4000-$4015` in a tight loop to ensure all channels update simultaneously.