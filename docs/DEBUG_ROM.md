# NES Debug ROM Feature

## Overview

MIDI2NES can generate **debug ROMs** that display real-time diagnostic information on the NES screen. This is extremely helpful for troubleshooting ROM generation issues and understanding what's happening during playback.

## Quick Start

Generate a debug ROM by adding the `--debug` flag:

```bash
# Generate debug ROM
python main.py --debug input.mid output_debug.nes

# or short form
python main.py -d input.mid output_debug.nes
```

## What's Displayed

The debug overlay shows:

### Row 1: Title
```
MIDI2NES DEBUG v1.0
```

### Row 2: APU Channel Status
```
P1:● P2:● TR:● NS:●
```

- **P1** = Pulse 1 channel
- **P2** = Pulse 2 channel
- **TR** = Triangle channel
- **NS** = Noise channel
- **●** (green) = Channel active/playing
- **○** (black) = Channel inactive/silent

### Row 3: Frame Counter
```
FRAME: 03E8
```

Shows the current music frame in hexadecimal (updated 60 times per second).

### Row 4: Error Code (if present)
```
ERROR: 01
```

Common error codes:
- `00` = OK (no errors)
- `01` = APU initialization failed
- `02` = Music data corrupt
- `03` = Invalid channel
- `04` = Buffer overflow
- `05` = Invalid note
- `06` = Pattern error
- `07` = Memory error

## Use Cases

### 1. **"My ROM doesn't make any sound"**

**Solution:** Check the APU status indicators
- If **all channels show ○ (black)**: APU not initialized, check for error code
- If **some channels show ● (green)**: Music is playing but may have mapping issues
- Check frame counter - if it's not incrementing, NMI isn't working

### 2. **"Music plays but sounds wrong"**

**Solution:** Watch which channels are active
- Compare active channels to your MIDI file's instrumentation
- If Triangle channel is constantly active, you may have sustained bass notes
- If Noise channel never activates, drum mapping may have failed

### 3. **"ROM crashes or freezes"**

**Solution:** Check error codes
- Error code `01`: APU failed to initialize
- Error code `02`: Music data is corrupt (pattern compression error)
- Error code `04`: Buffer overflow (music data too large)
- Error code `07`: Memory error (RAM corruption)

### 4. **"I want to verify the ROM is actually running"**

**Solution:** Watch the frame counter
- Should increment steadily (60 times per second)
- If frozen at `0000`: ROM isn't booting properly
- If incrementing but no sound: APU initialization issue

## Technical Details

### Memory Usage

The debug overlay adds approximately:
- **~2KB** of assembly code
- **~64 bytes** of RAM for debug variables
- **No CHR-ROM** required (uses CPU-rendered text)

### Performance Impact

- **Minimal**: Debug updates run during VBLANK
- **No audio impact**: APU updates happen before debug rendering
- **60 FPS maintained**: Debug rendering is optimized

### Screen Layout

The debug overlay uses the top portion of the nametable:
- Rows 0-10: Debug information
- Rest of screen: Black (can be customized)

## Advanced Usage

### Standalone Debug Overlay

You can add the debug overlay to any existing NES project:

```python
from nes.debug_overlay import NESDebugOverlay

# Create overlay generator
overlay = NESDebugOverlay(enable_overlay=True)

# Generate debug system code
debug_code = overlay.generate_full_debug_system()

# Append to your music.asm
with open('music.asm', 'a') as f:
    f.write(debug_code)
```

### Viewing Memory

The debug system includes a memory viewer:

```assembly
; Set memory address to view
LDA #$80
STA debug_memory_view_addr
LDA #$00
STA debug_memory_view_addr+1

; Display 8 bytes starting at $0080
JSR debug_show_memory
```

This will display:
```
MEM: 0080 12 34 56 78 9A BC DE F0
```

### Custom Error Messages

You can set custom error codes in your music.asm:

```assembly
; Set error code and display message
LDA #$03          ; Error code 3 (Invalid Channel)
JSR debug_set_error
```

## Limitations

1. **Text-only display**: No graphics, just ASCII characters
2. **Top screen only**: Debug info occupies ~10 rows
3. **No color palette**: Uses simple monochrome display
4. **NMI overhead**: Adds ~500 cycles per frame to NMI

## Troubleshooting the Debug ROM Itself

### "Debug ROM shows nothing on screen"

**Causes:**
- PPU not initialized
- VBLANK not enabled
- CHR-RAM not configured

**Check:** Make sure main.asm enables NMI and sets $2000 correctly

### "Debug info flickers"

**Cause:** PPU writes happening outside VBLANK

**Fix:** Debug rendering is synchronized to VBLANK automatically, but if you see flickering, the ROM may have timing issues

### "Frame counter doesn't increment"

**Cause:** NMI not firing or music_frame variable not being updated

**Check:**
1. Verify $FFFA vector points to `nmi` handler
2. Verify `debug_update` is called from NMI
3. Check if $2000 has bit 7 set (NMI enable)

## Comparing Debug vs. Release ROMs

| Feature | Debug ROM | Release ROM |
|---------|-----------|-------------|
| File Size | ~131 KB | ~131 KB (same) |
| Performance | ~500 extra cycles/frame | Full speed |
| Screen | Debug overlay visible | Clean display |
| Debugging | Full diagnostics | None |
| Use Case | Development/Testing | Distribution |

## Example Workflow

1. **Generate debug ROM:**
   ```bash
   python main.py --debug song.mid song_debug.nes
   ```

2. **Test in emulator:**
   ```bash
   fceux song_debug.nes
   ```

3. **Observe debug output:**
   - Check APU channels are activating
   - Verify frame counter increments
   - Look for error codes

4. **Fix issues** based on debug info

5. **Generate release ROM** (without --debug):
   ```bash
   python main.py song.mid song.nes
   ```

6. **Test release ROM** to confirm fix works

## Emulator Recommendations

For best debug experience:

- **FCEUX**: Excellent debugger, CPU/PPU viewers
- **Mesen**: Best accuracy, great debugging tools
- **Nestopia**: Good for final testing

## Further Reading

- [NES APU Technical Reference](http://wiki.nesdev.com/w/index.php/APU)
- [NES PPU Reference](http://wiki.nesdev.com/w/index.php/PPU)
- [CA65 Assembler Documentation](https://cc65.github.io/doc/ca65.html)

## Support

If you encounter issues with debug ROMs:

1. Check this documentation first
2. Verify your cc65 toolchain is installed correctly
3. Test with a simple MIDI file (single instrument, short duration)
4. Report issues at: https://github.com/matiaszanolli/midi2nes/issues

Include:
- Your debug ROM file
- Screenshot of debug output
- MIDI file used
- Command-line used to generate ROM
