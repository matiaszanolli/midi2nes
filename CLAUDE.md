# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIDI2NES is a high-performance MIDI to NES ROM compiler. It converts MIDI files into playable NES ROMs or generates audio data for homebrew NES games. The system features 120x faster parsing, multi-core pattern detection (95x compression), and complete NES ROM generation pipeline.

## Development Commands

### Core Pipeline Commands

```bash
# Single-command MIDI to NES ROM conversion
python main.py input.mid output.nes

# Step-by-step pipeline for debugging
python main.py parse input.mid parsed.json          # Fast MIDI parsing
python main.py map parsed.json mapped.json          # Track to NES channel mapping
python main.py frames mapped.json frames.json       # Frame generation
python main.py detect-patterns frames.json patterns.json  # Pattern detection
python main.py export frames.json output.s --format ca65 --patterns patterns.json
python main.py prepare output.s nes_project/        # Prepare NES project
```

### Testing

```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_main.py

# Run with coverage
python -m pytest --cov=.

# Test ROM generation pipeline
python -m debug.rom_tester
```

### Debug & Validation

```bash
# Quick ROM health check
python -m debug.check_rom output.nes

# Comprehensive ROM diagnostics
python debug/rom_diagnostics.py output.nes --verbose

# Performance analysis
python -m debug.performance_analyzer

# Pattern analysis
python -m debug.pattern_analysis output/patterns
```

### Building NES ROMs

After preparing a project with `main.py prepare`, build the ROM:

```bash
cd nes_project/
./build.sh          # Unix/Linux/macOS
# or
build.bat           # Windows
```

Build script compiles with CC65 toolchain:
```bash
ca65 main.asm -o main.o
ca65 music.asm -o music.o
ld65 -C nes.cfg main.o music.o -o game.nes
```

## Architecture

### Core Pipeline Flow

```
MIDI → Parse → Map → Frames → Export → Project → ROM
       (fast)  (NES) (60fps)  (CA65)   (CC65)   (.nes)
```

### Key Directories

- **`tracker/`** - MIDI processing core
  - `parser_fast.py` - Optimized MIDI parser (120x faster)
  - `pattern_detector_parallel.py` - Multi-core pattern detection
  - `tempo_map.py` - Enhanced tempo handling
  - `track_mapper.py` - NES channel assignment

- **`nes/`** - NES-specific components
  - `emulator_core.py` - Frame generation
  - `project_builder.py` - Complete NES project setup with MMC1
  - `pitch_table.py` - NES frequency tables
  - `envelope_processor.py` - ADSR envelope handling

- **`exporter/`** - Output format generators
  - `exporter_ca65.py` - CA65 assembly export with pattern compression
  - `exporter_nsf.py` - NSF audio format
  - `exporter_famistudio.py` - FamiTracker export

- **`dpcm_sampler/`** - Drum/sample processing
  - `enhanced_drum_mapper.py` - Intelligent drum mapping
  - `dpcm_sample_manager.py` - DPCM sample management

- **`debug/`** - Diagnostic and validation tools
  - `rom_diagnostics.py` - Complete ROM health checks
  - `check_rom.py` - Quick validation
  - `nes_devtools.py` - NES development utilities

- **`config/`** - Configuration management
  - `config_manager.py` - YAML config handling
  - `default_config.yaml` - Default settings

- **`tests/`** - Comprehensive test suite
  - Unit tests for all major components
  - Integration tests for pipeline stages

### Important Implementation Details

#### MMC1 ROM Generation
- The system **always uses MMC1 mapper** with 128KB PRG-ROM capacity
- `NESProjectBuilder` generates complete NES projects with:
  - `main.asm` - NMI-based 60Hz timing system (critical for playback)
  - `music.asm` - Generated CA65 assembly with music data
  - `nes.cfg` - MMC1 linker configuration
  - Build scripts for cross-platform compilation

