#!/usr/bin/env python3
"""
Real-world performance test using input.mid to identify MIDI parsing bottlenecks
"""

import time
import psutil
import os
import sys
import traceback
import cProfile
import pstats
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def analyze_midi_file(midi_path):
    """Analyze the MIDI file complexity"""
    import mido
    
    print(f"🔍 Analyzing MIDI file: {midi_path}")
    print("=" * 50)
    
    try:
        mid = mido.MidiFile(midi_path)
        
        total_messages = 0
        tempo_changes = 0
        note_events = 0
        tracks_count = len(mid.tracks)
        
        for i, track in enumerate(mid.tracks):
            track_messages = len(track)
            total_messages += track_messages
            
            track_tempo_changes = 0
            track_notes = 0
            
            for msg in track:
                if msg.type == 'set_tempo':
                    tempo_changes += 1
                    track_tempo_changes += 1
                elif msg.type in ['note_on', 'note_off']:
                    note_events += 1 
                    track_notes += 1
            
            print(f"  Track {i}: {track_messages} messages, {track_notes} notes, {track_tempo_changes} tempo changes")
        
        print(f"\n📊 MIDI File Complexity:")
        print(f"   - File size: {Path(midi_path).stat().st_size:,} bytes")
        print(f"   - Tracks: {tracks_count}")
        print(f"   - Total messages: {total_messages:,}")
        print(f"   - Note events: {note_events:,}")
        print(f"   - Tempo changes: {tempo_changes}")
        print(f"   - Ticks per beat: {mid.ticks_per_beat}")
        print(f"   - Total length: {mid.length:.2f} seconds")
        
        return {
            'tracks': tracks_count,
            'messages': total_messages,
            'notes': note_events,
            'tempo_changes': tempo_changes,
            'duration': mid.length
        }
        
    except Exception as e:
        print(f"❌ Failed to analyze MIDI file: {e}")
        return None

def profile_current_parser(midi_path):
    """Profile the current MIDI parser with detailed timing"""
    print(f"\n🔬 Profiling Current Parser")
    print("=" * 30)
    
    from tracker.parser import parse_midi_to_frames
    
    # Measure system resources
    process = psutil.Process(os.getpid())
    memory_before = process.memory_info().rss / 1024 / 1024
    
    print("⏱️  Starting detailed profiling...")
    
    # Profile with cProfile
    profiler = cProfile.Profile()
    profiler.enable()
    
    start_time = time.time()
    try:
        result = parse_midi_to_frames(midi_path)
        end_time = time.time()
        
        profiler.disable()
        
        # Analyze results
        parsing_time = end_time - start_time
        memory_after = process.memory_info().rss / 1024 / 1024
        
        print(f"✅ Parsing completed in {parsing_time:.3f} seconds")
        print(f"📊 Memory: {memory_after:.1f} MB (Δ {memory_after - memory_before:+.1f} MB)")
        
        # Analyze parsed data
        events_count = sum(len(events) for events in result['events'].values())
        tracks_count = len(result['events'])
        metadata_entries = len(result['metadata'])
        
        print(f"📈 Results: {tracks_count} tracks, {events_count:,} events, {metadata_entries} metadata entries")
        
        # Check for expensive operations
        total_patterns = 0
        total_loops = 0
        for track_name, meta in result['metadata'].items():
            patterns = len(meta.get('patterns', {}))
            loops = len(meta.get('loops', []))
            total_patterns += patterns
            total_loops += loops
            if patterns > 0 or loops > 0:
                print(f"  🔍 {track_name}: {patterns} patterns, {loops} loops")
        
        if total_patterns > 0:
            print(f"⚠️  PERFORMANCE ISSUE: {total_patterns} patterns detected during parsing!")
            print("   This suggests expensive pattern detection is running unnecessarily.")
        
        # Show profiling results
        print(f"\n📊 Profiling Results (Top 15 functions by time):")
        print("-" * 80)
        
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        
        # Capture stats output
        import io
        s = io.StringIO()
        stats.print_stats(15, file=s)
        profile_output = s.getvalue()
        
        # Print relevant lines
        lines = profile_output.split('\n')
        for line in lines:
            if 'ncalls' in line or 'tottime' in line:
                print(line)
            elif any(keyword in line.lower() for keyword in ['pattern', 'tempo', 'detect', 'loop', 'midi', 'parse']):
                print(line)
        
        return parsing_time, result
        
    except Exception as e:
        profiler.disable()
        print(f"❌ Parsing failed: {e}")
        print("\nTraceback:")
        traceback.print_exc()
        return None, None

