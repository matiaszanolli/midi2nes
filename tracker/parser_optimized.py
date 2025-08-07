import mido
import json
import time
import sys
import os
from collections import defaultdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from constants import FRAME_MS, FRAME_RATE_HZ
from tracker.tempo_map import (EnhancedTempoMap, TempoValidationConfig, TempoOptimizationStrategy,
                               TempoChangeType, TempoValidationError)
from tracker.pattern_detector import EnhancedPatternDetector
from tracker.loop_manager import EnhancedLoopManager

def parse_midi_to_frames_optimized(midi_path, enable_pattern_detection=True, max_events_per_track=5000, verbose=False):
    """
    Optimized version of MIDI parsing with performance improvements:
    - Optional pattern detection (biggest bottleneck)
    - Event limit per track to prevent exponential slowdown
    - Batch tempo calculations
    - Progress reporting
    - Early termination options
    """
    start_time = time.time()
    
    if verbose:
        print(f"Loading MIDI file: {midi_path}")
    
    mid = mido.MidiFile(midi_path)
    
    # Initialize with validation but NO optimization
    config = TempoValidationConfig(
        min_tempo_bpm=40.0,
        max_tempo_bpm=250.0,
        min_duration_frames=2,
        max_duration_frames=FRAME_RATE_HZ * 30  # 30 seconds
    )
    tempo_map = EnhancedTempoMap(
        initial_tempo=500000,  # 120 BPM
        validation_config=config,
        optimization_strategy=None  # Disable optimization
    )
    track_events = defaultdict(list)
    track_metadata = defaultdict(dict)

    # First pass: collect all tempo changes (fast)
    tempo_changes = 0
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
                    tempo_changes += 1
                except TempoValidationError as e:
                    if verbose:
                        print(f"Invalid tempo change: {e}")

    if verbose:
        print(f"Processed {tempo_changes} tempo changes in {time.time() - start_time:.2f}s")

    # Second pass: process notes with optimized timing calculations
    total_events = 0
    skipped_tracks = 0
    
    for i, track in enumerate(mid.tracks):
        track_start_time = time.time()
        current_tick = 0
        track_name = f"track_{i}"
        track_note_events = []

        # Pre-scan track to count events and get name
        event_count = sum(1 for msg in track if msg.type in ['note_on', 'note_off'])
        
        # Skip tracks with too many events to prevent exponential slowdown
        if event_count > max_events_per_track:
            if verbose:
                print(f"Skipping track {track_name} - too many events ({event_count} > {max_events_per_track})")
            skipped_tracks += 1
            continue
            
        if verbose and event_count > 100:
            print(f"Processing track {track_name} ({event_count} events)...")

        # Batch process events for better performance
        events_batch = []
        
        for msg in track:
            current_tick += msg.time
            
            if msg.type == 'track_name':
                track_name = msg.name.strip().replace(" ", "_")
            elif msg.type in ['note_on', 'note_off']:
                events_batch.append((current_tick, msg))
                
                # Process in batches of 1000 for better memory usage
                if len(events_batch) >= 1000:
                    track_note_events.extend(_process_event_batch(events_batch, tempo_map))
                    events_batch = []

        # Process remaining events
        if events_batch:
            track_note_events.extend(_process_event_batch(events_batch, tempo_map))
            
        track_events[track_name] = track_note_events
        total_events += len(track_note_events)
        
        if verbose and len(track_note_events) > 100:
            print(f"Track {track_name}: {len(track_note_events)} events in {time.time() - track_start_time:.2f}s")

    if verbose:
        print(f"Processed {total_events} events from {len(track_events)} tracks in {time.time() - start_time:.2f}s")
        if skipped_tracks > 0:
            print(f"Skipped {skipped_tracks} tracks due to size limits")

    # Third pass: pattern detection (optional, this is the major bottleneck)
    if enable_pattern_detection:
        pattern_start_time = time.time()
        if verbose:
            print("Starting pattern detection...")
        
        # Use optimized pattern detector settings
        pattern_detector = EnhancedPatternDetector(tempo_map, min_pattern_length=4, max_pattern_length=16)
        loop_manager = EnhancedLoopManager(tempo_map)

        for track_name, events in track_events.items():
            # Filter only note_on events for pattern detection
            note_on_events = [
                event for event in events 
                if event['type'] == 'note_on' and event['volume'] > 0
            ]
            
            # Skip pattern detection for tracks with too few or too many events
            if len(note_on_events) < 10:
                track_metadata[track_name] = {
                    "patterns": {},
                    "pattern_refs": {},
                    "compression_stats": {"compression_ratio": 0, "original_size": 0, "compressed_size": 0, "unique_patterns": 0},
                    "loops": {},
                    "jump_table": {}
                }
                continue
                
            if len(note_on_events) > 2000:
                if verbose:
                    print(f"Skipping pattern detection for {track_name} - too many note events ({len(note_on_events)})")
                track_metadata[track_name] = {
                    "patterns": {},
                    "pattern_refs": {},
                    "compression_stats": {"compression_ratio": 0, "original_size": 0, "compressed_size": 0, "unique_patterns": 0},
                    "loops": {},
                    "jump_table": {}
                }
                continue

            track_pattern_start = time.time()
            
            # Detect patterns with timeout protection
            try:
                pattern_data = _detect_patterns_with_timeout(pattern_detector, note_on_events, timeout_seconds=30)
                
                # Detect loops based on compressed patterns
                loops = loop_manager.detect_loops(
                    note_on_events, pattern_data['patterns']
                )
                
                # Generate jump table
                jump_table = loop_manager.generate_jump_table(loops)
                
                track_metadata[track_name] = {
                    "patterns": pattern_data['patterns'],
                    "pattern_refs": pattern_data['references'],
                    "compression_stats": pattern_data['stats'],
                    "loops": loops,
                    "jump_table": jump_table
                }
                
                if verbose:
                    patterns_found = len(pattern_data['patterns'])
                    compression = pattern_data['stats'].get('compression_ratio', 0)
                    print(f"Track {track_name}: {patterns_found} patterns, {compression:.1f}% compression in {time.time() - track_pattern_start:.2f}s")
                    
            except TimeoutError:
                if verbose:
                    print(f"Pattern detection timeout for {track_name}")
                track_metadata[track_name] = {
                    "patterns": {},
                    "pattern_refs": {},
                    "compression_stats": {"compression_ratio": 0, "original_size": 0, "compressed_size": 0, "unique_patterns": 0},
                    "loops": {},
                    "jump_table": {}
                }
        
        if verbose:
            print(f"Pattern detection completed in {time.time() - pattern_start_time:.2f}s")
    else:
        # Skip pattern detection entirely
        for track_name in track_events.keys():
            track_metadata[track_name] = {
                "patterns": {},
                "pattern_refs": {},
                "compression_stats": {"compression_ratio": 0, "original_size": 0, "compressed_size": 0, "unique_patterns": 0},
                "loops": {},
                "jump_table": {}
            }

    total_time = time.time() - start_time
    if verbose:
        print(f"Total parsing time: {total_time:.2f}s")

    # Return both events and metadata
    result = {
        "events": dict(track_events),
        "metadata": dict(track_metadata),
        "performance_stats": {
            "total_time_seconds": total_time,
            "total_events": total_events,
            "tracks_processed": len(track_events),
            "tracks_skipped": skipped_tracks,
            "pattern_detection_enabled": enable_pattern_detection
        }
    }
    
    return result


