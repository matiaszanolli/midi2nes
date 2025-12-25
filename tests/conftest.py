"""
Shared pytest fixtures and configuration for MIDI2NES tests.

This module provides:
- Shared fixtures for temp directories, MIDI files, ROM files
- Helper functions to generate ROM files for testing
- Pytest markers for categorizing tests
- Common test utilities
"""

import pytest
import tempfile
import struct
from pathlib import Path
import mido


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (>5 seconds, skipped by default)"
    )
    config.addinivalue_line(
        "markers", "requires_cc65: requires CC65 toolchain installed"
    )
    config.addinivalue_line(
        "markers", "integration: integration tests (test entire pipeline)"
    )


# ============================================================================
# Temporary Directory and File Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create and clean up a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_dir(temp_dir):
    """Create a NES project directory."""
    project_path = temp_dir / "nes_project"
    project_path.mkdir()
    return project_path


# ============================================================================
# MIDI File Fixtures
# ============================================================================

@pytest.fixture
def minimal_midi_file(temp_dir):
    """Create a minimal MIDI file with 2 simple notes.

    Returns a Path to a MIDI file with:
    - 1 track
    - 2 notes (C4 and E4)
    - 120 BPM
    """
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Add tempo
    track.append(mido.MetaMessage('set_tempo', tempo=500000))  # 120 BPM

    # Add notes
    track.append(mido.Message('note_on', note=60, velocity=64, time=0))
    track.append(mido.Message('note_off', note=60, velocity=0, time=480))
    track.append(mido.Message('note_on', note=64, velocity=64, time=0))
    track.append(mido.Message('note_off', note=64, velocity=0, time=480))
    track.append(mido.MetaMessage('end_of_track', time=0))

    midi_path = temp_dir / "minimal.mid"
    mid.save(midi_path)
    return midi_path


@pytest.fixture
def complex_midi_file(temp_dir):
    """Create a more complex MIDI file with multiple tracks and tempo changes.

    Returns a Path to a MIDI file with:
    - 3 tracks (melody, harmony, bass)
    - Multiple notes
    - Tempo changes
    """
    mid = mido.MidiFile()

    # Track 1: Melody
    track1 = mido.MidiTrack()
    mid.tracks.append(track1)
    track1.append(mido.MetaMessage('set_tempo', tempo=500000))  # 120 BPM
    for note in [60, 62, 64, 65, 67]:
        track1.append(mido.Message('note_on', note=note, velocity=64, time=0))
        track1.append(mido.Message('note_off', note=note, velocity=0, time=240))
    track1.append(mido.MetaMessage('end_of_track', time=0))

    # Track 2: Harmony (chords)
    track2 = mido.MidiTrack()
    mid.tracks.append(track2)
    for note in [48, 50, 52]:
        track2.append(mido.Message('note_on', note=note, velocity=64, time=0))
        track2.append(mido.Message('note_off', note=note, velocity=0, time=240))
    track2.append(mido.MetaMessage('end_of_track', time=0))

    # Track 3: Bass
    track3 = mido.MidiTrack()
    mid.tracks.append(track3)
    for note in [36, 38, 40]:
        track3.append(mido.Message('note_on', note=note, velocity=64, time=0))
        track3.append(mido.Message('note_off', note=note, velocity=0, time=480))
    track3.append(mido.MetaMessage('end_of_track', time=0))

    midi_path = temp_dir / "complex.mid"
    mid.save(midi_path)
    return midi_path


# ============================================================================
# Assembly File Fixtures
# ============================================================================

@pytest.fixture
def minimal_music_asm(temp_dir):
    """Create a minimal valid music.asm file.

    Returns a Path to a music.asm with:
    - init_music function
    - update_music function
    - Basic APU initialization pattern
    """
    music_asm = temp_dir / "music.asm"
    music_asm.write_text("""; Minimal music.asm for NES
; Exports init_music and update_music functions

.importzp frame_counter, ptr1, temp1, temp2

.segment "CODE"

; APU initialization - CRITICAL for ROM validation
init_music:
    ; Enable APU and all channels
    lda #$0F
    sta $4015                    ; APU Enable - CRITICAL PATTERN

    ; Initialize pulse 1
    lda #$BF
    sta $4000                    ; Pulse1 control - GOOD PATTERN

    ; Initialize pulse 2
    lda #$BF
    sta $4004                    ; Pulse2 control - GOOD PATTERN

    ; Initialize triangle
    lda #$80
    sta $4008                    ; Triangle control

    ; Initialize noise
    lda #$30
    sta $400C                    ; Noise control

    rts

; Music update - called every frame
update_music:
    ; Simple frame counter
    inc frame_counter
    bne :+
    inc frame_counter+1
:
    rts
""")
    return music_asm


