import mido
import json
from collections import defaultdict
from constants import FRAME_MS
from tracker.tempo_map import TempoMap
from tracker.pattern_detector import PatternDetector
from tracker.loop_manager import LoopManager

def parse_midi_to_frames(midi_path):
    mid = mido.MidiFile(midi_path)
    tempo_map = TempoMap(ticks_per_beat=mid.ticks_per_beat)
    track_events = defaultdict(list)
    track_metadata = defaultdict(dict)

    # First pass: collect all tempo changes
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                tempo_map.add_tempo_change(current_tick, msg.tempo)

    # Second pass: process notes with accurate timing
    for i, track in enumerate(mid.tracks):
        current_tick = 0
        track_name = f"track_{i}"

        for msg in track:
            current_tick += msg.time
            current_time_ms = tempo_map.calculate_time_ms(0, current_tick)
            frame = int(current_time_ms / FRAME_MS)

            if msg.type == 'track_name':
                track_name = msg.name.strip().replace(" ", "_")
            elif msg.type in ['note_on', 'note_off']:
                note = msg.note
                velocity = msg.velocity if msg.type == 'note_on' else 0

                # Handle note_on with velocity 0
                msg_type = 'note_off' if (msg.type == 'note_on' and velocity == 0) else msg.type

                track_events[track_name].append({
                    "frame": frame,
                    "note": note,
                    "volume": velocity,
                    "type": msg_type,
                    "tempo": tempo_map.get_tempo_at_tick(current_tick)
                })

    # Third pass: detect patterns and loops for each track
    pattern_detector = PatternDetector()
    loop_manager = LoopManager()

    for track_name, events in track_events.items():
        # Filter only note_on events for pattern detection
        note_on_events = [
            event for event in events 
            if event['type'] == 'note_on' and event['volume'] > 0
        ]

        # Detect patterns
        patterns = pattern_detector.detect_patterns(note_on_events)
        
        # Detect loops based on patterns
        loops = loop_manager.detect_loops(note_on_events, patterns)
        
        # Generate jump table
        jump_table = loop_manager.generate_jump_table(loops)
        
        # Store metadata for this track
        track_metadata[track_name] = {
            "patterns": patterns,
            "loops": loops,
            "jump_table": jump_table
        }

    # Return both events and metadata
    return {
        "events": dict(track_events),
        "metadata": dict(track_metadata)
    }

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
