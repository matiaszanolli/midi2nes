# MIDI to NES Compiler

This project converts MIDI files into NES-compatible audio data that can be used in homebrew NES games or music applications.

## Overview

The compiler processes MIDI files through several stages:
1. **Parse** - Convert MIDI to intermediate JSON format
2. **Map** - Assign MIDI tracks to NES audio channels (2 pulse, 1 triangle, 1 noise, 1 DPCM)
3. **Frames** - Generate frame-by-frame audio data
4. **Export** - Output as CA65 assembly or FamiTracker format

## NES Audio Channels

- **Pulse 1 & 2**: Melody and harmony with duty cycle control
- **Triangle**: Bass lines (no volume control)
- **Noise**: Percussion and sound effects
- **DPCM**: Drum samples and voice

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
```

## Current Status

The basic pipeline is implemented but several features are still needed:
- Proper NES pitch tables
- Envelope and duty cycle configurations
- Tempo control and pattern jumps
- Multiple song support
- Better drum mapping