import mido
import json
from collections import defaultdict
from constants import FRAME_MS, FRAME_RATE_HZ
from tracker.tempo_map import (EnhancedTempoMap, TempoValidationConfig, 
                               TempoChangeType, TempoValidationError)

def parse_midi_to_frames_optimized(midi_path):
    """Optimized MIDI parser that only does basic frame conversion"""
    mid = mido.MidiFile(midi_path)
    
    # Simple tempo map without expensive validation/optimization 
    config = TempoValidationConfig(
        min_tempo_bpm=40.0,
        max_tempo_bpm=250.0,
        min_duration_frames=2,
        max_duration_frames=FRAME_RATE_HZ * 30
    )
    tempo_map = EnhancedTempoMap(
        initial_tempo=500000,  # 120 BPM
        validation_config=config,
        optimization_strategy=None
    )
    track_events = defaultdict(list)

    # First pass: collect tempo changes (fast)
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                try:
                    tempo_map.add_tempo_change(
                        current_tick,
                        msg.tempo,
                        TempoChangeType.IMMEDIATE
                    )
                except TempoValidationError:
                    pass  # Skip invalid tempo changes silently

    # Second pass: process notes (fast)
    for i, track in enumerate(mid.tracks):
        current_tick = 0
        track_name = f"track_{i}"

        for msg in track:
            current_tick += msg.time
            frame = tempo_map.get_frame_for_tick(current_tick)

            if msg.type == 'track_name':
                track_name = msg.name.strip().replace(" ", "_")
            elif msg.type in ['note_on', 'note_off']:
                note = msg.note
                velocity = msg.velocity if msg.type == 'note_on' else 0
                msg_type = 'note_off' if (msg.type == 'note_on' and velocity == 0) else msg.type

                track_events[track_name].append({
                    "frame": frame,
                    "note": note,
                    "volume": velocity,
                    "type": msg_type,
                    "tempo": tempo_map.get_tempo_at_tick(current_tick)
                })

    # Return only events - no expensive pattern detection!
    return {
        "events": dict(track_events),
        "metadata": {}  # Empty metadata to avoid expensive operations
    }