def test_optimized_approach(midi_path):
    """Test a simplified parser approach"""
    print(f"\n🚀 Testing Optimized Approach")
    print("=" * 30)
    
    # Create a minimal parser that only does basic MIDI-to-frames conversion
    def parse_midi_minimal(midi_path):
        import mido
        from collections import defaultdict
        from tracker.tempo_map import EnhancedTempoMap, TempoValidationConfig, TempoChangeType
        
        mid = mido.MidiFile(midi_path)
        
        # Minimal tempo map setup
        config = TempoValidationConfig(
            min_tempo_bpm=40.0,
            max_tempo_bpm=250.0,
            min_duration_frames=2,
            max_duration_frames=1800  # 30 seconds at 60fps
        )
        tempo_map = EnhancedTempoMap(
            initial_tempo=500000,
            validation_config=config,
            optimization_strategy=None  # No optimization
        )
        
        track_events = defaultdict(list)
        
        # Pass 1: Collect tempo changes only
        for track in mid.tracks:
            current_tick = 0
            for msg in track:
                current_tick += msg.time
                if msg.type == 'set_tempo':
                    try:
                        tempo_map.add_tempo_change(current_tick, msg.tempo, TempoChangeType.IMMEDIATE)
                    except Exception:
                        pass  # Skip invalid tempo changes
        
        # Pass 2: Process note events only 
        for i, track in enumerate(mid.tracks):
            current_tick = 0
            track_name = f"track_{i}"
            
            for msg in track:
                current_tick += msg.time
                
                if msg.type == 'track_name':
                    track_name = msg.name.strip().replace(" ", "_")
                elif msg.type in ['note_on', 'note_off']:
                    try:
                        frame = tempo_map.get_frame_for_tick(current_tick)
                        velocity = msg.velocity if msg.type == 'note_on' else 0
                        msg_type = 'note_off' if (msg.type == 'note_on' and velocity == 0) else msg.type
                        
                        track_events[track_name].append({
                            "frame": frame,
                            "note": msg.note,
                            "volume": velocity,
                            "type": msg_type,
                            "tempo": tempo_map.get_tempo_at_tick(current_tick)
                        })
                    except Exception as e:
                        # Skip problematic events
                        pass
        
        # Return minimal result - NO pattern detection, NO loop detection
        return {
            "events": dict(track_events),
            "metadata": {}  # Empty - no expensive analysis
        }
    
    # Test the minimal parser
    process = psutil.Process(os.getpid())
    memory_before = process.memory_info().rss / 1024 / 1024
    
    start_time = time.time()
    try:
        result = parse_midi_minimal(midi_path)
        end_time = time.time()
        
        memory_after = process.memory_info().rss / 1024 / 1024
        parsing_time = end_time - start_time
        
        events_count = sum(len(events) for events in result['events'].values())
        tracks_count = len(result['events'])
        
        print(f"✅ Minimal parsing completed in {parsing_time:.3f} seconds")
        print(f"📊 Memory: {memory_after:.1f} MB (Δ {memory_after - memory_before:+.1f} MB)")
        print(f"📈 Results: {tracks_count} tracks, {events_count:,} events")
        
        return parsing_time
        
    except Exception as e:
        print(f"❌ Minimal parser failed: {e}")
        traceback.print_exc()
        return None

def main():
    midi_file = "/Users/matias/src/midi2nes/input.mid"
    
    print("🎵 MIDI2NES Real-World Performance Analysis")
    print("=" * 60)
    print(f"📁 Target file: {midi_file}")
    
    # Step 1: Analyze MIDI complexity
    midi_stats = analyze_midi_file(midi_file)
    if not midi_stats:
        print("❌ Cannot analyze MIDI file")
        return False
    
    # Step 2: Profile current parser
    current_time, current_result = profile_current_parser(midi_file)
    if current_time is None:
        print("❌ Current parser failed")
        return False
    
    # Step 3: Test optimized approach
    optimized_time = test_optimized_approach(midi_file)
    
    # Step 4: Summary and recommendations
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE ANALYSIS SUMMARY")
    print("=" * 60)
    
    print(f"📁 MIDI File: {midi_stats['tracks']} tracks, {midi_stats['notes']:,} notes, {midi_stats['duration']:.1f}s")
    print(f"⏱️  Current Parser: {current_time:.3f} seconds")
    
    if optimized_time:
        speedup = current_time / optimized_time if optimized_time > 0 else float('inf')
        print(f"🚀 Optimized Parser: {optimized_time:.3f} seconds")
        print(f"⚡ Speedup: {speedup:.1f}x faster")
        
        if speedup > 2:
            print(f"\n✅ SIGNIFICANT PERFORMANCE IMPROVEMENT POSSIBLE!")
        elif speedup > 1.5:
            print(f"\n⚠️  MODERATE PERFORMANCE IMPROVEMENT POSSIBLE")
        else:
            print(f"\n💡 MINOR PERFORMANCE IMPROVEMENT POSSIBLE")
    
    print(f"\n🔧 RECOMMENDATIONS:")
    
    if current_time > 1.0:
        print(f"1. ❗ CRITICAL: Parsing takes {current_time:.2f}s - too slow for interactive use")
    elif current_time > 0.5:
        print(f"1. ⚠️  WARNING: Parsing takes {current_time:.2f}s - noticeable delay")
    else:
        print(f"1. ✅ INFO: Parsing takes {current_time:.2f}s - acceptable")
    
    if current_result and current_result.get('metadata'):
        total_analysis = sum(
            len(meta.get('patterns', {})) + len(meta.get('loops', []))
            for meta in current_result['metadata'].values()
        )
        if total_analysis > 0:
            print("2. 🎯 OPTIMIZATION: Remove pattern/loop detection from basic parsing")
            print("3. 🔧 ARCHITECTURE: Move analysis to separate pipeline steps")
        else:
            print("2. ✅ Good: No expensive analysis during parsing")
    
    print("4. 💾 CACHING: Consider caching tempo calculations")
    print("5. 🏃 LAZY: Use lazy evaluation for expensive operations")
    print("6. 📊 STREAMING: Consider streaming processing for large files")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
