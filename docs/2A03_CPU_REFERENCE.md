# NES 2A03 / 2A07 CPU Reference

This document outlines the high-level architecture of the NES's central processing unit. The NTSC console uses the **RP2A03** (commonly just called 2A03), while the PAL console uses the **RP2A07**.

## 1. Core Architecture

The 2A03 is essentially a "System on a Chip" that contains:
1.  **A MOS Technology 6502 microprocessor core.**
2.  **The Audio Processing Unit (APU).**
3.  **Joypad / Controller polling circuitry.**
4.  **Direct Memory Access (DMA) units for OAM (Sprites) and DPCM audio.**

### ⚠️ Critical 6502 Quirk: No Decimal Mode
To avoid patent licensing fees during manufacturing, Nintendo intentionally severed the circuitry for Binary Coded Decimal (BCD) mode in the 6502 core.
*   **Impact:** The `SED` (Set Decimal) and `CLD` (Clear Decimal) instructions still exist and modify the status flag, but they have **zero effect** on `ADC` and `SBC` math operations. All arithmetic on the NES is strictly hexadecimal.

---

## 2. Register Map ($4000 - $401F)

Unlike the PPU (which mirrors its registers across `$2000-$3FFF`), the 2A03 completely decodes its addresses. This means the CPU registers exclusively occupy `$4000-$401F`, and the entire space from `$4020` through `$FFFF` is completely free for the Game Pak (Cartridge / Mapper) to use.

| Address | Name | Read / Write | Description |
| :--- | :--- | :--- | :--- |
| **$4000-$4003** | `SQ1_xxx` | Write Only | Pulse 1 (Square) Audio Channel |
| **$4004-$4007** | `SQ2_xxx` | Write Only | Pulse 2 (Square) Audio Channel |
| **$4008-$400B** | `TRI_xxx` | Write Only | Triangle Audio Channel (Note: $4009 is unused) |
| **$400C-$400F** | `NOISE_xxx` | Write Only | Noise Audio Channel (Note: $400D is unused) |
| **$4010-$4013** | `DMC_xxx` | Write Only | DPCM / Delta Modulation Audio Channel |
| **$4014** | `OAMDMA` | Write Only | Triggers 256-byte DMA copy to PPU OAM |
| **$4015** | `SND_CHN` | Read / Write | APU Channel Enable (Write) / APU Status (Read) |
| **$4016** | `JOY1` | Read / Write | Joystick Strobe (Write) / Joystick 1 Data (Read) |
| **$4017** | `JOY2` | Read / Write | Frame Counter Control (Write) / Joystick 2 Data (Read) |
| **$4018-$401A** | *(Test)* | *(Disabled)* | APU test functionality (disabled in retail consoles) |
| **$401C-$401F** | *(Timer)* | *(Disabled)* | Unfinished IRQ timer (disabled in retail consoles) |

---

## 3. The Unused / Test Registers ($4018 - $401F)

The range `$4018-$401F` was intended for 2A03 functionality (like an IRQ timer) that never made it to production. These registers do absolutely nothing on a retail NES.

*   **Writing:** Mappers and expansion chips are free to place writable registers in this space (e.g., Famicom Disk System uses some of this space) without conflicting with the 2A03.
*   **Reading:** Placing *readable* registers here should be avoided by hardware developers because reading from these addresses can trigger bugs and conflicts with the DMA unit.

---

## 4. Engine Implementation Notes (midi2nes)

*   **Hexadecimal Math:** Because the 2A03 lacks Decimal mode, our 6502 audio sequencer (`music.asm`) must rely on standard binary/hex math for all timer calculations, note lengths, and frame counters. 
*   **Memory Map:** 
    *   RAM: `$0000-$07FF` (Our zero-page variables and shadow registers go here).
    *   APU: `$4000-$4017` (Our driver writes here).
    *   Expansion: `$4020-$5FFF` (Often unused, occasionally holds extra RAM).
    *   SRAM / PRG-RAM: `$6000-$7FFF` (Available if our MMC1 mapper is configured to enable it).
    *   PRG-ROM: `$8000-$FFFF` (Where our bytecode, instruments, and DPCM samples live).
*   **Open Bus:** Most APU registers are write-only. Reading from `$4000-$4013` results in "Open Bus" behavior (returning the last value floating on the CPU data lines rather than the register's actual state). Therefore, our audio driver must track its own state in `apu_shadow` variables in RAM.