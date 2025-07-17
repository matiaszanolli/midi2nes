import mido
import json
from collections import defaultdict
from constants import FRAME_MS, FRAME_RATE_HZ
from tracker.tempo_map import (EnhancedTempoMap, TempoValidationConfig, TempoOptimizationStrategy,
                               TempoChangeType, TempoValidationError)
from tracker.pattern_detector import EnhancedPatternDetector
from tracker.loop_manager import EnhancedLoopManager

def parse_midi_to_frames(midi_path):
    mid = mido.MidiFile(midi_path)
    # Initialize with validation and optimization
    config = TempoValidationConfig(
        min_tempo_bpm=40.0,
        max_tempo_bpm=250.0,
        min_duration_frames=2,
        max_duration_frames=FRAME_RATE_HZ * 30  # 30 seconds
    )
    tempo_map = EnhancedTempoMap(
        initial_tempo=500000,  # 120 BPM
        validation_config=config,
        optimization_strategy=TempoOptimizationStrategy.FRAME_ALIGNED
    )
    track_events = defaultdict(list)
    track_metadata = defaultdict(dict)

    # First pass: collect all tempo changes
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                try:
                    tempo_map.add_tempo_change(
                        current_tick,  # tick
                        msg.tempo,  # 150 BPM
                        TempoChangeType.LINEAR,
                        duration_ticks=960
                    )
                except TempoValidationError as e:
                    print(f"Invalid tempo change: {e}")
        tempo_map.optimize_tempo_changes()

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
    pattern_detector = EnhancedPatternDetector()
    loop_manager = EnhancedLoopManager()

    for track_name, events in track_events.items():
        # Filter only note_on events for pattern detection
        note_on_events = [
            event for event in events 
            if event['type'] == 'note_on' and event['volume'] > 0
        ]

        # Detect patterns
        pattern_data = pattern_detector.detect_patterns(note_on_events)
        
        # Detect loops based on compressed patterns
        loops = loop_manager.detect_loops(
            note_on_events, pattern_data['patterns']
        )
        
        # Generate jump table
        jump_table = loop_manager.generate_jump_table(loops)
        
        # Store metadata for this track
        track_metadata[track_name] = {
            "patterns": pattern_data['patterns'],
            "pattern_refs": pattern_data['references'],
            "compression_stats": pattern_data['stats'],
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
