# NES APU DMC (Delta Modulation Channel) Reference

This document details the hardware behavior of the NES APU DMC (Delta Modulation Channel). The DMC is unique because it can output 1-bit delta-encoded samples (DPCM) directly from memory, or its 7-bit counter can be directly loaded for manual PCM playback. In `midi2nes`, this channel is primarily used for the heavy drum kits defined in `dpcm_index.json`.

## 1. Hardware Architecture

The DMC channel contains a memory reader, interrupt flag, sample buffer, timer, output unit, and a 7-bit output level up/down counter.

There is exactly **one** of each of those — one memory reader, one sample buffer, one output-level counter. The DMC can therefore only ever play a single sample at a time; it cannot mix ("layer") two samples together the way a software drum engine could. Triggering a second sample while one is still playing replaces it, it does not combine with it.

**Signal Flow:**
```text
                         Timer
                           |
                           v
Reader ---> Buffer ---> Shifter ---> Output level ---> (to the mixer)
```

---

## 2. Register Map (Write-Only)

| Register | Bitfield      | Description |
| :---     | :---          | :--- |
| `$4010`  | `IL--.RRRR`   | **I**: IRQ enabled flag<br>**L**: Loop flag<br>**R**: Rate index (0-15) |
| `$4011`  | `-DDD.DDDD`   | **D**: Direct load (7-bit unsigned value). Instantly sets the DMC output level. |
| `$4012`  | `AAAA.AAAA`   | **A**: Sample address. Starts in the `$C000–$FFFF` range.<br>*Formula:* `$C000 + (A * 64)` |
| `$4013`  | `LLLL.LLLL`   | **L**: Sample length in bytes.<br>*Formula:* `(L * 16) + 1 bytes` |

---

## 3. Playback Modes

### Automatic Delta-Encoded Playback
When a sample is triggered (via bit 4 of `$4015`), the memory reader fetches bytes from the sample address.
*   The timer dictates the playback rate (how many CPU cycles happen between output level changes).
*   For each bit in the shift register:
    *   If `1`, add 2 to the output level.
    *   If `0`, subtract 2 from the output level.
*   The output level clamps between 0-127 and will not wrap around.

### Direct Load / PCM Playback
Writing directly to `$4011` bypasses the memory reader and immediately forces the output level to the given 7-bit value. High-frequency writes here can play raw PCM audio (e.g., *Skate or Die 2* title screen), but this requires nearly 100% of the CPU's processing time.

---

## 4. Memory constraints & Quirk: The $8000 Wrap

Samples **must** originate in the PRG-ROM space starting at `$C000`. 
*   Address calculation forces a 64-byte alignment (`%11AAAAAA AA000000`).
*   Length calculation forces a 16-byte alignment plus 1 (`%LLLL LLLL0001`).

**⚠️ CRITICAL QUIRK - Address Wrapping:** 
If a long sample crosses the end of memory (`$FFFF`), the address counter wraps around to **`$8000`**, *not* `$C000`. This means samples placed near the end of ROM will bleed into mapped data at `$8000`, causing garbage noise playback.

---

## 5. ⚠️ CRITICAL QUIRK - DMA Controller Conflict

During automatic sample playback, the DMC's Memory Reader uses Direct Memory Access (DMA) to fetch the next byte from ROM. This stalls the CPU for 1-4 cycles.

If the CPU is stalled during an instruction that reads a register with side-effects (most notably the controller at `$4016` / `$4017` or PPU data at `$2007`), **the CPU will register multiple reads, destroying the read data.**

*This is why DPCM audio causes controller input glitches in many early NES games (e.g., Super Mario Bros. 3 map screen glitching).*

*(Note: This hardware bug was fixed in PAL 2A07 CPUs, but remains present in all NTSC 2A03 CPUs).*

---

## 6. Engine Implementation Notes (midi2nes)

*   **Memory Management:** Because we have an extensive DPCM library (`dpcm_index.json`), we must rely on a capable mapper (like MMC3 or MMC1) to bank-switch sample banks into the `$C000–$FFFF` window on demand. 
*   **Bytecode Triggers:** The `midi2nes` macro engine sequencer will implement a custom command (e.g., `CMD_DPCM_PLAY <sample_id>`). When encountered, the 6502 engine will:
    1. Map the appropriate PRG bank containing the sample.
    2. Write the predefined pitch/rate to `$4010`.
    3. Write the pre-calculated 64-byte aligned offset to `$4012`.
    4. Write the pre-calculated 16-byte aligned length to `$4013`.
    5. Write `$10` to `$4015` to trigger playback.
*   **Warning for Game Developers:** Because the `midi2nes` engine will be playing massive amounts of DPCM, it will heavily trigger the DMA Controller Conflict glitch. We should provide a standard "Safe Controller Read" macro (which reads `$4016` twice and compares the results) for users wanting to integrate our audio engine into actual games.
*   **Non-linear Mixer Trick:** Because of how the NES APU mixes audio, the current value of the DMC output counter (`$4011`) inversely affects the volume of the Triangle and Noise channels. We can technically write to `$4011` to artificially lower the volume of the Triangle channel, though this is considered an advanced technique.
*   **Silence Initialization:** For safety, our engine initialization routine should write `$00` to `$4011` to ensure the DPCM counter starts at 0 and doesn't accidentally muffle the other channels.
*   **255-Distinct-Sample Ceiling Per Song:** `NESEmulatorCore.process_all_tracks` remaps the DPCM samples a song actually references to a dense, song-local `0..N-1` id (`dense_id`) so a single frame byte (`note = min(255, dense_id + 1)`) can address them without colliding with the shipped catalog's up-to-1922 raw ids. That remap itself has a byte ceiling: at 256+ distinct samples in one song, `dense_id = 255` also encodes to `note = 255`, colliding with `dense_id = 254` — every `dense_id >= 255` silently plays the 255th sample instead of its own (#343/DP-DPCM-04, warned but not prevented). Musically this ceiling is rarely reached; keep a song under 255 distinct DPCM samples to stay exact.