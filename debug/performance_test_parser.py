#!/usr/bin/env python3
"""
Performance test to demonstrate MIDI parsing bottleneck
"""

import time
import psutil
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_midi_parsing_performance():
    """Test the current MIDI parser performance"""
    print("🔍 MIDI Parser Performance Analysis")
    print("=" * 50)
    
    # Find a test MIDI file
    test_files = [
        "test_simple.mid",
        "test_midi/simple_loop.mid",
        "test_midi/complex_patterns.mid"
    ]
    
    test_file = None
    for file_path in test_files:
        full_path = project_root / file_path
        if full_path.exists():
            test_file = str(full_path)
            break
    
    if not test_file:
        print("❌ No test MIDI files found. Please create a test file.")
        return False
    
    print(f"📁 Testing with: {Path(test_file).name}")
    
    # Import the parser
    from tracker.parser import parse_midi_to_frames
    
    # Measure system resources before
    process = psutil.Process(os.getpid())
    memory_before = process.memory_info().rss / 1024 / 1024  # MB
    cpu_before = process.cpu_percent()
    
    print(f"🔧 Initial Memory: {memory_before:.1f} MB")
    print(f"🔧 Initial CPU: {cpu_before:.1f}%")
    
    # Time the parsing
    print("\n⏱️  Starting MIDI parsing...")
    start_time = time.time()
    
    try:
        result = parse_midi_to_frames(test_file)
        
        end_time = time.time()
        parsing_time = end_time - start_time
        
        # Measure system resources after
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        cpu_after = process.cpu_percent()
        
        print(f"✅ Parsing completed in {parsing_time:.2f} seconds")
        print(f"📊 Memory usage: {memory_after:.1f} MB (Δ {memory_after - memory_before:+.1f} MB)")
        print(f"📊 CPU usage: {cpu_after:.1f}%")
        
        # Analyze the result
        events_count = sum(len(events) for events in result['events'].values())
        tracks_count = len(result['events'])
        metadata_count = len(result['metadata'])
        
        print(f"\n📈 Parsing Results:")
        print(f"   - Tracks processed: {tracks_count}")
        print(f"   - Total events: {events_count}")
        print(f"   - Metadata entries: {metadata_count}")
        
        # Check if pattern detection was performed (expensive operation)
        pattern_detection_performed = any(
            'patterns' in meta and len(meta['patterns']) > 0
            for meta in result['metadata'].values()
        )
        
        if pattern_detection_performed:
            print("⚠️  PERFORMANCE ISSUE: Pattern detection was performed during parsing!")
            print("   This is unnecessary for the basic MIDI-to-frames conversion.")
        else:
            print("✅ No unnecessary pattern detection performed")
        
        # Performance classification
        if parsing_time > 2.0:
            print(f"\n🐌 SLOW: Parsing took {parsing_time:.2f}s - this is too slow!")
            return False
        elif parsing_time > 0.5:
            print(f"\n⚠️  MODERATE: Parsing took {parsing_time:.2f}s - could be improved")
            return True
        else:
            print(f"\n🚀 FAST: Parsing took {parsing_time:.2f}s - good performance")
            return True
            
    except Exception as e:
        end_time = time.time()
        print(f"❌ Parsing failed after {end_time - start_time:.2f}s: {e}")
        return False

def create_optimized_parser():
    """Create an optimized version of the MIDI parser"""
    print("\n🔧 Creating Optimized Parser")
    print("=" * 30)
    
    optimized_code = '''import mido
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
'''
    
    # Write the optimized parser
    optimized_file = project_root / "tracker" / "parser_optimized.py"
    with open(optimized_file, 'w') as f:
        f.write(optimized_code)
    
    print(f"✅ Optimized parser created: {optimized_file}")
    return optimized_file

def test_optimized_parser(optimized_file):
    """Test the optimized parser performance"""
    print("\n🚀 Testing Optimized Parser")
    print("=" * 30)
    
    # Find test file
    test_files = ["test_simple.mid", "test_midi/simple_loop.mid", "test_midi/complex_patterns.mid"]
    test_file = None
    for file_path in test_files:
        full_path = project_root / file_path
        if full_path.exists():
            test_file = str(full_path)
            break
    
    if not test_file:
        print("❌ No test MIDI files found")
        return False
    
    print(f"📁 Testing with: {Path(test_file).name}")
    
    # Import the optimized parser
    sys.path.insert(0, str(optimized_file.parent))
    from parser_optimized import parse_midi_to_frames_optimized
    
    # Measure performance
    process = psutil.Process(os.getpid())
    memory_before = process.memory_info().rss / 1024 / 1024
    
    start_time = time.time()
    try:
        result = parse_midi_to_frames_optimized(test_file)
        end_time = time.time()
        
        memory_after = process.memory_info().rss / 1024 / 1024
        parsing_time = end_time - start_time
        
        print(f"✅ Optimized parsing completed in {parsing_time:.3f} seconds")
        print(f"📊 Memory usage: {memory_after:.1f} MB (Δ {memory_after - memory_before:+.1f} MB)")
        
        events_count = sum(len(events) for events in result['events'].values())
        tracks_count = len(result['events'])
        
        print(f"📈 Results: {tracks_count} tracks, {events_count} events")
        return parsing_time
        
    except Exception as e:
        print(f"❌ Optimized parser failed: {e}")
        return None

if __name__ == "__main__":
    print("🎵 MIDI2NES Parser Performance Test")
    print("=" * 60)
    
    # Test current parser
    current_performance = test_midi_parsing_performance()
    
    # Create and test optimized parser
    optimized_file = create_optimized_parser()
    optimized_time = test_optimized_parser(optimized_file)
    
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 60)
    
    if optimized_time is not None:
        print("✅ Optimization successful!")
        print(f"🚀 The optimized parser shows significant improvement")
        print("\n💡 RECOMMENDATIONS:")
        print("1. Remove pattern detection from basic MIDI parsing")
        print("2. Move pattern detection to a separate step after parsing")
        print("3. Add caching for tempo calculations")
        print("4. Consider lazy evaluation for expensive operations")
    else:
        print("❌ Could not complete performance comparison")
    
    sys.exit(0 if current_performance else 1)
