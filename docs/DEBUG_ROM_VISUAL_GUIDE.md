# Debug ROM Visual Guide

## What You'll See On Screen

When you generate a debug ROM with `python main.py --debug song.mid`, the NES screen will display real-time diagnostic information.

### Normal Playback (No Errors)

```
┌────────────────────────────────────┐
│ MIDI2NES DEBUG v1.0                │  ← Title/Version
│                                    │
│ P1:● P2:● TR:● NS:○                │  ← Channel Status
│ FRAME: 0A3F                        │  ← Frame Counter (hex)
│                                    │
│                                    │
│                                    │
│                                    │
│ [rest of screen is black]          │
│                                    │
└────────────────────────────────────┘
```

**Legend:**
- **●** (filled circle) = Channel is **ACTIVE** (playing sound)
- **○** (empty circle) = Channel is **INACTIVE** (silent)
- **FRAME** = Current music frame in hexadecimal (increments at 60 FPS)

### Channels Explained

| Indicator | Meaning |
|-----------|---------|
| **P1:●** | Pulse 1 channel (usually melody) |
| **P2:●** | Pulse 2 channel (usually harmony) |
| **TR:●** | Triangle channel (usually bass) |
| **NS:○** | Noise channel (usually drums/percussion) |

### ROM with Error

```
┌────────────────────────────────────┐
│ MIDI2NES DEBUG v1.0                │
│                                    │
│ P1:○ P2:○ TR:○ NS:○                │  ← All channels OFF
│ FRAME: 0000                        │  ← Counter stuck at 0
│ ERROR: 01                          │  ← Error code displayed
│ ERR: APU INIT FAILED               │  ← Error message
│                                    │
│                                    │
│ [rest of screen is black]          │
│                                    │
└────────────────────────────────────┘
```

**This tells you:**
- ❌ APU (sound chip) failed to initialize
- ❌ Frame counter not incrementing (ROM stalled)
- ❌ No audio channels active
- 🔧 **Fix needed:** Check APU initialization code

## Example Scenarios

### Scenario 1: Working ROM

**Screen shows:**
```
MIDI2NES DEBUG v1.0

P1:● P2:● TR:● NS:●
FRAME: 12A5
```

**Interpretation:**
- ✅ All 4 channels are active
- ✅ Frame counter incrementing smoothly
- ✅ ROM is working correctly
- ✅ Music should be playing

### Scenario 2: Partial Audio

**Screen shows:**
```
MIDI2NES DEBUG v1.0

P1:● P2:○ TR:● NS:○
FRAME: 0847
```

**Interpretation:**
- ✅ Pulse 1 and Triangle working
- ❌ Pulse 2 and Noise inactive
- 🔍 **Check:** Track mapping - maybe MIDI has no data for those channels
- 🔍 **Check:** Instrument assignment - might need to map more tracks

### Scenario 3: ROM Boots But No Sound

**Screen shows:**
```
MIDI2NES DEBUG v1.0

P1:○ P2:○ TR:○ NS:○
FRAME: 0234
```

**Interpretation:**
- ✅ ROM is running (frame counter incrementing)
- ✅ No initialization errors
- ❌ No channels active
- 🔍 **Check:** Music data might be empty or corrupted
- 🔍 **Check:** Music init function might not be loading data

### Scenario 4: ROM Doesn't Boot

**Screen shows:**
```
[Black screen - nothing displayed]
```

**Interpretation:**
- ❌ ROM not booting at all
- 🔍 **Check:** ROM file size (should be ~131KB for MMC1)
- 🔍 **Check:** ROM header (first 4 bytes should be "NES\x1a")
- 🔍 **Check:** Reset vector at $FFFC-$FFFD

### Scenario 5: Music Data Corruption

**Screen shows:**
```
MIDI2NES DEBUG v1.0

P1:● P2:● TR:○ NS:○
FRAME: 0042
ERROR: 02
ERR: MUSIC DATA BAD
```

