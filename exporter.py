import json
import sys
from collections import defaultdict

PATTERN_LEN = 64

NOTE_TABLE = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']

def midi_note_to_ft(note):
    octave = (note // 12) - 1
    note_name = NOTE_TABLE[note % 12]
    return f"{note_name}{octave}"

def generate_famitracker_txt(nes_frames, rows_per_pattern=64):
    # Find the max frame number to determine total patterns
    max_frame = max(
        int(frame)
        for channel_data in nes_frames.values()
        for frame in channel_data
    )
    total_patterns = (max_frame // rows_per_pattern) + 1

    lines = []
    lines.append("# FamiTracker text export")
    lines.append("# Song title: MIDI2NES")
    lines.append("COLUMNS 1 1 1 1 1")
    lines.append(f"ROWS {rows_per_pattern}")
    lines.append("ORDER " + " ".join(f"{i:02X}" for i in range(total_patterns)))
    channel_order = ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']

    # Write ORDER list
    order_str = "ORDER " + " ".join(f"{i:02X}" for i in range(total_patterns))
    lines.append(order_str)

    # Generate patterns
    for pattern_index in range(total_patterns):
        lines.append(f"PATTERN {pattern_index:02X}")

        pattern_data = {ch: ['... .. ..'] * rows_per_pattern for ch in channel_order}

        for ch in channel_order:
            if ch not in nes_frames:
                continue

            for frame_str, data in nes_frames[ch].items():
                frame = int(frame_str)
                if (frame // rows_per_pattern) != pattern_index:
                    continue
                row = frame % rows_per_pattern

                if ch in ['pulse1', 'pulse2', 'triangle']:
                    if data['volume'] == 0:
                        note_str = '... .. ..'
                    else:
                        note_name = midi_note_to_ft(data['note'])
                        instr = '00' if 'pulse' in ch else '01'
                        vol = format(data['volume'], 'X').rjust(2, '0')
                        note_str = f"{note_name} {instr} {vol}"

                elif ch == 'noise':
                    vol = format(data['volume'], 'X').rjust(2, '0')
                    note_str = f"F#2 02 {vol}" if data['volume'] > 0 else "... .. .."

                elif ch == 'dpcm':
                    sample_id = format(data['sample_id'], 'X').rjust(2, '0')
                    note_str = f"C-3 03 {sample_id}"

                pattern_data[ch][row] = note_str

        for row in range(rows_per_pattern):
            line = f"{row:02X} |"
            for ch in channel_order:
                line += f" {pattern_data[ch][row]}"
            lines.append(line)

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python exporter.py <nes_frames.json> <output.txt>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        frames = json.load(f)

    out = generate_famitracker_txt(frames)

    with open(sys.argv[2], 'w') as f:
        f.write(out)

    print(f"Exported to {sys.argv[2]}")
