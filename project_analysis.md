# MIDI to NES Compiler Project Analysis

## Project Overview
This project converts MIDI files into NES-compatible audio data for use in homebrew NES games or music applications.

### Pipeline Stages
1. **Parse**: Convert MIDI to intermediate JSON format
   - Implemented in parser.py
   - Uses mido library for MIDI parsing
   - Converts to frame-based intermediate format
   - Current tempo handling is basic

2. **Map**: Assign MIDI tracks to NES channels
   - Implemented in track_mapper.py
   - Maps to available NES channels:
     - 2 pulse channels
     - 1 triangle channel
     - 1 noise channel
     - 1 DPCM channel
   - Basic heuristic-based mapping

3. **Frames**: Generate frame-by-frame audio data
   - Implemented in nes_emulator_core.py
   - Uses simplified pitch conversion
   - Lacks proper envelope and duty cycle handling
   - Frame rate fixed at 60Hz

4. **Export**: Output as assembly or FamiTracker format
   - Two export formats supported:
     - CA65 assembly (exporter_ca65.py)
     - NSF text format (exporter_nsftxt.py)
   - Basic implementation without advanced features

## Current Implementation Analysis

#### Core Components

1. **MIDI Parsing (`parser.py`)**
   - **Functionality**: Converts MIDI files to a frame-based intermediate JSON format.
   - **Details**:
     - Uses `mido` library for MIDI parsing.
     - Handles basic note on/off events.
     - Tracks tempo changes but does not fully implement them.
     - Converts time to a 60Hz frame rate.
   - **Current Limitations**:
     - Limited handling of MIDI control changes (CC)
     - Basic tempo change tracking without dynamic adjustment
     - No support for pitch bend or modulation
     - No handling of MIDI program changes

2. **Track Mapping (`track_mapper.py`)**
   - **Functionality**: Assigns MIDI tracks to NES audio channels.
   - **Details**:
     - Maps to available NES channels: 2 pulse, 1 triangle, 1 noise, 1 DPCM.
     - Uses a basic heuristic-based mapping strategy based on pitch.
     - Implements arpeggio fallback for pulse2 channel.
     - Maps drum events to DPCM and noise channels using drum_engine.py.
   - **Current Limitations**:
     - Simple priority system without optimization
     - Limited polyphony handling (only basic arpeggio)
     - No intelligent track analysis for instrument types
     - No dynamic channel reassignment during playback

3. **Audio Generation (`nes_emulator_core.py`)**
   - **Functionality**: Generates frame-by-frame audio data.
   - **Details**:
     - Uses accurate NES note table for pitch conversion.
     - Handles basic volume control and note duration.
     - Processes tracks for pulse, triangle, noise, and DPCM channels.
   - **Current Limitations**:
     - Missing envelope processing (ADSR)
     - No duty cycle pattern implementation
     - Basic volume handling without dynamics
     - No effects processing (vibrato, slides, etc.)
     - Limited note duration handling

4. **Export System**
   - **Functionality**: Outputs data as CA65 assembly or FamiTracker format.
   - **Details**:
     - Two export formats supported:
       - CA65 assembly (exporter_ca65.py)
       - NSF text format (exporter_nsftxt.py)
     - Generates playable code for NES hardware.
   - **Current Limitations**:
     - Basic implementation without memory optimization
     - No support for multiple songs or segments
     - Limited metadata handling
     - No compression or pattern reuse
     - Missing advanced audio features (effects, etc.)

### Tasks to Implement

1. **Envelope and Duty Cycle Configuration**
   - **Priority**: High
   - **Details**:
     - Implement ADSR envelope processing in nes_emulator_core.py
     - Add envelope data structures to frame generation
     - Integrate duty cycle patterns from nes_audio_constants.py
     - Add envelope control bytes to CA65 export
     - Required changes:
       - nes_emulator_core.py: Add EnvelopeProcessor class
       - track_mapper.py: Add envelope mapping logic
       - exporter_ca65.py: Add envelope byte sequence generation

2. **NES Pitch Tables**
   - **Priority**: High
   - **Details**:
     - Add per-channel pitch range validation
     - Implement pitch bending and slides
     - Add octave shifting for out-of-range notes
     - Required changes:
       - nes_emulator_core.py:
         - Add PitchProcessor class
         - Implement channel-specific pitch limits
         - Add pitch bend support