# ============================================================================
# ROM File Fixtures
# ============================================================================

def _create_ines_header(prg_banks: int, chr_banks: int, mapper: int = 1, mirroring: int = 0) -> bytes:
    """Create an iNES header.

    Args:
        prg_banks: Number of 16KB PRG-ROM banks
        chr_banks: Number of 8KB CHR-ROM banks
        mapper: Mapper number (1 = MMC1)
        mirroring: 0 = horizontal, 1 = vertical

    Returns:
        16-byte iNES header
    """
    header = bytearray(16)
    header[0:3] = b'NES'
    header[3] = 0x1A
    header[4] = prg_banks
    header[5] = chr_banks
    header[6] = (mapper & 0x0F) | (mirroring << 0)  # Mapper low nibble + mirroring
    header[7] = (mapper & 0xF0)  # Mapper high nibble
    header[8:16] = b'\x00' * 8   # Padding
    return bytes(header)


def _create_valid_rom_binary() -> bytes:
    """Create a minimal valid NES ROM binary.

    Returns:
        Complete ROM file data with:
        - Valid iNES header
        - APU initialization pattern
        - Valid reset vectors
        - Some assembly code
    """
    # iNES header: 8 PRG banks (128KB), 0 CHR, Mapper 1 (MMC1)
    header = _create_ines_header(8, 0, mapper=1)

    # PRG-ROM data (128KB) - filled with varied patterns, not zeros
    prg_rom = bytearray(128 * 1024)

    # Fill with repeating pattern to avoid excessive zeros
    # Use a pattern that looks like actual code
    pattern = b'\xA9\x00\x8D\x15\x40\x4C\x00\x80'  # LDA #$00, STA $4015, JMP $8000
    for i in range(0, len(prg_rom), len(pattern)):
        remaining = min(len(pattern), len(prg_rom) - i)
        prg_rom[i:i+remaining] = pattern[:remaining]

    # Insert APU initialization patterns at specific locations
    apu_patterns = [
        (100, b'\xA9\x0F\x8D\x15\x40'),      # APU Enable pattern (CRITICAL)
        (200, b'\xA9\xBF\x8D\x00\x40'),      # Pulse1 Init (GOOD)
        (300, b'\xA9\xBF\x8D\x04\x40'),      # Pulse2 Init (GOOD)
        (400, b'\xA9\x80\x8D\x08\x40'),      # Triangle Init
        (500, b'\xA9\x30\x8D\x0C\x40'),      # Noise Init
    ]

    # Insert patterns at various locations
    for offset, pattern_data in apu_patterns:
        prg_rom[offset:offset+len(pattern_data)] = pattern_data

    # Add assembly code patterns throughout
    code_patterns = [
        (1000, b'\x4C\x00\x80' * 10),        # JMP $8000 (repeat)
        (2000, b'\x20\x00\x80' * 10),        # JSR $8000 (repeat)
        (3000, b'\x60' * 20),                 # RTS (repeat)
        (4000, b'\xA9\x01\xA9\x02' * 20),    # LDA patterns
        (5000, b'\x8D\x15\x40' * 20),        # STA patterns
    ]

    for offset, code in code_patterns:
        if offset + len(code) <= len(prg_rom):
            prg_rom[offset:offset+len(code)] = code

    # Add valid reset vectors at the end
    # Vectors are at $FFFA-$FFFF in ROM space, which is at offset 0x7FFA in the 128KB PRG-ROM
    vectors_offset = 0x20000 - 6  # Last 6 bytes of 128KB
    prg_rom[vectors_offset:vectors_offset+2] = struct.pack('<H', 0x8000)  # NMI vector
    prg_rom[vectors_offset+2:vectors_offset+4] = struct.pack('<H', 0x8000)  # RESET vector
    prg_rom[vectors_offset+4:vectors_offset+6] = struct.pack('<H', 0x8000)  # IRQ vector

    return header + bytes(prg_rom)


