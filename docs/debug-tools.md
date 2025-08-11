# MIDI2NES Debug Tools Documentation

A comprehensive guide to using the MIDI2NES ROM diagnostics and debugging tools.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Tool Reference](#tool-reference)
- [ROM Health Classification](#rom-health-classification)
- [Common Issues & Solutions](#common-issues--solutions)
- [Integration Examples](#integration-examples)
- [Troubleshooting](#troubleshooting)

## Overview

The MIDI2NES debug tools provide comprehensive ROM validation and diagnostics capabilities to help identify and fix issues with generated NES ROMs. These tools are essential for:

- **Quality Assurance**: Validate ROM integrity before distribution
- **Development**: Debug ROM generation issues during development
- **Maintenance**: Monitor ROM health over time
- **CI/CD Integration**: Automate ROM validation in build pipelines

### Key Features

- 🔍 **Comprehensive Analysis**: Header validation, corruption detection, vector validation
- 🎵 **Audio-Specific Checks**: APU pattern detection and music data analysis
- 📊 **Multiple Output Formats**: Human-readable reports and JSON for automation
- 🚀 **Easy Integration**: Simple CLI tools and Python API
- 🛡️ **Actionable Recommendations**: Specific guidance for each issue type

## Quick Start

### Basic Health Check

Check if your ROM is healthy:

```bash
python debug/check_rom.py your_rom.nes
```

**Example Output:**
```
🔍 Quick ROM Health Check
========================================
🟡 your_rom.nes: GOOD
   📊 32,783 bytes (2 PRG banks)

✅ ROM appears healthy!
```

### Detailed Analysis

For comprehensive diagnostics:

```bash
python debug/rom_diagnostics.py your_rom.nes
```

**Example Output:**
```
============================================================
🔍 MIDI2NES ROM Diagnostics Report
============================================================
📁 File: your_rom.nes
📊 Size: 32,783 bytes
🎮 Format: iNES (PRG: 2 banks, CHR: 0 banks)
📐 Expected size: 32,784 bytes
⚠️  Size difference: -1 bytes

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

❌ Issues Found (1):
   1. Size mismatch: 1 bytes smaller than expected
```

### Verbose Analysis

For detailed pattern analysis:

```bash
python debug/rom_diagnostics.py your_rom.nes --verbose
```

This includes detailed APU and assembly pattern breakdowns.

## Tool Reference

### `check_rom.py` - Quick Health Checker

**Purpose**: Fast ROM validation with minimal output

**Usage:**
```bash
python debug/check_rom.py [ROM_FILE]
```

**Features:**
- Quick pass/fail assessment
- Critical issue highlighting
- Basic ROM statistics
- Actionable next steps

**Exit Codes:**
- `0`: ROM is healthy/good
- `1`: ROM has issues

### `rom_diagnostics.py` - Comprehensive Analysis

**Purpose**: Complete ROM diagnostics with detailed reporting

**Usage:**
```bash
python debug/rom_diagnostics.py [ROM_FILES...] [OPTIONS]
```

**Options:**
- `--verbose, -v`: Enable detailed pattern analysis
- `--output {human,json}`: Choose output format (default: human)

**Features:**
- Complete ROM health assessment
- Detailed corruption analysis
- APU and assembly pattern detection
- Multiple output formats
- Batch processing support

**Examples:**
```bash
# Basic analysis
python debug/rom_diagnostics.py game.nes

# Verbose analysis with pattern details
python debug/rom_diagnostics.py game.nes --verbose

# JSON output for automation
python debug/rom_diagnostics.py game.nes --output json

# Analyze multiple ROMs
python debug/rom_diagnostics.py *.nes

# Compare before/after
python debug/rom_diagnostics.py broken.nes fixed.nes
```

### `pipeline_integration_example.py` - Integration Example

**Purpose**: Demonstrates integration with MIDI2NES pipeline

**Usage:**
```bash
python debug/pipeline_integration_example.py input.mid output.nes
```

**Features:**
- Full pipeline execution with validation
- Automatic ROM health checking
- Integrated error reporting
- CI/CD ready

## ROM Health Classification

| Status | Icon | Description | Action Required |
|--------|------|-------------|-----------------|
| **HEALTHY** | 🟢 | Perfect ROM with no issues | None - ROM is ready for use |
| **GOOD** | 🟡 | Minor issues that don't affect functionality | Optional improvements |
| **FAIR** | 🟠 | Some issues that may cause problems | Review and consider fixes |
| **POOR** | 🔴 | Major issues, ROM likely corrupted | Fix required before use |
| **ERROR** | ❌ | Cannot read or invalid ROM file | Check file path and format |

### Health Factors

The health assessment considers:

- **Size Matching**: ROM file size vs. header expectations
- **Zero Byte Ratio**: Excessive zeros indicate corruption
- **Repetition Patterns**: Too much repetition suggests generation issues
- **Reset Vectors**: Must point to valid ROM addresses ($8000-$FFFF)
- **APU Patterns**: Presence of audio initialization code
- **Pattern Density**: Quality of generated music data
- **Assembly Activity**: Presence of valid 6502 instruction patterns

## Common Issues & Solutions

### 🔴 Size Mismatch

**Problem**: ROM file size doesn't match header expectations

**Symptoms:**
- File size differs from expected size based on PRG/CHR bank count
- Usually indicates linker configuration issues

**Solutions:**
1. Check linker configuration (`linker.cfg`)
2. Verify PRG/CHR bank count in ROM header
3. Ensure reset vectors are properly placed
4. Review memory layout in build scripts

**Example Fix:**
```cfg
# linker.cfg
MEMORY {
    HEADER: start = $0000, size = $0010, type = ro, file = %O, fill = yes;
    ROM: start = $0010, size = $7FF0, type = ro, file = %O, fill = yes;
    VECTORS: start = $7FFA, size = $0006, type = ro, file = %O, fill = yes;
}
```

### 🔴 Excessive Zero Bytes (>70%)

**Problem**: ROM contains too many zeros, indicating corruption

**Symptoms:**
- Zero byte percentage above 70%
- ROM appears much larger than actual content
- Music may not play correctly

**Solutions:**
1. Regenerate ROM from source MIDI
2. Check MIDI input file for validity
3. Verify pattern generation pipeline
4. Review assembly export process

**Prevention:**
- Validate MIDI files before processing
- Use ROM diagnostics in build pipeline
- Monitor pattern generation output

### 🔴 Invalid Reset Vectors

**Problem**: Reset vectors don't point to valid ROM addresses

**Symptoms:**
- Vector addresses below $8000 or invalid
- ROM may not boot on hardware/emulators
- Crash on startup

**Solutions:**
1. Check linker script vector placement
2. Ensure vectors are at $FFFA-$FFFF in ROM
3. Verify code section layout
4. Review assembly file structure

**Example Fix:**
```asm
.segment "VECTORS"
    .word nmi_handler    ; $FFFA
    .word reset_handler  ; $FFFC  
    .word irq_handler    ; $FFFE
```

### 🔴 No APU Code Found

**Problem**: No audio initialization patterns detected

**Symptoms:**
- No sound output
- Missing APU register writes
- Music player not initialized

**Solutions:**
1. Include music player code in build
2. Verify APU initialization in main.asm
3. Ensure sound data is properly linked
4. Check for missing audio drivers

**Example APU Init:**
```asm
; Enable APU
LDA #$0F
STA $4015

; Initialize pulse channels
LDA #$BF
STA $4000  ; Pulse 1
STA $4004  ; Pulse 2
```

### 🟡 Low Assembly Activity

**Problem**: Minimal assembly code patterns detected

**Note**: This may be normal for music-only ROMs that primarily contain data

**Solutions:**
- If ROM functions correctly, this is usually acceptable
- For complex ROMs, may indicate missing code sections
- Review if all necessary code modules are included

## Integration Examples

### Build Pipeline Integration

Add ROM validation to your build process:

```bash
#!/bin/bash
# build.sh

echo "Building ROM..."
python main.py song.mid song.nes

echo "Validating ROM..."
if python debug/check_rom.py song.nes; then
    echo "✅ ROM validation passed"
else
    echo "❌ ROM validation failed"
    echo "Running detailed diagnostics..."
    python debug/rom_diagnostics.py song.nes
    exit 1
fi
```

### CI/CD Integration

GitHub Actions example:

```yaml
name: ROM Validation
on: [push, pull_request]

jobs:
  validate-roms:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Generate ROM
        run: python main.py test.mid test.nes
      
      - name: Validate ROM
        run: |
          python debug/check_rom.py test.nes
          python debug/rom_diagnostics.py test.nes --output json > rom_report.json
      
      - name: Upload Report
        uses: actions/upload-artifact@v3
        with:
          name: rom-diagnostics
          path: rom_report.json
```

### Python API Usage

```python
from debug.rom_diagnostics import ROMDiagnostics

# Create diagnostics instance
diagnostics = ROMDiagnostics(verbose=False)

# Analyze ROM
result = diagnostics.diagnose_rom("game.nes")

# Check health
if result.overall_health in ['HEALTHY', 'GOOD']:
    print("ROM is ready for distribution")
else:
    print(f"ROM has issues: {result.issues}")
    
# Access specific metrics
print(f"Zero bytes: {result.zero_byte_percent:.1f}%")
print(f"APU patterns found: {result.apu_pattern_count}")
print(f"Reset vectors valid: {result.reset_vectors_valid}")
```

### Automated Testing

```python
import unittest
from debug.rom_diagnostics import ROMDiagnostics

class TestROMQuality(unittest.TestCase):
    def test_rom_health(self):
        diagnostics = ROMDiagnostics()
        result = diagnostics.diagnose_rom("output.nes")
        
        # Assert ROM meets quality standards
        self.assertIn(result.overall_health, ['HEALTHY', 'GOOD'])
        self.assertLess(result.zero_byte_percent, 70)
        self.assertTrue(result.reset_vectors_valid)
        self.assertGreater(result.apu_pattern_count, 0)
```

## Troubleshooting

### ROM Won't Load in Emulator

1. **Check file format**: Ensure ROM has valid iNES header
2. **Verify size**: Use diagnostics to check size matching
3. **Test reset vectors**: Invalid vectors prevent booting
4. **Try different emulator**: Some are more tolerant than others

### No Sound Output

1. **Check APU patterns**: Use `--verbose` to see audio initialization
2. **Verify music data**: Ensure pattern density is reasonable (>5%)
3. **Test with known good ROM**: Isolate hardware vs. ROM issues
4. **Check emulator audio settings**: Ensure audio is enabled

### ROM Too Large/Small

1. **Check bank configuration**: Verify PRG/CHR bank counts
2. **Review linker script**: Ensure memory layout is correct
3. **Validate build process**: Check for missing or extra data
4. **Compare with reference**: Use diagnostics to compare ROMs

### False Positives

If diagnostics report issues but ROM works fine:

1. **Check thresholds**: Some music ROMs naturally have repetitive data
2. **Use verbose mode**: Get detailed breakdown of detected patterns
3. **Compare with known good ROMs**: Establish baselines for your ROMs
4. **File GitHub issue**: Help improve diagnostic accuracy

### Getting Help

1. **Check this documentation**: Most common issues are covered
2. **Run verbose diagnostics**: Get detailed analysis
3. **Compare with working ROMs**: Use diagnostics to find differences
4. **Review build logs**: Check for warnings or errors
5. **File bug report**: Include diagnostic output and ROM details

## Best Practices

### Development Workflow

1. **Generate ROM** with MIDI2NES pipeline
2. **Quick check** with `check_rom.py`  
3. **Detailed analysis** with `rom_diagnostics.py` if issues found
4. **Fix issues** based on recommendations
5. **Re-validate** after fixes
6. **Test on hardware/emulator**

### Quality Assurance

- **Automate validation** in build pipelines
- **Set quality gates** based on ROM health status
- **Monitor trends** over time with JSON output
- **Document known issues** and their fixes
- **Test on multiple emulators/hardware**

### Performance Tips

- Use `check_rom.py` for quick validation
- Save detailed reports with `--output json` for later analysis
- Process multiple ROMs in single command for efficiency
- Cache results for unchanged ROMs in CI/CD

---

For more information, see:
- [API Reference](debug-api.md)
- [Architecture Overview](debug-architecture.md)
- [Contributing Guide](../CONTRIBUTING.md)
