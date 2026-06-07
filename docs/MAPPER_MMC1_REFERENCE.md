# NES MMC1 Mapper Reference

This document details the hardware behavior of the Nintendo MMC1 Mapper (iNES Mapper 001). Because `midi2nes` supports massive DPCM drum kits that exceed the standard 32KB NES PRG-ROM limit, an advanced memory mapper is required. 

The MMC1 supports up to 256KB of PRG-ROM (or up to 512KB on SUROM/SXROM boards), making it an ideal choice for housing large audio and sample data.

## 1. The Serial Interface

Unlike most mappers which update banks with a single memory write, the MMC1 is configured through a serial port to reduce physical pin count. 

To change a register's value, the CPU must write to the mapper **five times**:
1.  The first four writes shift the least significant bit (`D0`) into an internal shift register.
2.  The fifth write copies `D0` and the shift register contents into the target internal register.

**⚠️ CRITICAL QUIRK - Mapper Reset:** 
Writing any value with Bit 7 set (`$80-$FF`) to any address in `$8000-$FFFF` immediately clears the shift register and forces the PRG-ROM bank mode to 3 (fixing the last bank at `$C000`). To save bytes, games often reset the mapper by using the `INC` instruction on a ROM location containing `$FF`.

---

## 2. Register Map

Registers are determined by bits 14 and 13 of the address on the **fifth write**.

### Control Register ($8000-$9FFF)
| Bitfield | Description |
| :--- | :--- |
| `CPPMM` | **M**: Nametable Mirroring (0=1ScA, 1=1ScB, 2=Vert, 3=Horz)<br>**P**: PRG-ROM Bank Mode (See section 3)<br>**C**: CHR-ROM Bank Mode (0=8KB, 1=4KB) |

### CHR Bank 0 ($A000-$BFFF)
Selects the 4KB or 8KB CHR bank mapped to PPU `$0000`.

### CHR Bank 1 ($C000-$DFFF)
Selects the 4KB CHR bank mapped to PPU `$1000` (ignored in 8KB mode).

### PRG Bank ($E000-$FFFF)
| Bitfield | Description |
| :--- | :--- |
| `RPPPP` | **P**: Selects the 16KB PRG-ROM bank to map into the switchable CPU window.<br>**R**: PRG-RAM Enable (0=Enable, 1=Disable) |

---

## 3. PRG-ROM Bank Modes (The `P` bits in Control)

The MMC1 has 4 distinct modes for mapping PRG-ROM into the CPU's memory space (`$8000-$FFFF`).

*   **Mode 0 & 1:** Switch 32KB at `$8000` (ignores low bit of bank number).
*   **Mode 2:** Fix the FIRST bank at `$8000-$BFFF`, and switch 16KB banks at `$C000-$FFFF`.
*   **Mode 3:** Fix the LAST bank at `$C000-$FFFF`, and switch 16KB banks at `$8000-$BFFF`.

---

## 4. Engine Implementation Notes (midi2nes)

### Bank Layout Strategy (Mode 2 is Mandatory)
As noted in the APU DMC Reference, **DPCM samples MUST reside in the `$C000-$FFFF` range.** 

If we use the default MMC1 Mode 3 (which fixes the last bank at `$C000`), we would be strictly limited to a maximum of 16KB of DPCM samples for the entire game, because that window could never be switched.

Instead, `midi2nes` **must initialize the MMC1 to Mode 2**:
1.  The 6502 Audio Driver (`music.asm`), Sequencer, and fixed Note tables will reside in **Bank 0**, which is permanently fixed to `$8000-$BFFF`.
2.  The `$C000-$FFFF` window remains switchable. 
3.  When a specific DPCM drum needs to play, the driver will bank-switch the appropriate 16KB Sample Bank into `$C000`, trigger the DMA, and continue executing safely from `$8000`.

### 6502 Implementation of Bank Switch
To switch banks efficiently without being interrupted by NMIs, our driver should implement a dedicated subroutine:

```ca65
; A = Bank Number (0-15)
set_prg_bank:
    STA $E000
    LSR A
    STA $E000
    LSR A
    STA $E000
    LSR A
    STA $E000
    LSR A
    STA $E000
    RTS
```

### Reset Vector Consideration
Because the MMC1 powers up in Mode 3 (fixing the *last* bank at `$C000`), our `RESET` vector and initialization code **must** be placed in the very last bank of the ROM. 

The initialization code will immediately reconfigure the MMC1 to Mode 2 (fixing Bank 0 at `$8000`), jump to Bank 0, and leave the upper window free for DPCM sample streaming!