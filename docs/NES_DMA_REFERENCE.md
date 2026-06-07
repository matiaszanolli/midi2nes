# NES 2A03 DMA (Direct Memory Access) Reference

This document details the hardware behavior of the 2A03 CPU's Direct Memory Access (DMA) units. The NES uses DMA for two purposes: copying Sprite data to the PPU (OAM DMA), and streaming sample bytes to the audio unit (DMC DMA).

Because `midi2nes` relies heavily on DPCM samples for percussion, understanding how DMC DMA interrupts and conflicts with the CPU is critical for engine stability and game integration.

## 1. DMA Cadence & CPU Halting

The DMA units cannot read/write on any cycle. They alternate between **Get (Read) cycles** and **Put (Write) cycles**, which align to the first and second halves of the APU clock.

When a DMA unit needs to fetch data, it asserts the CPU's internal `RDY` line to halt the CPU. 
*   The CPU can **only** be halted on a read cycle. If the CPU is writing, the DMA unit waits and tries again on the next cycle.
*   During the halt, the DMA unit may perform an **Alignment Cycle** (a dummy cycle) to wait for a valid "Get" cycle.

---

## 2. OAM DMA (Sprite Transfer)

Triggered by writing a page number (e.g., `$02`) to `$4014`.
*   **Behavior:** Copies 256 bytes from CPU RAM to the PPU's OAM memory.
*   **Duration:** Takes 513 or 514 CPU cycles (depending on if an alignment cycle is needed).
*   **Priority:** OAM DMA has a lower priority than DMC DMA. If the DMC needs to fetch a sample byte while OAM DMA is running, OAM DMA is briefly paused.

---

## 3. DMC DMA (DPCM Audio Transfer)

Triggered automatically when the DMC channel is active (via `$4015`) and the 1-byte sample buffer empties.
*   **Behavior:** Copies a single byte from the `$C000-$FFFF` ROM space to the APU's sample buffer.
*   **Duration:** Takes 3 or 4 CPU cycles.
    *   *Load DMA* (First byte): Takes 3 cycles.
    *   *Reload DMA* (Subsequent bytes): Takes 4 cycles.

---

## 4. ⚠️ CRITICAL QUIRK - Register Conflicts (The DPCM Glitch)

This is one of the most famous hardware bugs on the NES (present on all NTSC 2A03 CPUs).

When the CPU is halted by the DMC DMA, **it indefinitely repeats the last read cycle** on the bus during the DMA dummy/alignment cycles. 
If the CPU happened to be reading a register with side-effects when it was halted, **that register will register multiple extra reads**, corrupting the data.

**Affected Registers:**
*   `$4016` / `$4017` (Controller Joypads)
*   `$2007` (PPU Data)
*   `$2002` (PPU Status)
*   `$4015` (APU Status)

### The Joypad Glitch
If a DMC DMA occurs exactly while the game is reading the controller (`$4016`), the extra reads will skip button presses, causing players to jump randomly or move in the wrong direction.

---

## 5. ⚠️ CRITICAL QUIRK - DMC DMA Abort/Extra Bugs

DMC DMA suffers from internal bugs if sample playback stops *exactly* around the time a DMA output cycle ends.
1.  **Aborted DMA:** If playback is stopped on the 2nd or 3rd CPU cycle before a Reload DMA schedules, the DMA starts but aborts after a single cycle.
2.  **Unexpected DMA:** (On newer 2A03G CPUs) If playback is stopped implicitly exactly when a Reload DMA schedules, an unexpected extra byte is fetched and played.

---

## 6. Engine Implementation Notes (midi2nes)

*   **Frequent Interruptions:** Because `midi2nes` uses a massive drum catalog (`dpcm_index.json`), the DMC DMA will be firing constantly. OAM DMA will be routinely delayed by 1-3 cycles, meaning raster effects or split-screen timing relying on cycle-counted OAM DMA will be unstable.
*   **Mandatory Controller Protection:** Any game integrating the `midi2nes` engine **must** use a DPCM-safe controller reading routine. 
    *   *Safe Read Strategy:* The game must read the joypad state, save it, read the joypad state a second time, and compare the two. If they match, the read is valid. If they don't match (meaning a DMA corrupted the read), the game must read a third time.
*   **PPU Protection:** Game developers using our engine must be warned never to read from `$2007` (VRAM) while DPCM drums are playing, as the data will likely be corrupted by the extra read glitch. (Writing to `$2007` is perfectly safe, as DMA cannot halt the CPU on a write cycle).
*   **Synchronization Limits:** Because the DPCM timer is completely disconnected from the PPU, and DMC DMAs steal variable amounts of cycles (3-4), absolute cycle-perfect game logic is virtually impossible while `midi2nes` percussion is active.