3. **Tempo and Pattern Control**
   - **Priority**: Medium
   - **Details**:
     - Enhance tempo change handling in parser.py
     - Add pattern jump markers and loop points
     - Implement song structure metadata
     - Required changes:
       - parser.py: Enhance tempo tracking
       - Add new TempoProcessor class
       - Add pattern/loop metadata to frame data

4. **Multi-song Support**
   - **Priority**: Medium
   - **Details**:
     - Add song segment definitions
     - Implement memory-efficient segment storage
     - Add segment metadata and jump tables
     - Required changes:
       - exporter_ca65.py:
         - Add segment data structures
         - Implement jump tables
         - Add segment metadata handling

### Technical Debt and Issues

1. **Parser Limitations**
   - No handling of MIDI control changes.
   - Limited tempo change support.
   - Basic track naming.

2. **Mapping Inefficiencies**
   - Simple priority system.
   - No optimization for channel usage.
   - Limited polyphony handling.

3. **Audio Generation Gaps**
   - Missing envelope support.
   - Inaccurate pitch conversion.
   - Basic volume handling.

4. **Export Limitations**
   - Minimal CA65 implementation.
   - No optimization of output.
   - Missing advanced features.

### Recommended Implementation Order

1. NES Pitch Tables
2. Envelope/Duty Configurations
3. Tempo/Pattern Control
4. Multi-song Support

### Dependencies and Requirements

- **External Libraries**: mido, json, pathlib
- **Development Tools**: Python 3.x, CA65 assembler, NES emulator

### Testing Considerations

1. **Unit Tests Needed**
   - Pitch conversion accuracy.
   - Envelope processing.
   - Frame generation.
   - Export format validation.

2. **Integration Tests**
   - Full pipeline verification.
   - Multi-song handling.
   - Performance testing.

3. **Audio Testing**
   - Waveform verification.
   - Channel isolation tests.
   - Timing accuracy checks.

### Future Enhancements

1. **Advanced Features**
   - Effect support.
   - Loop points.
   - Fine-tuning controls.

2. **Optimization**
   - Data compression.
   - Pattern reuse.
   - Memory optimization.

3. **Tool Integration**
   - GUI frontend.
   - Real-time preview.
   - Direct emulator integration.

### Core Components

1. **MIDI Parsing (parser.py)**
   - Frame-based event system
   - Handles basic note on/off events
   - Tempo changes tracked but not fully implemented
   - Time conversion to 60Hz frame rate

2. **Track Mapping (track_mapper.py)**
   - Simple priority-based channel assignment
   - Basic drum pattern recognition
   - No optimization for channel reuse
   - Limited handling of polyphony

3. **Audio Generation (nes_emulator_core.py)**
   - Simplified NES_NOTE_TABLE implementation
   - Basic volume handling
   - Missing envelope configurations
   - Missing duty cycle patterns

4. **Export System**
   - CA65 export is placeholder only
   - NSF export handles basic note data
   - No support for multiple songs
   - Missing advanced audio features

### Data Flow
1. MIDI → JSON (parsed.json)
2. JSON → Channel mapping (mapped.json)
3. Mapping → Frame data (frames.json)
4. Frames → Assembly/NSF output

## Tasks to Implement

### 1. Envelope and Duty Cycle Configuration
**Priority: High**
- Add envelope data structures
- Implement duty cycle patterns
- Create byte sequence generation
- Integrate with CA65 export

Required changes:
- nes_emulator_core.py: Add envelope processing
- exporter_ca65.py: Add byte sequence generation
- New module needed for envelope definitions

### 2. NES Pitch Tables
**Priority: High**
- Replace simplified pitch conversion
- Implement accurate frequency tables
- Add per-channel pitch limitations

Files to modify:
- nes_emulator_core.py:
  - Replace NES_NOTE_TABLE
  - Add channel-specific tables
  - Implement proper frequency calculation

### 3. Tempo and Pattern Control
**Priority: Medium**
- Add tempo change handling
- Implement pattern jumps
- Support song structure markers

Required changes:
- parser.py: Enhanced tempo tracking
- track_mapper.py: Pattern recognition
- nes_emulator_core.py: Tempo processing

### 4. Multi-song Support
**Priority: Medium**
- Add song segmentation
- Implement segment management
- Update CA65 export format

Files to modify:
- exporter_ca65.py:
  - Add segment support
  - Implement song data blocks
  - Add segment references

## Technical Debt and Issues

