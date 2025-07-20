# MIDI to NES Compiler

This project converts MIDI files into NES-compatible audio data that can be used in homebrew NES games or music applications.

## Overview

The compiler processes MIDI files through several stages:
1. **Parse** - Convert MIDI to intermediate JSON format
2. **Map** - Assign MIDI tracks to NES audio channels
3. **Frames** - Generate frame-by-frame audio data with envelope processing
4. **Pattern Detection** - Detect and compress repeating musical patterns
5. **Export** - Output as CA65 assembly or FamiTracker format

## Features

### Core Features
- Complete MIDI parsing pipeline
- Intelligent channel mapping with priority system
- Accurate NES pitch tables with per-channel processing
- ADSR envelope processing for pulse channels
- Multiple duty cycle patterns
- Pattern detection and compression
- CA65 and FamiTracker export formats

### Advanced Features
- Multi-song support with bank switching
- Segment management for complex compositions
- Enhanced tempo handling with accurate timing
- Pattern and loop point support
- Basic drum mapping and DPCM support

## Usage

Basic usage:
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
