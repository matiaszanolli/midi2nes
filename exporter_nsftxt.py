import json

def generate_nsftxt(frames_data, rows_per_pattern=64, title="MIDI2NES", author="Matías", copyright="Free 8-bit joy"):
    channel_order = ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']

    # Determine total patterns
    max_frame = max(
        int(f) for ch in frames_data.values() for f in ch
    )
    total_patterns = (max_frame // rows_per_pattern) + 1

    lines = []
    lines.append("# FamiTracker text export")
    lines.append("# Exported by midi2nes")
    lines.append("")

    # Header
    lines.append("HEADER")
    lines.append(f"NAME {title}")
    lines.append(f"AUTHOR {author}")
    lines.append(f"COPYRIGHT {copyright}")
    lines.append("MACHINE NTSC")
    lines.append("FRAMERATE 60")
    lines.append("EXPANSION NONE")
    lines.append("SONGS 1")
    lines.append("START 0")
    lines.append("")

    # Song 0 metadata
    lines.append("# SONG 0")
    lines.append(f"TITLE {title}")
    lines.append(f"ARTIST {author}")
    lines.append(f"COPYRIGHT (C) {copyright}")
    lines.append("COMMENT Exported by midi2nes")
    lines.append(f"ROWS {rows_per_pattern}")
    lines.append("COLUMNS PULSE1 PULSE2 TRIANGLE NOISE DPCM")
    lines.append("ORDER " + " ".join(f"{i:02X}" for i in range(total_patterns)))
    lines.append("")

    # Instruments
    lines.append("INSTRUMENTS")
    for i in range(4):
        lines.append(f"INST2A03 {i:02X}")
        lines.append("ENVELOPE VOLUME 15 15 15 15 15 15 15 0")
        lines.append("ENVELOPE ARPEGGIO 0")
        lines.append("ENVELOPE PITCH 0")
        lines.append("ENVELOPE HI-PITCH 0")
        if i < 2:
            lines.append("DUTY 2")
        lines.append("INST2A03_END")
    lines.append("")

    # Patterns
    for pattern_index in range(total_patterns):
        lines.append(f"PATTERN {pattern_index:02X}")
        pattern_data = {ch: ['... .. ..'] * rows_per_pattern for ch in channel_order}

        for ch in channel_order:
            if ch not in frames_data:
                continue
            for frame_str, data in frames_data[ch].items():
                frame = int(frame_str)
                if frame // rows_per_pattern != pattern_index:
                    continue
                row = frame % rows_per_pattern

                if ch in ['pulse1', 'pulse2', 'triangle']:
                    if data['volume'] == 0:
                        note_str = '... .. ..'
                    else:
                        note_name = midi_note_to_ft(data['note'])
                        instr = '00' if ch == 'pulse1' else '01' if ch == 'pulse2' else '02'
                        vol = format(data['volume'], 'X').rjust(2, '0')
                        note_str = f"{note_name} {instr} {vol}"

                elif ch == 'noise':
                    vol = format(data['volume'], 'X').rjust(2, '0')
                    note_str = f"F#2 03 {vol}" if data['volume'] > 0 else "... .. .."

                elif ch == 'dpcm':
                    sample_id = format(data['sample_id'], 'X').rjust(2, '0')
                    note_str = f"C-3 03 {sample_id}"

                pattern_data[ch][row] = note_str

        for row in range(rows_per_pattern):
            line = f"{row:02X} |"
            for ch in channel_order:
                line += f" {pattern_data[ch][row]}"
            lines.append(line)
        lines.append("")

    return "\n".join(lines)

def midi_note_to_ft(note):
    NOTE_TABLE = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']
    octave = (note // 12) - 1
    name = NOTE_TABLE[note % 12]
    return f"{name}{octave}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python exporter_nsftxt.py <frames.json> <output.txt>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        frames = json.load(f)

    output = generate_nsftxt(frames)
    with open(sys.argv[2], 'w') as f:
        f.write(output)
        
    print(f"Exported FamiTracker NSF-compatible .txt to {sys.argv[2]}")
