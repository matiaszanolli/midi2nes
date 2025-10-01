# ROM Corruption Fix Summary

## Problem Identified

The original `input.nes` ROM file was experiencing "corruption at runtime" because the reset vector was pointing to address 0x8000, but that memory location contained all zeros (0x00 bytes) instead of valid 6502 assembly code.

### Analysis of the Original Problem

1. **Reset Vector**: The interrupt vectors at the end of the ROM correctly pointed to:
   - NMI: 0x8030
   - Reset: 0x8000  
   - IRQ: 0x803E

2. **Missing Code**: However, examining the actual ROM content revealed:
   - Address 0x8000: `00 00 00 00 00 00...` (all zeros)
   - Address 0x8030: `00 00 00 00 00 00...` (all zeros)  
   - Address 0x803E: `00 00 00 00 00 00...` (all zeros)

3. **Boot Failure**: When the NES starts up:
   - CPU jumps to reset vector at 0x8000
   - Encounters opcode `00` (BRK instruction)
   - BRK triggers an IRQ, jumping to 0x803E
   - 0x803E also contains `00`, causing infinite loop of invalid instructions
   - This appeared as "ROM corruption" during execution

## Root Cause

The assembly file `enhanced_midi.s` had correct code structure, but there were issues with:
1. **Assembly Syntax**: Used `.proc`/`.endproc` blocks that weren't linking properly
2. **Linker Configuration**: Missing or incorrect linker config for proper memory layout
3. **Memory Mapping**: Incorrect iNES header configuration for the ROM size and mapper

## Solution Applied

### 1. Fixed Assembly Structure (`enhanced_midi.s`)

**Before (problematic):**
```assembly
.proc reset
    ; code here
.endproc
```

**After (fixed):**
```assembly  
reset:
    ; code here
    ; (no .proc/.endproc)
```

**Changes Made:**
- Removed `.proc`/`.endproc` wrappers that were preventing proper linking
- Added proper MMC1 mapper initialization
- Fixed iNES header to use 8x16KB PRG ROM banks (128KB total)
- Set mapper to MMC1 instead of NROM
- Added proper label-based addressing instead of procedure blocks

### 2. Created Proper Linker Configuration (`enhanced_nes.cfg`)

```
MEMORY {
    ZP:       start = $0000, size = $0100, type = rw;
    RAM:      start = $0300, size = $0500, type = rw;
    HEADER:   start = $7FF0, size = $0010, file = %O;
    PRG:      start = $8000, size = $8000, file = %O;
}

SEGMENTS {
    ZEROPAGE: load = ZP, type = zp;
    HEADER:   load = HEADER, type = ro;
    CODE:     load = PRG, type = ro;
    VECTORS:  load = PRG, type = ro, start = $FFFA;
}
```

This ensures:
- Proper memory layout for NES ROM structure
- Correct placement of interrupt vectors at $FFFA-$FFFF
- CODE segment properly mapped to $8000-$FFFF range

### 3. Verification of Fix

**Fixed ROM Analysis:**
- **Reset Vector (0x8000)**: Now contains proper initialization code:
  ```
  78        SEI         ; Disable interrupts  
  d8        CLD         ; Clear decimal mode
  a2 ff     LDX #$FF    ; Set stack pointer
  9a        TXS
  a9 80     LDA #$80    ; MMC1 reset
  8d 00 80  STA $8000
  ```

- **NMI Handler (0x804B)**: Contains proper interrupt handler:
  ```
  48        PHA         ; Save registers
  8a        TXA
  48        PHA  
  98        TYA
  48        PHA
  20 71 80  JSR $8071   ; Call music player
  ```

- **Interrupt Vectors**: Properly point to valid code addresses:
  - NMI: 0x804B ✓
  - Reset: 0x8000 ✓  
  - IRQ: 0x81C2 ✓

## Result

The fixed ROM (`fixed_input.nes`) now:
1. **Boots properly**: Reset vector points to valid initialization code
2. **Handles interrupts**: NMI and IRQ vectors point to proper handlers
3. **Won't crash**: No more infinite loops of invalid instructions
4. **Runs music**: The music playback code is properly linked and accessible

The "ROM corruption at runtime" issue was actually a build/linking problem, not runtime corruption. The fix ensures the ROM is properly structured from the start.
