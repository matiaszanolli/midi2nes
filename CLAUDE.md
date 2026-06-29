# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIDI2NES is a high-performance MIDI to NES ROM compiler. It converts MIDI files into playable NES ROMs or generates audio data for homebrew NES games. The system features 120x faster parsing, multi-core pattern detection (95x compression), and complete NES ROM generation pipeline.

## Development Commands

### Core Pipeline Commands

```bash
# Single-command MIDI to NES ROM conversion (parse → map → frames → patterns → export → prepare → compile)
# When the first non-flag arg is NOT a known subcommand, main.py runs the full pipeline (run_full_pipeline).
python main.py input.mid output.nes      # output defaults to input.nes if omitted

# Useful top-level flags for the default pipeline:
python main.py --arranger input.mid out.nes        # Intelligent voice allocation + arpeggiation (polyphony)
python main.py --no-patterns input.mid out.nes     # Skip pattern compression (direct export, full fidelity)
python main.py --debug input.mid out.nes           # ROM with on-screen APU/frame/error overlay (dev)
python main.py --skip-validation input.mid out.nes # Skip post-compile ROM validation
python main.py -v input.mid out.nes                # Verbose (prints full traceback on failure)

# Step-by-step pipeline for debugging (subcommands)
python main.py parse input.mid parsed.json          # Fast MIDI parsing (tracker/parser_fast.py)
python main.py map parsed.json mapped.json          # Track to NES channel mapping
python main.py frames mapped.json frames.json       # Frame generation
python main.py detect-patterns frames.json patterns.json  # Pattern detection
python main.py export frames.json music.asm --format ca65 --patterns patterns.json
python main.py prepare music.asm nes_project/       # Prepare NES project (default mapper: MMC3)

# Other subcommands: `config init|validate`, `song add|list|remove` (JSON song-bank storage/analysis only — not compiled to ROM), `benchmark run|memory`
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

# Full ROM build/playback test harness
python -m debug.rom_tester

# Performance benchmarking (via main.py, not a debug module)
python main.py benchmark run [files...] [--memory]
python main.py benchmark memory
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
MIDI → Parse → Map/Arrange → Frames → Patterns → Export → Project → Compile → ROM
       (fast)   (NES chans)  (60fps)  (compress) (CA65)   (builder)  (CC65)    (.nes)
```

Two front-ends select how MIDI tracks become NES channels:
- **Legacy mode** (default): `track_mapper.assign_tracks_to_nes_channels` + `NESEmulatorCore.process_all_tracks`.
- **Arranger mode** (`--arranger`): `arranger.arrange_for_nes` does role analysis, GM-instrument mapping, smart channel allocation, and arpeggiation for polyphonic content. Both produce the same `frames` dict consumed downstream.

The full pipeline (`run_full_pipeline` in `main.py`) runs everything in a temp dir and ends by calling `compiler.compile_rom`, so the single-command form needs the CC65 toolchain installed.

### Key Directories

- **`tracker/`** - MIDI processing core
  - `parser_fast.py` - Optimized MIDI parser (120x faster); `parser.py` is the older full parser
  - `pattern_detector_parallel.py` - Multi-core pattern detection (`ParallelPatternDetector`)
  - `pattern_detector.py` - Single-process `EnhancedPatternDetector` (fallback + used by `detect-patterns`)
  - `tempo_map.py` - Enhanced tempo handling
  - `track_mapper.py` - NES channel assignment (legacy mode)
  - `loop_manager.py` - Loop point detection

- **`arranger/`** - Intelligent arrangement (`--arranger` mode)
  - `role_analyzer.py` - Voice role detection (bass/melody/harmony)
  - `voice_allocator.py` - Smart channel allocation + arpeggiation
  - `gm_instruments.py` - GM program → NES channel/duty mapping
  - `pipeline_integration.py` - Exposes `arrange_for_nes`

- **`mappers/`** - NES mapper abstraction (`base.py` + `nrom.py`, `mmc1.py`, `mmc3.py`)
  - `factory.py` - `MapperFactory` selects/auto-detects a mapper by data size

- **`compiler/`** - ROM compilation via CC65
  - `compiler.py` - `ROMCompiler` / `compile_rom` (validate → assemble → link → verify)
  - `cc65_wrapper.py` - Wraps `ca65`/`ld65` invocation

- **`core/`** - Shared data types (`dto.py`, `types.py`) and `exceptions.py` (`CompilationError`, `ValidationError`)

- **`nes/`** - NES-specific components
  - `emulator_core.py` - Frame generation
  - `project_builder.py` - `NESProjectBuilder`: writes main.asm/music.asm/nes.cfg + build scripts
  - `pitch_table.py` - NES frequency tables
  - `envelope_processor.py` - ADSR envelope handling
  - `song_bank.py` - Song-bank storage/analysis (`song` subcommands; JSON banks only — there is no song-bank → ROM build route yet, see docs/ROADMAP.md)

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

#### Mapper Selection & ROM Generation
- Mappers are pluggable via `mappers/` (NROM, MMC1, MMC3) behind `BaseMapper`; `MapperFactory` can auto-select by data size.
- The `prepare` subcommand and `run_full_pipeline` currently instantiate `NESProjectBuilder` with **`MMC3Mapper`** (not MMC1 — the older docs/PROJECT_STATUS may still say MMC1). When changing mapper behavior, check `main.py:run_prepare` and the builder's mapper argument.
- `NESProjectBuilder` generates complete NES projects with:
  - `main.asm` - NMI-based 60Hz timing system (critical for playback)
  - `music.asm` - Generated CA65 assembly with music data
  - `nes.cfg` - mapper-specific linker configuration
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
