# New file: exporter/exporter_famistudio.py

import json
from pathlib import Path

def generate_famistudio_txt(frames_data, project_name="MIDI2NES", author="", copyright=""):
    """
    Generate FamiStudio text format export
    
    Args:
        frames_data: Dictionary of frame data per channel
        project_name: Name of the project
        author: Author name
        copyright: Copyright information
        
    Returns:
        String containing the FamiStudio text format data
    """
    lines = []
    
    # Header
    lines.extend([
        "# FamiStudio Text Export",
        f"# Project: {project_name}",
        f"# Author: {author}",
        f"# Copyright: {copyright}",
        ""
    ])
    
    # Project settings
    lines.extend([
        "PROJECT",
        f"  NAME {project_name}",
        f"  AUTHOR {author}",
        f"  COPYRIGHT {copyright}",
        "  MACHINE NTSC",
        "  CHANNELS 5",
        "  SPEED 1",
        "END",
        ""
    ])
    
    # Instruments
    lines.extend([
        "INSTRUMENTS",
        "  INSTRUMENT \"Pulse 1\"",
        "    TYPE Pulse",
        "    VOLUME 15",
        "    DUTY 2",
        "  END",
        "",
        "  INSTRUMENT \"Pulse 2\"",
        "    TYPE Pulse",
        "    VOLUME 15",
        "    DUTY 2",
        "  END",
        "",
        "  INSTRUMENT \"Triangle\"",
        "    TYPE Triangle",
        "    VOLUME 15",
        "  END",
        "",
        "  INSTRUMENT \"Noise\"",
        "    TYPE Noise",
        "    VOLUME 15",
        "  END",
        "",
        "  INSTRUMENT \"DPCM\"",
        "    TYPE DPCM",
        "    VOLUME 15",
        "  END",
        "END",
        ""
    ])
    
    # Calculate patterns
    patterns = {}
    pattern_length = 64  # Standard pattern length
    
    # Handle empty frames_data case
    if not frames_data:
        max_frame = 0
    else:
        # Find maximum frame across all channels
        all_frames = []
        for channel_data in frames_data.values():
            all_frames.extend(int(f) for f in channel_data.keys())
        max_frame = max(all_frames) if all_frames else 0
    
    for channel, events in frames_data.items():
        current_pattern = []
        for frame in range(max_frame + 1):
            if str(frame) in events:
                event = events[str(frame)]
                if channel in ['pulse1', 'pulse2', 'triangle']:
                    note = midi_note_to_famistudio(event['note'])
                    volume = min(15, event['volume'])
                    current_pattern.append(f"{note} {volume}")
                elif channel == 'noise':
                    volume = min(15, event['volume'])
                    current_pattern.append(f"F#4 {volume}")
                elif channel == 'dpcm':
                    sample_id = event['sample_id']
                    current_pattern.append(f"C-4 {sample_id}")
            else:
                current_pattern.append("... ..")
                
            if len(current_pattern) == pattern_length:
                pattern_key = f"{channel}_{len(patterns)}"
                patterns[pattern_key] = current_pattern
                current_pattern = []
        
        # Add any remaining pattern data
        if current_pattern:
            pattern_key = f"{channel}_{len([k for k in patterns.keys() if k.startswith(channel)])}"
            patterns[pattern_key] = current_pattern
    
    # Write patterns
    lines.append("PATTERNS")
    for pattern_key, pattern_data in patterns.items():
        channel, index = pattern_key.split('_')
        lines.extend([
            f"  PATTERN \"{channel}_{index}\"",
            f"    CHANNEL {channel.upper()}",
            "    LENGTH 64"
        ])
        for i, note in enumerate(pattern_data):
            lines.append(f"    {i:02X} | {note}")
        lines.extend([
            "  END",
            ""
        ])
    lines.append("END")
    
    # Write song
    lines.extend([
        "SONG \"Main Song\"",
        "  SPEED 6",
        "  TEMPO 150"
    ])
    
    # Add pattern order for each channel
    for channel in ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']:
        pattern_count = sum(1 for k in patterns.keys() if k.startswith(channel))
        if pattern_count > 0:
            lines.append(f"  CHANNEL {channel.upper()}")
            lines.append("    SEQUENCE " + " ".join(f"\"{channel}_{i}\"" for i in range(pattern_count)))
            lines.append("  END")
    
    lines.extend([
        "END",
        ""
    ])
    
    return "\n".join(lines)

def midi_note_to_famistudio(note):
    """Convert MIDI note to FamiStudio note format"""
    NOTE_NAMES = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']
    octave = (note // 12) - 1
    note_name = NOTE_NAMES[note % 12]
    return f"{note_name}{octave}"

def export_famistudio(frames_data, output_path, project_name="MIDI2NES", author="", copyright=""):
    """Export frame data to FamiStudio text format"""
    output = generate_famistudio_txt(frames_data, project_name, author, copyright)
    Path(output_path).write_text(output)