@pytest.fixture
def valid_rom_file(temp_dir):
    """Create a minimal valid NES ROM file.

    Returns a Path to a ROM with:
    - Valid iNES header
    - APU initialization patterns
    - Valid reset vectors
    - Good assembly code density
    """
    rom_path = temp_dir / "valid.nes"
    rom_data = _create_valid_rom_binary()
    rom_path.write_bytes(rom_data)
    return rom_path


@pytest.fixture
def invalid_header_rom(temp_dir):
    """Create a ROM with an invalid iNES header.

    Returns a Path to a ROM with:
    - Invalid magic bytes (should be 'NES\x1A')
    """
    rom_path = temp_dir / "invalid_header.nes"
    rom_data = b'INVALID_HEADER' + b'\x00' * 131072
    rom_path.write_bytes(rom_data)
    return rom_path


@pytest.fixture
def zero_filled_rom(temp_dir):
    """Create a ROM with excessive zero bytes (>70%).

    Returns a Path to a ROM with:
    - Valid iNES header
    - ~90% zero bytes in PRG-ROM
    """
    rom_path = temp_dir / "zero_filled.nes"
    header = _create_ines_header(8, 0, mapper=1)
    prg_rom = b'\x00' * (128 * 1024)
    rom_data = header + prg_rom
    rom_path.write_bytes(rom_data)
    return rom_path


@pytest.fixture
def bad_vectors_rom(temp_dir):
    """Create a ROM with invalid reset vectors.

    Returns a Path to a ROM with:
    - Valid iNES header
    - Reset vectors pointing outside $8000-$FFFF
    """
    rom_path = temp_dir / "bad_vectors.nes"
    header = _create_ines_header(8, 0, mapper=1)

    # Create PRG-ROM with bad vectors
    prg_rom = bytearray(128 * 1024)
    vectors_offset = 0x20000 - 6

    # Bad vectors (point to zero page or invalid areas)
    prg_rom[vectors_offset:vectors_offset+2] = struct.pack('<H', 0x0050)  # NMI in zero page
    prg_rom[vectors_offset+2:vectors_offset+4] = struct.pack('<H', 0x00F0)  # RESET in zero page
    prg_rom[vectors_offset+4:vectors_offset+6] = struct.pack('<H', 0x0100)  # IRQ in stack area

    rom_data = header + bytes(prg_rom)
    rom_path.write_bytes(rom_data)
    return rom_path


@pytest.fixture
def no_apu_rom(temp_dir):
    """Create a ROM with no APU initialization patterns.

    Returns a Path to a ROM with:
    - Valid iNES header
    - Valid reset vectors
    - But NO APU initialization code
    """
    rom_path = temp_dir / "no_apu.nes"
    header = _create_ines_header(8, 0, mapper=1)

    # Create PRG-ROM with valid vectors but no APU patterns
    prg_rom = bytearray(128 * 1024)

    # Only add non-APU assembly patterns
    assembly_patterns = [
        b'\x4C',  # JMP
        b'\x20',  # JSR
        b'\x60',  # RTS
    ]

    for i, pattern in enumerate(assembly_patterns):
        offset = 100 + i * 256
        prg_rom[offset:offset+len(pattern)] = pattern

    # Add valid reset vectors
    vectors_offset = 0x20000 - 6
    prg_rom[vectors_offset:vectors_offset+2] = struct.pack('<H', 0x8000)
    prg_rom[vectors_offset+2:vectors_offset+4] = struct.pack('<H', 0x8000)
    prg_rom[vectors_offset+4:vectors_offset+6] = struct.pack('<H', 0x8000)

    rom_data = header + bytes(prg_rom)
    rom_path.write_bytes(rom_data)
    return rom_path


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def mido_module():
    """Provide the mido module for tests."""
    return mido
