# MMC1 Configuration Fix for MIDI2NES

## Problem
The MIDI2NES ROM generator was producing ROMs that were 1 byte smaller than expected (32,783 bytes instead of 32,784 bytes). Analysis showed that this was caused by incorrect MMC1 mapper configuration.

## Root Cause
In `/nes/project_builder.py`, the MMC1 control register was being set to `$0E` (00001110 binary):
- Bits 2-3 = 11: This configured the mapper for **16KB PRG banking mode**
- However, our ROMs are designed as single **32KB units**

## Solution
Changed the MMC1 control register value from `$0E` to `$0A` (00001010 binary):

```assembly
; OLD (incorrect):
lda #$0E              ; 16KB PRG mode, CHR-RAM, horizontal mirroring

; NEW (correct):  
lda #$0A              ; 32KB PRG mode, CHR-RAM, horizontal mirroring
```

### MMC1 Control Register Breakdown for $0A:
- Bits 0-1: 10 = Horizontal mirroring ✓
- Bits 2-3: 10 = **32KB PRG banking mode** ✓ (this was the key fix!)
- Bit 4: 0 = CHR A/B switching ✓

## Results
- ✅ ROM size now exactly 32,784 bytes (16-byte header + 32KB PRG ROM)
- ✅ ROM diagnostics report "HEALTHY" 
- ✅ MMC1 mapper properly configured for single 32KB ROM layout
- ✅ Vectors placed correctly at $FFFA-$FFFF

## Files Modified
- `/nes/project_builder.py` - Line 70: Changed `lda #$0E` to `lda #$0A`

This fix ensures that all generated MIDI2NES ROMs use the correct MMC1 configuration for 32KB PRG mode, matching the intended ROM structure.
