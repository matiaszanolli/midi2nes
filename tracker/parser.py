import mido
import json
from collections import defaultdict
from constants import FRAME_MS

def parse_midi_to_frames(midi_path):
    mid = mido.MidiFile(midi_path)
    ticks_per_beat = mid.ticks_per_beat
    current_tempos = [500000]  # List of tempo changes (default 120 BPM)

    # Dict of {track_name: [events]}
    track_events = defaultdict(list)

    for i, track in enumerate(mid.tracks):
        current_tick = 0
        current_time_ms = 0
        tempo = 500000

        track_name = f"track_{i}"
        for msg in track:
            current_tick += msg.time

            if msg.type == 'set_tempo':
                tempo = msg.tempo
                current_tempos.append(tempo)

            # Recalculate time with new tempo
            time_per_tick = tempo / ticks_per_beat / 1000.0
            current_time_ms = current_tick * time_per_tick
            frame = int(current_time_ms / FRAME_MS)

            if msg.type == 'track_name':
                track_name = msg.name.strip().replace(" ", "_")

            elif msg.type == 'note_on' or msg.type == 'note_off':
                note = msg.note
                velocity = msg.velocity if msg.type == 'note_on' else 0

                # Ignore note_on with velocity 0 (acts as note_off)
                if msg.type == 'note_on' and velocity == 0:
                    msg_type = 'note_off'
                    velocity = 0
                else:
                    msg_type = msg.type

                track_events[track_name].append({
                    "frame": frame,
                    "note": note,
                    "volume": velocity,  # volume is the expected key
                    "type": msg_type
                })

    return track_events


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python parser.py <input.mid> <output.json>")
        sys.exit(1)

    midi_path = sys.argv[1]
    output_path = sys.argv[2]

    parsed = parse_midi_to_frames(midi_path)
    with open(output_path, 'w') as f:
        json.dump(parsed, f, indent=2)

    print(f"Parsed MIDI saved to {output_path}")
