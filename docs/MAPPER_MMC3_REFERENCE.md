# NES MMC3 Mapper Reference

This document details the hardware behavior of the Nintendo MMC3 Mapper (iNES Mapper 004). The MMC3 is one of the most advanced and widely used ASICs on the NES, supporting up to 512KB of PRG-ROM and featuring a scanline-based IRQ counter.

## 1. Memory Map & Bank Windows

Unlike the MMC1's large 16KB PRG windows, the MMC3 divides PRG-ROM into finer **8KB windows**.

*   **CPU `$6000-$7FFF`:** 8KB PRG-RAM (optional, battery backed)
*   **CPU `$8000-$9FFF`:** 8KB Switchable PRG-ROM (or fixed to second-last bank)
*   **CPU `$A000-$BFFF`:** 8KB Switchable PRG-ROM
*   **CPU `$C000-$DFFF`:** 8KB Fixed to second-last bank (or switchable)
*   **CPU `$E000-$FFFF`:** 8KB Fixed to the LAST bank

---

## 2. Register Map

The MMC3 uses 4 pairs of registers mapped to `$8000-$FFFF`. Even addresses select the low register, odd addresses select the high register. (Unlike MMC1, writes take effect instantly without a serial shift register).

### Bank Select ($8000, Even)
| Bitfield | Description |
| :--- | :--- |
| `CPMx xRRR` | **C**: CHR A12 Inversion (Swaps 2KB and 1KB CHR windows)<br>**P**: PRG-ROM Bank Mode (0 = `$8000` swappable, 1 = `$C000` swappable)<br>**R**: Selects which bank register (0-7) to update on the next write to `$8001`. |

### Bank Data ($8001, Odd)
Writes the actual bank number to the register selected by the `R` bits in `$8000`.
*   `R6`: Updates the 8KB PRG bank at `$8000` (or `$C000`).
*   `R7`: Updates the 8KB PRG bank at `$A000`.

### Mirroring & RAM Protect ($A000 / $A001)
*   **`$A000`**: Nametable arrangement (0 = Vertical, 1 = Horizontal).
*   **`$A001`**: PRG-RAM Protect (Bit 7: 1 = Deny writes, Bit 6: 1 = Enable RAM).

### Scanline IRQ Counter ($C000 - $E001)
The MMC3 features an internal counter driven by the PPU's A12 line (which toggles when fetching sprites vs. background tiles).
*   **`$C000`**: IRQ Latch (Reload value).
*   **`$C001`**: IRQ Reload (Forces the counter to reload from the latch on the next scanline).
*   **`$E000`**: IRQ Disable (Acknowledges and disables interrupts).
*   **`$E001`**: IRQ Enable (Allows the counter to trigger CPU IRQs).

---

## 3. PRG-ROM Bank Modes (The `P` bit in $8000)

The `P` bit (Bit 6) of `$8000` dictates how the PRG-ROM windows behave:

### Mode 0 (P = 0)
*   `$8000-$9FFF`: **Swappable** (via `R6`)
*   `$A000-$BFFF`: **Swappable** (via `R7`)
*   `$C000-$DFFF`: Fixed to second-to-last bank
*   `$E000-$FFFF`: Fixed to last bank

### Mode 1 (P = 1)
*   `$8000-$9FFF`: Fixed to second-to-last bank
*   `$A000-$BFFF`: **Swappable** (via `R7`)
*   `$C000-$DFFF`: **Swappable** (via `R6`)
*   `$E000-$FFFF`: Fixed to last bank

---

## 4. Engine Implementation Notes: MMC1 vs MMC3 for midi2nes

If we choose to use MMC3 over MMC1 for the `midi2nes` engine, we must carefully consider how it affects our massive DPCM drum libraries.

### The DPCM Constraint on MMC3
DPCM samples **must** play from the `$C000-$FFFF` memory range. 
*   **On MMC1 (Mode 2):** The entire 16KB window from `$C000-$FFFF` is fully swappable as a single chunk.
*   **On MMC3 (Mode 1):** Only the 8KB window from `$C000-$DFFF` is swappable. The top 8KB (`$E000-$FFFF`) is **permanently fixed** to the last bank of the ROM (which contains our reset vectors and core engine code).

**What this means:**
If we use MMC3, a single bank-switched DPCM drum kit can only be 8KB large, and all dynamically swapped samples must reside in the `$C000-$DFFF` window. Since the maximum size of a single DPCM sample is ~4KB (4081 bytes), an 8KB window is completely sufficient to hold samples. The driver will just swap 8KB chunks via register `R6` instead of 16KB chunks.

### Advantages of MMC3 for Audio
1.  **Instant Bank Switching:** MMC3 does not require a 5-write serial routine like MMC1. Bank switching takes exactly two instructions (`STA $8000`, `STA $8001`), taking a fraction of the CPU cycles.
2.  **Scanline IRQ Timers:** The MMC3 IRQ counter could theoretically be used to trigger audio updates multiple times per frame, allowing for extremely high-frequency software pitch envelopes or sample playback (though usually, NMI at 60Hz is preferred for standard music engines).

### MMC3 Bank Layout Strategy
If `midi2nes` targets MMC3:
1.  **`$E000-$FFFF` (Fixed):** 6502 Audio Driver (`music.asm`), NMI handlers, and Note lookup tables.
2.  **`$C000-$DFFF` (Swappable):** DPCM Sample Banks (swapped via `R6`).
3.  **`$A000-$BFFF` (Swappable):** Pattern Data / Macro Bytecode (swapped via `R7`).
4.  **`$8000-$9FFF` (Fixed to second-last):** Additional engine logic, config, or extra fixed instruments.