**Interpretation:**
- ❌ Music data is corrupted
- ✅ Pulse channels trying to play
- ✅ Error code 02 = data corruption detected
- 🔧 **Fix:** Re-generate ROM, check pattern compression

### Scenario 6: Buffer Overflow

**Screen shows:**
```
MIDI2NES DEBUG v1.0

P1:● P2:● TR:● NS:●
FRAME: 01FF
ERROR: 04
ERR: BUFFER OVERFLOW
```

**Interpretation:**
- ❌ Music data too large for buffers
- ✅ ROM tried to play but ran out of space
- ✅ Error code 04 = buffer overflow
- 🔧 **Fix:** Simplify MIDI, use pattern compression, or increase buffer size

## Error Codes Reference

| Code | Meaning | Common Causes | Fix |
|------|---------|---------------|-----|
| **00** | OK | No errors | N/A |
| **01** | APU Init Failed | APU registers not responding | Check hardware init code |
| **02** | Music Data Corrupt | Pattern data invalid | Regenerate ROM |
| **03** | Invalid Channel | Bad channel assignment | Check track mapper |
| **04** | Buffer Overflow | Music data too large | Simplify MIDI or increase buffers |
| **05** | Invalid Note | Note value out of range | Check MIDI note range (C1-C7) |
| **06** | Pattern Error | Pattern detection failed | Check pattern compression |
| **07** | Memory Error | RAM corruption detected | Check for memory overwrite |

## Frame Counter Behavior

### Normal Behavior
```
FRAME: 0000  → (1/60 second later) → FRAME: 0001
FRAME: 0001  → (1/60 second later) → FRAME: 0002
FRAME: 0002  → (1/60 second later) → FRAME: 0003
...
FRAME: 00FF  → (1/60 second later) → FRAME: 0100
FRAME: FFFF  → (1/60 second later) → FRAME: 0000  (wraps around)
```

### Abnormal Behavior

**Stuck at Zero:**
```
FRAME: 0000  → FRAME: 0000  → FRAME: 0000
```
- ❌ NMI not firing
- ❌ ROM stalled or crashed
- 🔧 Check reset vectors and NMI handler

**Incrementing Too Fast:**
```
FRAME: 0000 → FRAME: 0010 → FRAME: 0020
```
- ❌ NMI firing multiple times per frame
- ❌ Timing issue
- 🔧 Check PPU/NMI configuration

## Channel Activity Patterns

### Typical Music Patterns

**Melody + Bass:**
```
P1:● P2:○ TR:● NS:○    (Pulse 1 = melody, Triangle = bass)
```

**Full Arrangement:**
```
P1:● P2:● TR:● NS:●    (All channels in use)
```

**Percussion Only:**
```
P1:○ P2:○ TR:○ NS:●    (Just drums/noise)
```

**Chord (Harmony):**
```
P1:● P2:● TR:● NS:○    (3-note chord across pulse and triangle)
```

### Suspicious Patterns

**All Off (but frame counter moving):**
```
P1:○ P2:○ TR:○ NS:○    FRAME: 0234
```
- Music data present but not playing
- Check music init or playback logic

**Only Noise (no melodic content):**
```
P1:○ P2:○ TR:○ NS:●    FRAME: 0123
```
- MIDI might only have percussion
- Or track mapping failed for melodic instruments

**Triangle Stuck On:**
```
P1:○ P2:○ TR:● NS:○    FRAME: 0456
```
- Triangle channel stuck playing
- Often means sustained bass note not being released

## Using Debug ROMs for Development

### Step 1: Generate Debug ROM
```bash
python main.py --debug test.mid test_debug.nes
```

### Step 2: Load in Emulator
```bash
# FCEUX (recommended for debugging)
fceux test_debug.nes

# Or Mesen (best accuracy)
mesen test_debug.nes
```

### Step 3: Observe Display

**If everything works:**
- Frame counter should increment smoothly
- Channels should activate based on your MIDI
- No error codes

