import json
import sys
from exporter.pattern_exporter import PatternExporter

PATTERN_LEN = 64

NOTE_TABLE = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']

def midi_note_to_ft(note):
    octave = (note // 12) - 1
    note_name = NOTE_TABLE[note % 12]
    return f"{note_name}{octave}"

# exporter.py (modified version)

def generate_famitracker_txt_with_patterns(frames_data, compressed_patterns, pattern_refs, rows_per_pattern=64):
    pattern_exporter = PatternExporter(compressed_patterns, pattern_refs)
    
    # Get the maximum frame number
    max_frame = pattern_exporter.get_max_frame()
    total_patterns = (max_frame // rows_per_pattern) + 1
    
    lines = []
    lines.append("# FamiTracker text export (Pattern Compressed)")
    lines.append("# Song title: MIDI2NES")
    lines.append("COLUMNS 1 1 1 1 1")
    lines.append(f"ROWS {rows_per_pattern}")
    
    # Write pattern data
    for pattern_index in range(total_patterns):
        lines.append(f"PATTERN {pattern_index:02X}")
        
        for row in range(rows_per_pattern):
            frame = pattern_index * rows_per_pattern + row
            frame_data = pattern_exporter.get_frame_data(frame)
            
            if frame_data:
                note_str = midi_note_to_ft(frame_data['note'])
                vol = format(frame_data['volume'], 'X').rjust(2, '0')
                lines.append(f"{row:02X} | {note_str} 00 {vol}")
            else:
                lines.append(f"{row:02X} | ... .. ..")
                
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python exporter.py <nes_frames.json> <output.txt>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        frames = json.load(f)

    out = generate_famitracker_txt_with_patterns(frames)

    with open(sys.argv[2], 'w') as f:
        f.write(out)

    print(f"Exported to {sys.argv[2]}")
