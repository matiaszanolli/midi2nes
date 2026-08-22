# New file: exporter/exporter_famistudio.py

from exporter.base_exporter import BaseExporter, atomic_write_text

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
        # Find maximum frame across all channels. dpcm_sample_map's keys are
        # dense sample ids, not frame numbers (#313/EXP-11) -- exclude it.
        all_frames = []
        for channel_name, channel_data in frames_data.items():
            if channel_name == 'dpcm_sample_map':
                continue
            all_frames.extend(int(f) for f in channel_data.keys())
        max_frame = max(all_frames) if all_frames else 0
    
    for channel, events in frames_data.items():
        if channel == 'dpcm_sample_map':
            # dense_id -> catalog_id side table (#200/D-14), not a playable
            # channel; iterating it like one produces a malformed
            # "dpcm_sample_map_N" pattern key that crashes the split('_')
            # below (#313/EXP-11).
            continue
        current_pattern = []
        # Per-channel pattern index (#440/EXP-2026-08-21-2): PATTERN keys and
        # the SEQUENCE below must agree on the same numbering. Indexing by
        # len(patterns) counted every channel's patterns emitted so far, not
        # just this channel's -- only the first channel processed got
        # correctly-numbered keys by coincidence (nothing had been emitted
        # yet); every later channel's full-pattern keys landed on indices
        # already claimed by earlier channels, while SEQUENCE always
        # references this channel's own 0-based range, so channel 2+'s
        # SEQUENCE pointed at undefined (or wrong) PATTERN names.
        channel_pattern_count = 0
        for frame in range(max_frame + 1):
            # Accept int OR str frame keys, mirroring exporter_ca65.py's dual-
            # key tolerance (`channel_frames.get(str(frame_idx),
            # channel_frames.get(frame_idx))`): frames built in-memory carry
            # int keys, JSON round-trips produce str keys. Checking only
            # `str(frame) in events` silently exported nothing but rest rows
            # for an int-keyed frames dict (#441/EXP-2026-08-21-3).
            event = events.get(str(frame), events.get(frame))
            if event is not None:
                if channel in ['pulse1', 'pulse2', 'triangle']:
                    # .get() with the same defaults exporter_ca65.py uses
                    # (#370/EXP-2026-07-19-2) -- a frame dict missing 'note'
                    # or 'volume' used to raise KeyError here while the CA65
                    # path tolerated it, so the two exporters disagreed on
                    # what counts as a valid frames input.
                    note = midi_note_to_famistudio(event.get('note', 0))
                    volume = min(15, event.get('volume', 0))
                    current_pattern.append(f"{note} {volume}")
                elif channel == 'noise':
                    volume = min(15, event.get('volume', 0))
                    current_pattern.append(f"F#4 {volume}")
                elif channel == 'dpcm':
                    # The frames dict the rest of the pipeline produces encodes
                    # the DPCM trigger as `note = sample_id + 1`, not a raw
                    # `sample_id` key, so reading event['sample_id'] raised
                    # KeyError on real frames (#82). Prefer an explicit sample_id
                    # if present, else recover it from note.
                    sample_id = event.get('sample_id')
                    if sample_id is None:
                        sample_id = max(0, event.get('note', 1) - 1)
                    current_pattern.append(f"C-4 {sample_id}")
            else:
                current_pattern.append("... ..")
                
            if len(current_pattern) == pattern_length:
                pattern_key = f"{channel}_{channel_pattern_count}"
                patterns[pattern_key] = current_pattern
                channel_pattern_count += 1
                current_pattern = []

        # Add any remaining pattern data
        if current_pattern:
            pattern_key = f"{channel}_{channel_pattern_count}"
            patterns[pattern_key] = current_pattern
            channel_pattern_count += 1
    
    # Write patterns
    lines.append("PATTERNS")
    for pattern_key, pattern_data in patterns.items():
        channel, index = pattern_key.split('_')
        lines.extend([
            f"  PATTERN \"{channel}_{index}\"",
            f"    CHANNEL {channel.upper()}",
            # The remainder pattern (song length not an even multiple of 64
            # frames) is shorter than a full pattern -- declaring it LENGTH
            # 64 regardless of its actual row count was cosmetically wrong
            # (#440/EXP-2026-08-21-2).
            f"    LENGTH {len(pattern_data)}"
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
    # Clamp to FamiStudio's valid 0-7 octave range; low notes gave octave -1 (#82).
    octave = max(0, min(7, (note // 12) - 1))
    note_name = NOTE_NAMES[note % 12]
    return f"{note_name}{octave}"

class FamiStudioExporter(BaseExporter):
    """FamiStudio Text Format Exporter"""
    
    def __init__(self):
        super().__init__()
    
    def generate_famistudio_txt(self, frames_data, project_name="MIDI2NES", author="", copyright=""):
        """Generate FamiStudio text format export"""
        return generate_famistudio_txt(frames_data, project_name, author, copyright)
    
    def export(self, frames_data, output_path, project_name="MIDI2NES", author="", copyright=""):
        """Export frame data to FamiStudio text format"""
        output = generate_famistudio_txt(frames_data, project_name, author, copyright)
        atomic_write_text(output_path, output)  # #385/SAFE-2026-07-19-3

def export_famistudio(frames_data, output_path, project_name="MIDI2NES", author="", copyright=""):
    """Export frame data to FamiStudio text format"""
    output = generate_famistudio_txt(frames_data, project_name, author, copyright)
    atomic_write_text(output_path, output)  # #385/SAFE-2026-07-19-3
