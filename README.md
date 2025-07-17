# MIDI to NES Compiler

This project converts MIDI files into NES-compatible audio data that can be used in homebrew NES games or music applications.

## Overview

The compiler processes MIDI files through several stages:
1. **Parse** - Convert MIDI to intermediate JSON format
2. **Map** - Assign MIDI tracks to NES audio channels (2 pulse, 1 triangle, 1 noise, 1 DPCM)
3. **Frames** - Generate frame-by-frame audio data with envelope processing
4. **Export** - Output as CA65 assembly or FamiTracker format

## NES Audio Channels

- **Pulse 1 & 2**: Melody and harmony with duty cycle control and envelope processing
- **Triangle**: Bass lines (no volume control)
- **Noise**: Percussion and sound effects
- **DPCM**: Drum samples and voice

## Features

- ✅ Complete MIDI parsing pipeline
- ✅ Channel mapping with priority system
- ✅ Accurate NES pitch tables with per-channel processing
- ✅ ADSR envelope processing for pulse channels
- ✅ Multiple duty cycle patterns
- ✅ Basic drum mapping and DPCM support
- ✅ CA65 and FamiTracker export formats

## Usage

```bash
# Parse MIDI file
python main.py parse input.mid parsed.json

# Map tracks to NES channels
python main.py map parsed.json mapped.json

# Generate frame data
python main.py frames mapped.json frames.json

# Export to assembly
python main.py export frames.json output.s --format ca65

# Prepare output project
python main.py prepare output.s output_project_dir
```

## Current Status and Roadmap

### Completed (v0.2.0)
- ✅ Basic MIDI parsing and channel mapping
- ✅ Accurate NES pitch tables implementation
- ✅ ADSR envelope processing
- ✅ Duty cycle patterns
- ✅ Comprehensive test coverage

### In Progress (v0.3.0)
- 🔄 Enhanced tempo handling
- 🔄 Pattern and loop support
- 🔄 Multi-song capability
- 🔄 Advanced drum mapping

### Planned (v0.4.0)
- Memory optimization
- Pattern compression
- Performance improvements
- Real-time preview capability

### Future (v1.0.0)
- GUI frontend
- Direct emulator integration
- Effect support
- Fine-tuning controls

## Development

The project uses Python 3.x and includes a comprehensive test suite. To run the tests:

```bash
python -m unittest discover tests
```

## Contributing

Contributions are welcome! Please check the issues page for current tasks and feature requests.