def _process_event_batch(events_batch, tempo_map):
    """Process a batch of events efficiently"""
    processed_events = []
    
    for current_tick, msg in events_batch:
        # Use tempo_map's get_frame_for_tick for consistent frame calculation
        frame = tempo_map.get_frame_for_tick(current_tick)
        
        note = msg.note
        velocity = msg.velocity if msg.type == 'note_on' else 0

        # Handle note_on with velocity 0
        msg_type = 'note_off' if (msg.type == 'note_on' and velocity == 0) else msg.type

        processed_events.append({
            "frame": frame,
            "note": note,
            "volume": velocity,
            "type": msg_type,
            "tempo": tempo_map.get_tempo_at_tick(current_tick)
        })
    
    return processed_events


def _detect_patterns_with_timeout(pattern_detector, events, timeout_seconds=30):
    """Detect patterns with timeout to prevent hanging"""
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Pattern detection timeout")
    
    # Set timeout
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)
    
    try:
        result = pattern_detector.detect_patterns(events)
        signal.alarm(0)  # Cancel timeout
        return result
    except TimeoutError:
        signal.alarm(0)  # Cancel timeout
        raise
    finally:
        signal.signal(signal.SIGALRM, old_handler)


def parse_midi_to_frames_fast(midi_path, verbose=False):
    """
    Ultra-fast version that skips pattern detection entirely.
    Use this for large MIDI files where you only need the raw event data.
    """
    return parse_midi_to_frames_optimized(
        midi_path, 
        enable_pattern_detection=False, 
        max_events_per_track=50000,  # Much higher limit when no pattern detection
        verbose=verbose
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python parser_optimized.py <input.mid> <output.json> [--fast] [--verbose]")
        print("  --fast: Skip pattern detection for maximum speed")
        print("  --verbose: Show progress information")
        sys.exit(1)

    midi_path = sys.argv[1]
    output_path = sys.argv[2]
    fast_mode = "--fast" in sys.argv
    verbose = "--verbose" in sys.argv

    print(f"Parsing {midi_path}...")
    start_time = time.time()
    
    if fast_mode:
        print("Fast mode: skipping pattern detection")
        parsed = parse_midi_to_frames_fast(midi_path, verbose=verbose)
    else:
        parsed = parse_midi_to_frames_optimized(midi_path, verbose=verbose)
    
    with open(output_path, 'w') as f:
        json.dump(parsed, f, indent=2)

    total_time = time.time() - start_time
    print(f"Parsed MIDI saved to {output_path}")
    print(f"Total time: {total_time:.2f}s")
    
    # Show performance summary
    stats = parsed.get('performance_stats', {})
    if stats:
        print(f"Events processed: {stats.get('total_events', 0)}")
        print(f"Tracks: {stats.get('tracks_processed', 0)} processed, {stats.get('tracks_skipped', 0)} skipped")
        if stats.get('pattern_detection_enabled'):
            print("Pattern detection: enabled")
        else:
            print("Pattern detection: disabled")
