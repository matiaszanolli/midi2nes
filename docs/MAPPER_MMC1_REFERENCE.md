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


> **Status (as of #281/#282): NOT YET IMPLEMENTED.** The Mode-2 DPCM-streaming
> design below is the *target* design, not the current behavior. The direct-export
> (`--no-patterns`) engine's `play_dpcm` trigger and the DPCM sample packer are
> still MMC3-only (MMC3 R6 bank-select + `DPCM_NN` segments). Until this design
> lands, a `--no-patterns` build of a song with a DPCM channel forces `--mapper
> mmc3` under `auto` and is rejected outright for an explicit `--mapper mmc1`/
> `nrom` (a clean error, not a corrupting/unlinkable ROM). DPCM drums otherwise
> ship via the MMC3 macro-bytecode (pattern) path, which is always MMC3.

### Bank Layout Strategy (Mode 2 is Mandatory)
As noted in the APU DMC Reference, **DPCM samples MUST reside in the `$C000-$FFFF` range.** 

1.  The 6502 Audio Driver (`music.asm`), Sequencer, vectors, and reset/init code
    reside in the **fixed last bank at `$C000-$FFFF`**.
2.  The `$8000-$BFFF` window is **switchable**; the direct-export
    (`--no-patterns`) exporter bin-packs frame tables that overflow one 16 KB
    window into per-bank `RODATA_BANK_NN` segments and emits a
    `generate_bank_switch_code()` write to `$E000` before each (#255). This is
    what MMC1 buys today: **frame-table capacity beyond NROM's 32 KB**, not DPCM.
3.  **DPCM samples are not supported on MMC1.** DMC hardware can only fetch from
    `$C000-$FFFF`, which Mode 3 permanently fixes, so the switchable window can't
    stream sample banks. The direct-export DPCM trigger/packer are MMC3-only, so
    a `--no-patterns` build of a song with a DPCM channel forces `--mapper mmc3`
    under `auto` and is rejected for an explicit `--mapper mmc1`/`nrom`
    (#281/#282). DPCM drums otherwise ship via the always-MMC3 bytecode path.

### 6502 Implementation of Bank Switch (Mode 3, `$8000-$BFFF`)
The shipped `generate_bank_switch_code()` serially writes the target bank number
to the PRG Bank register (`$E000`), switching the `$8000-$BFFF` window:

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

Because MMC1 powers up in Mode 3 (fixing the *last* bank at `$C000`), the `RESET`
vector and init code naturally live in that fixed last bank — no mode change is
needed at boot.

---

### Future Target: Mode 2 + `$C000` DPCM streaming (NOT YET IMPLEMENTED)
The design below would add real MMC1 DPCM support. It is **not implemented** — the
shipped mapper is Mode 3 as described above. Kept here as the intended end state
for the #281/#282 DPCM-on-MMC1 work.

As noted in the APU DMC Reference, **DPCM samples MUST reside in the `$C000-$FFFF`
range.** Under Mode 3 that window is fixed, capping DPCM at a single non-switchable
16 KB bank. To stream large drum kits, `midi2nes` would instead initialize the
MMC1 to **Mode 2**:
1.  The audio driver, sequencer, and fixed note tables reside in **Bank 0**,
    permanently fixed to `$8000-$BFFF`.
2.  The `$C000-$FFFF` window remains switchable.
3.  When a DPCM drum plays, the driver bank-switches the appropriate 16 KB sample
    bank into `$C000`, triggers the DMA, and continues executing safely from
    `$8000`.

Since MMC1 powers up in Mode 3, the `RESET`/init code would sit in the last bank,
immediately reconfigure to Mode 2 (fixing Bank 0 at `$8000`), jump to Bank 0, and
leave the upper window free for DPCM streaming.