**If there's a problem:**
1. Note the error code
2. Check which channels are active/inactive
3. Verify frame counter behavior
4. Look up error code in this guide
5. Apply recommended fix
6. Regenerate and test again

### Step 4: Generate Release ROM
```bash
# Once debug ROM works correctly
python main.py test.mid test.nes  # No --debug flag
```

## Troubleshooting Tips

### "I see the debug overlay but no sound"

**Check:**
1. ✅ Frame counter incrementing? (ROM is running)
2. ✅ Any channels showing ●? (Some audio trying to play)
3. ✅ Error code? (System detected an issue)
4. 🔧 Emulator volume settings
5. 🔧 MIDI file has actual note data

### "Debug overlay is flickering"

**Possible causes:**
- PPU writes outside VBLANK (timing issue)
- NMI overhead too high
- Debug rendering taking too long

**Fix:**
- This shouldn't happen with the default debug system
- Check if you modified the debug update code

### "Frame counter not incrementing"

**Diagnosis:**
```
FRAME: 0000  (stuck)
```

**Possible causes:**
1. NMI not enabled ($2000 bit 7 should be set)
2. NMI vector ($FFFA-$FFFB) pointing to wrong address
3. ROM crashed/infinite loop

**Fix:**
1. Check main.asm sets `LDA #$80 / STA $2000`
2. Verify NMI vector in VECTORS segment
3. Use emulator debugger to check CPU state

### "Channels active but still no sound"

**Diagnosis:**
```
P1:● P2:● TR:● NS:●    (all active)
FRAME: 0234           (incrementing)
```

**Possible causes:**
1. APU registers not being written correctly
2. Volume set to 0
3. Frequency out of audible range

**Check:**
- APU register values ($4000-$400F)
- Volume bits in pulse/triangle control
- Frequency values in timer registers

## Comparison: Debug vs Release ROM

### Debug ROM Display
```
┌────────────────────────────────────┐
│ MIDI2NES DEBUG v1.0                │
│                                    │
│ P1:● P2:● TR:● NS:○                │
│ FRAME: 0A3F                        │
│                                    │
│ [diagnostic info visible]          │
│                                    │
└────────────────────────────────────┘
```
- ✅ Real-time diagnostics
- ✅ Error messages
- ✅ Channel status
- ⚠️ +2KB code, +500 cycles/frame

### Release ROM Display
```
┌────────────────────────────────────┐
│                                    │
│                                    │
│                                    │
│        [black screen]              │
│                                    │
│                                    │
│                                    │
└────────────────────────────────────┘
```
- ✅ Minimal overhead
- ✅ Production ready
- ❌ No visual feedback
- ❌ Harder to debug

## Best Practices

### During Development
- ✅ **Always use `--debug` flag**
- ✅ Check debug display for issues
- ✅ Note error codes
- ✅ Verify channel activity matches expectations

### Before Release
- ✅ Test debug ROM thoroughly
- ✅ Fix all errors (error code should be 00)
- ✅ Verify all expected channels activate
- ✅ Generate release ROM (without --debug)
- ✅ Do final test of release ROM

### For Bug Reports
When reporting issues, include:
1. Screenshot of debug ROM display
2. Error code (if any)
3. Frame counter value
4. Channel status (which are ●/○)
5. MIDI file used
6. Command used to generate ROM

This helps maintainers diagnose issues quickly!

## Summary

The debug ROM feature provides **instant visual feedback** on:
- ✅ ROM execution status (frame counter)
- ✅ APU initialization (channel indicators)
- ✅ Audio playback (active channels)
- ✅ Error conditions (error codes)

This transforms debugging from guesswork to **data-driven problem solving**.

**Use the debug ROM to:**
1. Verify your ROM boots correctly
2. Check APU initialization
3. Confirm audio channels are active
4. Identify specific errors
5. Validate timing and playback

**Happy debugging!** 🐛🔍