#### Pattern Detection & Compression
- Uses `ParallelPatternDetector` for multi-core processing
- Automatically detects CPU cores and distributes work
- Achieves compression ratios up to 95.86x
- Smart sampling for very large files (maintains quality)
- Falls back gracefully if multiprocessing fails

#### Fast Parsing Strategy
- `parser_fast.py` performs **minimal** MIDI-to-frames conversion only
- Pattern detection, loop detection, and optimization are separate pipeline steps
- This separation enables 120x performance improvement
- Validation config uses relaxed settings for speed

#### Tempo Handling
- `EnhancedTempoMap` manages tempo changes with frame-accurate timing
- Supports tempo validation and optimization strategies
- Handles complex MIDI with multiple tempo changes

## Key Technical Constraints

### NES Hardware Limits
- 4 audio channels: Pulse1, Pulse2, Triangle, Noise (+ DPCM for drums)
- 60 FPS frame timing via NMI interrupts (critical - do not modify)
- NTSC frequency: 1.789773 MHz
- NES pitch tables are channel-specific (different for Pulse/Triangle)

### ROM Structure
- Always use MMC1 mapper configuration
- Header: 16 bytes iNES format
- PRG-ROM: 128KB (8 banks × 16KB)
- Reset vectors at $FFFA-$FFFF must point to valid code
- NMI handler must call music update at 60Hz

### Assembly Export
- `CA65Exporter.export_tables_with_patterns()` generates music.asm
- Uses pattern compression when pattern data provided
- Exports APU register writes ($4000-$4015)
- Must be compatible with `NESProjectBuilder` expectations

## Common Development Tasks

### Adding New Export Format
1. Create exporter in `exporter/` inheriting from `BaseExporter`
2. Implement `export()` method
3. Add format option to `main.py` run_export()
4. Add tests in `tests/test_exporter_integration.py`

### Modifying Pattern Detection
- Main logic in `tracker/pattern_detector_parallel.py`
- Uses worker pools - be careful with shared state
- Results must include: patterns dict, references dict, stats, variations
- Test with `tests/test_patterns.py`

### Debugging ROM Issues
1. Run `python debug/rom_diagnostics.py output.nes` for full analysis
2. Check for: size mismatch, zero bytes >70%, invalid reset vectors
3. Verify APU initialization patterns exist
4. Use `--verbose` flag for detailed output

### Performance Optimization
- Profile with `utils/profiling.py` utilities
- Check `benchmarks/performance_suite.py` for benchmark framework
- Pattern detection is the slowest stage - already parallelized
- Consider adjusting `max_workers` in `ParallelPatternDetector`

## Dependencies

Required packages (install via `pip install -r requirements.txt`):
- `mido==1.3.3` - MIDI file parsing
- `numpy==2.3.1` - Pattern detection algorithms
- `tqdm==4.67.1` - Progress bars
- `packaging==25.0` - Version utilities
- `PyYAML>=6.0.1` - Configuration file parsing
- `pytest>=7.4.0` - Testing framework
- `pytest-cov>=4.1.0` - Test coverage
- `psutil>=5.9.0` - Performance benchmarking

External tools:
- **CC65 toolchain** (ca65, ld65) - Required for NES ROM compilation
  - macOS: `brew install cc65`
  - Ubuntu/Debian: `sudo apt-get install cc65`
  - Windows: Download from https://cc65.github.io/

## Testing Strategy

- Unit tests for individual components
- Integration tests for pipeline stages
- Performance tests in `tests/test_performance_suite.py`
- ROM generation tests in `debug/rom_tester.py`
- Run full test suite before major changes
- Coverage analysis available via pytest-cov

## Project Status

✅ Fully operational end-to-end pipeline (see PROJECT_STATUS.md)
- Parses any MIDI file correctly
- Maps tracks to NES channels with intelligent priority
- Generates frame-accurate timing data
- Exports real assembly code with pattern compression
- Creates working MMC1 ROMs (128KB capacity)
- Produces ROMs that play music correctly on emulators and hardware