1. **Parser Limitations**
   - No handling of MIDI control changes
   - Limited tempo change support
   - Basic track naming

2. **Mapping Inefficiencies**
   - Simple priority system
   - No optimization for channel usage
   - Limited polyphony handling

3. **Audio Generation Gaps**
   - Missing envelope support
   - Inaccurate pitch conversion
   - Basic volume handling

4. **Export Limitations**
   - Minimal CA65 implementation
   - No optimization of output
   - Missing advanced features

## Recommended Implementation Order

1. NES Pitch Tables
   - Most fundamental to sound quality
   - Affects all channels
   - Required for accurate playback

2. Envelope/Duty Configs
   - Builds on pitch implementation
   - Improves sound quality
   - Needed for authentic NES sound

3. Tempo/Pattern Control
   - Enhances playback control
   - Improves song structure
   - Enables more complex compositions

4. Multi-song Support
   - Builds on other features
   - Adds project organization
   - Enables game integration

## Project Structure and Data Flow

### File Structure

```
├── main.py                 # Main entry point and command-line interface
├── parser.py               # MIDI parsing module
├── track_mapper.py         # Channel assignment module
├── nes_emulator_core.py    # Frame generation and audio processing
├── nes_audio_constants.py  # NES audio hardware constants
├── exporter.py             # Base exporter functionality
├── exporter_ca65.py        # CA65 assembly exporter
├── exporter_nsftxt.py      # FamiTracker text format exporter
├── drum_engine.py          # Drum pattern detection and mapping
├── dpcm_converter.py       # WAV to DPCM sample conversion
├── dpcm_index.json         # DPCM sample metadata
└── dmc/                    # DPCM sample files
```

### Data Flow Pipeline

1. **MIDI Parsing** (parser.py)
   - Input: MIDI file (.mid)
   - Process: Convert MIDI events to frame-based events
   - Output: JSON with track events at specific frames
   - Command: `python main.py parse input.mid parsed.json`

2. **Track Mapping** (track_mapper.py)
   - Input: Parsed JSON from step 1
   - Process: Assign MIDI tracks to NES channels
   - Output: JSON with NES channel assignments
   - Command: `python main.py map parsed.json mapped.json`

3. **Frame Generation** (nes_emulator_core.py)
   - Input: Mapped JSON from step 2
   - Process: Generate frame-by-frame audio data
   - Output: JSON with frame data for each channel
   - Command: `python main.py frames mapped.json frames.json`

4. **Export** (exporter_ca65.py / exporter_nsftxt.py)
   - Input: Frame JSON from step 3
   - Process: Convert to target format (CA65 or NSF text)
   - Output: Assembly code (.s) or FamiTracker text (.txt)
   - Command: `python main.py export frames.json output.s --format ca65`

### Data Transformations

1. **MIDI → Parsed JSON**
   - MIDI events → Frame-based events
   - Tempo calculations → Frame timing
   - Track metadata → Channel hints

2. **Parsed JSON → Mapped JSON**
   - Track events → Channel assignments
   - Note clustering → Polyphony handling
   - Drum detection → DPCM/noise mapping

3. **Mapped JSON → Frame JSON**
   - Channel events → Frame-by-frame data
   - Note properties → NES register values
   - Duration → Note sustain

4. **Frame JSON → Output Format**
   - Frame data → Assembly code / FamiTracker format
   - Channel data → Register writes
   - Metadata → Song information

## Dependencies and Requirements

### External Libraries
- mido: MIDI file parsing
- json: Data serialization
- pathlib: File operations
- numpy: Used in DPCM conversion
- wave: WAV file handling

### Development Tools
- Python 3.x
- CA65 assembler (for testing output)
- NES emulator (for audio verification)
- FamiTracker (for NSF text format testing)

## Testing Considerations

1. **Unit Tests Needed**
   - Pitch conversion accuracy
   - Envelope processing
   - Frame generation
   - Export format validation

2. **Integration Tests**
   - Full pipeline verification
   - Multi-song handling
   - Performance testing

3. **Audio Testing**
   - Waveform verification
   - Channel isolation tests
   - Timing accuracy checks

## Future Enhancements

1. **Advanced Features**
   - Effect support
   - Loop points
   - Fine-tuning controls

2. **Optimization**
   - Data compression
   - Pattern reuse
   - Memory optimization

3. **Tool Integration**
   - GUI frontend
   - Real-time preview
   - Direct emulator integration
