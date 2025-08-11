# MIDI to NES Compiler

🎵 **High-performance MIDI to NES ROM compiler with advanced pattern detection and multiprocessing optimization**

Convert MIDI files into playable NES ROMs or use the generated audio data in homebrew NES games and music applications.

[![Performance](https://img.shields.io/badge/Performance-120x%20Faster-brightgreen)](#performance)
[![CPU](https://img.shields.io/badge/CPU-Multi--Core-blue)](#multiprocessing)
[![Patterns](https://img.shields.io/badge/Patterns-95.86x%20Compression-orange)](#pattern-detection)

## ⚡ Quick Start

**One-command MIDI to NES ROM conversion:**
```bash
python main.py input.mid output.nes
```

**That's it!** The compiler handles the entire pipeline automatically:
1. **Fast MIDI Parsing** - Optimized parser with 120x performance improvement
2. **Intelligent Channel Mapping** - Automatic track-to-NES-channel assignment
3. **Frame Generation** - High-accuracy NES audio frame data
4. **Parallel Pattern Detection** - Multi-core pattern compression (up to 95x compression)
5. **NES ROM Compilation** - Ready-to-run NES ROM file

## 🚀 Performance

### Real-World Performance Results
- **120+ times faster** than previous versions
- **Multi-core processing** using all available CPU cores
- **Complex MIDI files** (51KB, 15 tracks, 13,362 events) processed in ~15 seconds
- **Pattern compression** achieving up to 95.86x compression ratios
- **Smart sampling** for very large files with quality preservation

### Test Results (input.mid - 51KB, 15 tracks)
| Implementation | Time | Status |
|---|---|---|
| **Original** | ∞ (timeout) | ❌ Failed |
| **Optimized** | 15 seconds | ✅ Success |

## 📋 Features

### Core Features
- **🏃‍♂️ High-performance MIDI parsing** with optimized algorithms
- **🧠 Intelligent channel mapping** with priority system
- **🎯 Accurate NES pitch tables** with per-channel processing
- **📈 ADSR envelope processing** for pulse channels
- **🔄 Multiple duty cycle patterns** for rich sound
- **🗜️ Advanced pattern detection** with multiprocessing
- **📤 Multiple export formats** (CA65, NSF, FamiTracker)

### Advanced Features
- **⚡ Parallel processing** utilizing all CPU cores
- **🎼 Multi-song support** with bank switching
- **📊 Segment management** for complex compositions
- **⏱️ Enhanced tempo handling** with accurate timing
- **🔁 Pattern and loop point support**
- **🥁 Drum mapping and DPCM support**
- **📈 Visual progress bars** with real-time speed and completion tracking
- **🛡️ Graceful fallback** for compatibility

## 🎮 Usage Examples

### Simple ROM Generation
```bash
# Convert MIDI directly to NES ROM
python main.py song.mid
# Creates: song.nes (ready to play on emulators)

# Specify output filename
python main.py song.mid my_game.nes
```

### Advanced Pipeline Control
```bash
# Step-by-step processing for debugging/customization
python main.py parse input.mid parsed.json
python main.py map parsed.json mapped.json
python main.py frames mapped.json frames.json
python main.py detect-patterns frames.json patterns.json
python main.py export frames.json output.s --format ca65 --patterns patterns.json
python main.py prepare output.s nes_project/
```

### Development and Testing
```bash
# Fast parsing only (for development)
python tracker/parser_fast.py input.mid output.json

# Run performance benchmarks
python main.py benchmark run input.mid

# Configuration management
python main.py config init my_config.yaml
python main.py config validate my_config.yaml

# Song bank management
python main.py song add input.mid --bank my_songs.json --name "My Song"
python main.py song list my_songs.json
```

## 🔧 Installation

### Prerequisites
- Python 3.8 or higher
- **CC65 toolchain** (for NES ROM compilation)
- Required Python packages (install via requirements.txt)

### Quick Install
```bash
# Clone the repository
git clone https://github.com/matiaszanolli/midi2nes.git
cd midi2nes

# Install dependencies
pip install -r requirements.txt

# Install CC65 toolchain
# macOS:
brew install cc65

# Ubuntu/Debian:
sudo apt-get install cc65

# Windows: Download from https://cc65.github.io/
```

## 🖥️ Multiprocessing

### How It Works
The MIDI2NES compiler automatically detects your system's CPU cores and distributes pattern detection work across multiple processes:

```
🚀 Starting parallel pattern detection with 7 workers
🔧 Created 236 work chunks for parallel processing
Processing pattern chunks: 100%|████████████| 236/236 [00:12<00:00, 19.2chunk/s, patterns=5505]
📈 Found 5505 candidate patterns
✅ Parallel pattern detection completed in 12.49s
```

### Performance Scaling
- **Single-core**: Traditional processing (legacy compatibility)
- **Multi-core**: Automatic work distribution across all CPU cores
- **Large files**: Smart sampling maintains quality while ensuring reasonable processing times
- **Fallback safety**: Graceful degradation if multiprocessing fails

### System Requirements
- **Minimum**: Single-core system (fallback mode)
- **Recommended**: Multi-core CPU for optimal performance
- **Memory**: 1GB+ RAM for large MIDI files
- **Storage**: Minimal disk space for temporary files

## 🎯 Pattern Detection

### Advanced Compression
The parallel pattern detection system identifies and compresses repeating musical patterns:

- **Pattern Recognition**: Finds exact and transposed musical phrases
- **Variation Detection**: Handles pitch shifts and volume changes
- **Compression Scoring**: Optimizes for NES memory constraints
- **Non-overlapping Selection**: Ensures optimal pattern selection

### Example Output
```
📈 Found 19,285 candidate patterns
🔍 Selected 23 optimal patterns
📦 Compression ratio: 95.86x
```

## 🎼 Supported Formats

### Input Formats
- **MIDI Files** (.mid, .midi) - Standard MIDI format
- **All MIDI Types** - Format 0, 1, and 2 supported
- **Complex Files** - Multi-track, tempo changes, large files

### Output Formats
- **NES ROM** (.nes) - Ready-to-run NES ROM files
- **CA65 Assembly** (.s) - For integration with NES projects
- **NSF Audio** (.nsf) - NES Sound Format for music playback
- **FamiTracker** (.txt) - Import into FamiTracker editor

## 📊 Performance Benchmarks

### File Size Performance
| File Size | Events | Processing Time | Pattern Detection |
|---|---|---|---|
| Small (<1KB) | <100 | <1s | Instant |
| Medium (1-10KB) | 100-1K | 1-5s | <5s |
| Large (10-50KB) | 1K-10K | 5-15s | 5-15s |
| Very Large (50KB+) | 10K+ | 15-30s | Smart sampling |

### Real-World Examples
- **Simple melodies**: <1 second total processing
- **Complex orchestral**: 15-30 seconds with high compression
- **Game soundtracks**: Optimal pattern detection and ROM generation

## 🐛 Debug Tools

MIDI2NES includes a comprehensive suite of debugging and analysis tools to help troubleshoot conversion issues and analyze output quality.

### Quick Debug Commands
```bash
# Check audio patterns in generated ROM
python -m debug.audio_checker output.nes

# Analyze pattern compression effectiveness
python -m debug.pattern_analysis output/patterns

# Examine music structure in ROM
python -m debug.music_structure_analyzer output.nes

# Test ROM generation pipeline
python -m debug.rom_tester

# Performance analysis of MIDI parsing
python -m debug.performance_analyzer
```

### Available Debug Tools
- **`audio_checker`**: APU pattern validation in NES ROMs
- **`pattern_analysis`**: Pattern detection result analysis
- **`ca65_inspector`**: Assembly output inspection
- **`frame_analyzer`**: Frame generation debugging
- **`music_structure_analyzer`**: Comprehensive ROM music analysis
- **`pattern_reference_debugger`**: Pattern reference table analysis
- **`performance_analyzer`**: MIDI parser performance testing
- **`rom_tester`**: Complete pipeline validation

### Programmatic Usage
```python
from debug import (
    check_audio_simple,
    analyze_patterns,
    test_rom_generation
)

# Validate ROM audio patterns
check_audio_simple("output.nes")

# Run full test suite
success = test_rom_generation()
```

For detailed debug tool documentation, see [debug/README.md](debug/README.md).

## 🛠️ Development

### Architecture
```
📁 midi2nes/
├── 🎵 tracker/           # Core MIDI processing
│   ├── parser_fast.py    # Optimized MIDI parser
│   ├── pattern_detector_parallel.py  # Multi-core pattern detection
│   └── tempo_map.py      # Advanced tempo handling
├── 🎮 nes/              # NES-specific components
├── 📤 exporter/         # Output format generators
├── 🔧 config/           # Configuration management
├── 🐛 debug/            # Debugging and analysis tools
│   ├── audio_checker.py      # ROM audio validation
│   ├── pattern_analysis.py   # Pattern compression analysis
│   ├── performance_analyzer.py # MIDI parser benchmarking
│   └── rom_tester.py         # Complete pipeline testing
└── 📊 benchmarks/       # Performance testing
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Run the test suite: `python -m pytest`
4. Submit a pull request

### Testing
```bash
# Run all tests
python -m pytest

# Run performance tests
python test_input_performance.py

# Test ROM generation
python test_rom_generation.py
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Acknowledgments

- NES development community for technical documentation
- CC65 development team for the excellent toolchain
- Contributors and testers who helped optimize performance

## 🔗 Links

- [GitHub Repository](https://github.com/matiaszanolli/midi2nes)
- [Performance Documentation](PERFORMANCE_OPTIMIZATIONS.md)
- [CC65 Toolchain](https://cc65.github.io/)
- [NES Development Resources](https://wiki.nesdev.org/)
