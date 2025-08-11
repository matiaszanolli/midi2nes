# MIDI2NES Debug Tools

This module contains debugging, analysis, and diagnostic tools for the MIDI2NES pipeline. These tools are used during development and for troubleshooting issues in the conversion process.

## Available Tools

### Pattern Analysis
- **`pattern_analysis.py`**: Analyze pattern detection results and compression effectiveness
  ```bash
  python -m debug.pattern_analysis
  ```

### CA65 Assembly Analysis
- **`ca65_inspector.py`**: Inspect CA65 assembly output and pattern reference tables
  ```bash
  python -m debug.ca65_inspector
  ```

### Frame Generation Analysis
- **`frame_analyzer.py`**: Debug frame generation from mapped MIDI data
  ```bash
  python -m debug.frame_analyzer [mapped_file.json]
  ```

### Music Structure Analysis
- **`music_structure_analyzer.py`**: Comprehensive analysis of music structure in NES ROMs
  ```bash
  python -m debug.music_structure_analyzer [rom_file.nes]
  ```

### Pattern Reference Debugging
- **`pattern_reference_debugger.py`**: Advanced pattern reference table analysis
  ```bash
  python -m debug.pattern_reference_debugger [rom_file.nes]
  ```

### Performance Analysis
- **`performance_analyzer.py`**: MIDI parser performance testing and optimization
  ```bash
  python -m debug.performance_analyzer
  ```

### Audio Pattern Checking
- **`audio_checker.py`**: Simple APU pattern checking for NES ROMs
  ```bash
  python -m debug.audio_checker [rom_file.nes]
  ```

### ROM Testing
- **`rom_tester.py`**: Comprehensive ROM generation test suite
  ```bash
  python -m debug.rom_tester
  ```

## Using from Code

You can import and use these tools programmatically:

```python
from debug import (
    analyze_patterns,
    inspect_ca65_output,
    analyze_frames,
    analyze_music_structure,
    debug_pattern_references,
    analyze_performance,
    check_audio_simple,
    test_rom_generation
)

# Analyze pattern detection results
analyze_patterns("output/patterns")

# Check audio patterns in ROM
check_audio_simple("output.nes")

# Run full ROM generation test suite
success = test_rom_generation()
```

## Legacy Files

The `debug/` directory also contains the original debug scripts that were moved from the root directory:

- `debug_ca65_detailed.py`
- `debug_ca65_references.py`
- `debug_music_structure.py`
- `debug_pattern_refs.py`
- `inspect_ca65_output.py`
- `simple_audio_check.py`
- `performance_test_parser.py`
- `test_rom_generation.py`
- `manual_assembly_test.py`
- `test_pattern_reference_fix.py`
- `test_performance.py`
- `test_input_performance.py`

These files are preserved for backward compatibility but it's recommended to use the new organized modules instead.

## Development Guidelines

When adding new debug tools:

1. Create a new module in the `debug/` directory
2. Follow the naming convention: `[purpose]_[type].py` (e.g., `pattern_analyzer.py`)
3. Include a main function for CLI usage
4. Add the module to the `__init__.py` imports
5. Document the tool in this README
6. Include proper error handling and user-friendly output

## Dependencies

Some debug tools require additional dependencies:
- `psutil` for performance analysis
- `ca65`/`ld65` tools for ROM testing
- Various MIDI2NES modules for functionality

Make sure to handle import errors gracefully if dependencies are missing.
