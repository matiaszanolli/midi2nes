import mido
import json
from collections import defaultdict
from constants import FRAME_MS, FRAME_RATE_HZ
from tracker.tempo_map import (EnhancedTempoMap, TempoValidationConfig, TempoOptimizationStrategy,
                               TempoChangeType, TempoValidationError)

def parse_midi_to_frames(midi_path):
    """
    Fast MIDI parser that only does basic MIDI-to-frames conversion.
    Pattern detection, loop detection, and other expensive analysis 
    is moved to separate pipeline steps.
    """
    mid = mido.MidiFile(midi_path)
    
    # Initialize tempo map with minimal validation for performance
    config = TempoValidationConfig(
        min_tempo_bpm=40.0,
        max_tempo_bpm=250.0,
        min_duration_frames=2,
        max_duration_frames=FRAME_RATE_HZ * 300  # Allow up to 5 minutes
    )
    tempo_map = EnhancedTempoMap(
        initial_tempo=500000,  # 120 BPM
        validation_config=config,
        optimization_strategy=None  # Disable expensive optimization
    )
    
    track_events = defaultdict(list)

    # First pass: collect tempo changes efficiently
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                try:
                    # Use IMMEDIATE tempo changes for speed
                    tempo_map.add_tempo_change(
                        current_tick,
                        msg.tempo,
                        TempoChangeType.IMMEDIATE
                    )
                except TempoValidationError:
                    # Skip invalid tempo changes silently for performance
                    continue

    # Second pass: process notes efficiently
    for i, track in enumerate(mid.tracks):
        current_tick = 0
        track_name = f"track_{i}"

        for msg in track:
            current_tick += msg.time
            
            if msg.type == 'track_name':
                track_name = msg.name.strip().replace(" ", "_")
            elif msg.type in ['note_on', 'note_off']:
                try:
                    # Fast frame calculation
                    frame = tempo_map.get_frame_for_tick(current_tick)
                    note = msg.note
                    velocity = msg.velocity if msg.type == 'note_on' else 0

                    # Handle note_on with velocity 0 as note_off
                    msg_type = 'note_off' if (msg.type == 'note_on' and velocity == 0) else msg.type

                    track_events[track_name].append({
                        "frame": frame,
                        "note": note,
                        "volume": velocity,
                        "type": msg_type,
                        "tempo": tempo_map.get_tempo_at_tick(current_tick)
                    })
                except Exception:
                    # Skip problematic events to avoid crashes
                    continue

    # Return ONLY events - no expensive pattern/loop analysis
    # Pattern detection should be done in a separate step if needed
    return {
        "events": dict(track_events),
        "metadata": {}  # Empty metadata - analysis moved to separate steps
    }


def parse_midi_to_frames_with_analysis(midi_path):
    """
    Full parser that includes pattern and loop detection.
    This should only be used when analysis is specifically needed.
    """
    # First do fast parsing
    result = parse_midi_to_frames(midi_path)
    
    # Then add expensive analysis if needed
    from tracker.pattern_detector import EnhancedPatternDetector
    from tracker.loop_manager import EnhancedLoopManager
    from tracker.tempo_map import EnhancedTempoMap
    
    # Create tempo map again (could be optimized with caching)
    config = TempoValidationConfig(
        min_tempo_bpm=40.0,
        max_tempo_bpm=250.0,
        min_duration_frames=2,
        max_duration_frames=FRAME_RATE_HZ * 300
    )
    tempo_map = EnhancedTempoMap(
        initial_tempo=500000,
        validation_config=config,
        optimization_strategy=None
    )
    
    # Rebuild tempo map (this could be cached from first pass)
    mid = mido.MidiFile(midi_path)
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                try:
                    tempo_map.add_tempo_change(current_tick, msg.tempo, TempoChangeType.IMMEDIATE)
                except TempoValidationError:
                    continue
    
    # Now do expensive analysis
    pattern_detector = EnhancedPatternDetector(tempo_map)
    loop_manager = EnhancedLoopManager(tempo_map)
    
    track_metadata = defaultdict(dict)
    
    for track_name, events in result['events'].items():
        # Filter only note_on events for pattern detection
        note_on_events = [
            event for event in events 
            if event['type'] == 'note_on' and event['volume'] > 0
        ]

        if note_on_events:  # Only analyze tracks with actual notes
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
    
    # Return events with metadata
    return {
        "events": result['events'],
        "metadata": dict(track_metadata)
    }


if __name__ == "__main__":
    import sys
    import time
    
    if len(sys.argv) < 3:
        print("Usage: python parser_fast.py <input.mid> <output.json> [--with-analysis]")
        sys.exit(1)

    midi_path = sys.argv[1]
    output_path = sys.argv[2]
    with_analysis = '--with-analysis' in sys.argv
    
    print(f"Parsing {midi_path} ({'with' if with_analysis else 'without'} analysis)...")
    
    start_time = time.time()
    
    if with_analysis:
        parsed = parse_midi_to_frames_with_analysis(midi_path)
        print("Used full parser with pattern/loop analysis")
    else:
        parsed = parse_midi_to_frames(midi_path)
        print("Used fast parser without expensive analysis")
    
    end_time = time.time()
    
    with open(output_path, 'w') as f:
        json.dump(parsed, f, indent=2)
    
    events_count = sum(len(events) for events in parsed['events'].values())
    tracks_count = len(parsed['events'])
    
    print(f"Parsing completed in {end_time - start_time:.3f} seconds")
    print(f"Results: {tracks_count} tracks, {events_count:,} events")
    print(f"Parsed MIDI saved to {output_path}")
