# Debug Tools Quick Reference

Quick reference for common ROM diagnostic scenarios.

## Quick Commands

### Basic Health Check
```bash
python debug/check_rom.py game.nes
```

### Detailed Analysis
```bash
python debug/rom_diagnostics.py game.nes
```

### Verbose Analysis
```bash
python debug/rom_diagnostics.py game.nes --verbose
```

### JSON Output
```bash
python debug/rom_diagnostics.py game.nes --output json
```

### Multiple ROMs
```bash
python debug/rom_diagnostics.py *.nes
```

### Pipeline with Validation
```bash
python debug/pipeline_integration_example.py song.mid song.nes
```

## Health Status Guide

| Icon | Status | Meaning | Action |
|------|--------|---------|--------|
| 🟢 | HEALTHY | Perfect ROM | Ready for use |
| 🟡 | GOOD | Minor issues | Optional fixes |
| 🟠 | FAIR | Some problems | Review issues |
| 🔴 | POOR | Major issues | Fix required |
| ❌ | ERROR | Cannot read | Check file |

## Common Issues Quick Fix

### Size Mismatch
```bash
# Check linker config memory layout
# Verify PRG bank count matches actual size
```

### Excessive Zeros (>70%)
```bash
# Regenerate ROM from MIDI
# Check pattern generation pipeline
```

### Invalid Reset Vectors
```bash
# Vectors must point to $8000-$FFFF range
# Check linker script vector placement
```

### No APU Code
```bash
# Ensure APU initialization code included
# Verify music player linkage
```

## Python API Quick Start

### Basic Usage
```python
from debug.rom_diagnostics import ROMDiagnostics

diagnostics = ROMDiagnostics()
result = diagnostics.diagnose_rom("game.nes")

if result.overall_health in ['HEALTHY', 'GOOD']:
    print("ROM is ready!")
else:
    print(f"Issues: {result.issues}")
```

### Quick Check Function
```python
from debug import quick_check_rom

if quick_check_rom("game.nes"):
    print("ROM passed!")
```

### Batch Analysis
```python
import os
from debug.rom_diagnostics import ROMDiagnostics

diagnostics = ROMDiagnostics()
for rom in os.listdir('.'):
    if rom.endswith('.nes'):
        result = diagnostics.diagnose_rom(rom)
        print(f"{rom}: {result.overall_health}")
```

## Key Metrics

### Size Analysis
- **Expected vs Actual**: File size should match header
- **PRG Banks**: Usually 1-2 for music ROMs
- **Size Tolerance**: ±10 bytes is typically acceptable

### Content Analysis
- **Zero Bytes**: <70% is good, >70% indicates corruption
- **Repetition**: <80% is good, >80% may indicate issues
- **Pattern Density**: >5% shows good music data
- **Assembly Score**: 50+ indicates sufficient code

### Reset Vectors
- **Valid Range**: $8000-$FFFF
- **Common Values**: $FFFF (unimplemented), or actual handler addresses
- **Required**: All three vectors (NMI, RESET, IRQ) must be valid

### Audio Indicators
- **APU Patterns**: >0 shows audio initialization
- **Common Patterns**: `$0F → $4015` (APU enable), `$BF → $4000/$4004` (pulse init)

## Troubleshooting Flowchart

```
ROM Issues?
    │
    ├─ Won't Load → Check reset vectors, file format
    │
    ├─ No Sound → Check APU patterns, pattern density
    │
    ├─ Too Large → Check bank count, linker config
    │
    ├─ Corrupted → Check zero bytes, regenerate ROM
    │
    └─ Build Fails → Check size mismatch, memory layout
```

## Integration Examples

### Build Script
```bash
#!/bin/bash
python main.py input.mid output.nes
python debug/check_rom.py output.nes || exit 1
```

### GitHub Actions
```yaml
- name: Validate ROM
  run: python debug/check_rom.py output.nes
```

### Testing
```python
def test_rom_quality(self):
    result = ROMDiagnostics().diagnose_rom("test.nes")
    self.assertIn(result.overall_health, ['HEALTHY', 'GOOD'])
```

## Output Examples

### Healthy ROM
```
🟡 game.nes: GOOD
   📊 32,783 bytes (2 PRG banks)
✅ ROM appears healthy!
```

### Corrupted ROM
```
🔴 broken.nes: POOR
   📊 131,077 bytes (8 PRG banks)
   ⚠️  Critical: Excessive zero bytes (96.9%)
   💡 Tip: ROM may be corrupted or improperly generated
```

### Detailed Report
```
============================================================
🔍 MIDI2NES ROM Diagnostics Report
============================================================
📁 File: game.nes
📊 Size: 32,783 bytes
🎮 Format: iNES (PRG: 2 banks, CHR: 0 banks)

🔍 Content Analysis:
   Zero bytes: 44.9% ✅
   Repetition: 40.6% ✅
   Pattern density: 12.2% ✅
   Assembly score: 77/220 ✅
   APU patterns: 2 ✅

🎯 Reset Vectors:
   NMI: $FFFF ✅
   RESET: $FFFF ✅
   IRQ: $FFFF ✅

🟡 Overall Health: GOOD
```

## File Locations

```
debug/
├── README.md                    # Tool overview
├── __init__.py                 # Module setup
├── rom_diagnostics.py          # Main diagnostic tool
├── check_rom.py               # Quick checker
├── pipeline_integration_example.py # Integration demo
└── test_rom_diagnostics.py    # Test suite

docs/
├── debug-tools.md             # Complete user guide
├── debug-api.md               # Python API reference
└── debug-quickref.md          # This quick reference
```

## Exit Codes

- `0`: Success (ROM healthy/good)
- `1`: Issues found (ROM has problems)

Perfect for CI/CD integration and scripting.

---

**Need more details?** See [debug-tools.md](debug-tools.md) for complete documentation.
