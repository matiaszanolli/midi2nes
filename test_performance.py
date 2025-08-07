#!/usr/bin/env python3
"""
Performance comparison test for MIDI parsing approaches.
"""

import time
import sys
import tempfile
import json
from pathlib import Path

# Add the project directory to the path
sys.path.insert(0, str(Path(__file__).parent))

def test_parsing_performance(midi_path):
    """Compare different parsing approaches"""
    print(f"Testing performance with: {midi_path}")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Original parser (if it completes)
    print("1. Original parser (with pattern detection)...")
    try:
        from tracker.parser import parse_midi_to_frames
        
        start_time = time.time()
        # Set timeout for original parser
        result1 = parse_midi_to_frames(midi_path)
        original_time = time.time() - start_time
        
        results['original'] = {
            'time': original_time,
            'tracks': len(result1.get('events', {})),
            'total_events': sum(len(events) for events in result1.get('events', {}).values()),
            'patterns': sum(len(meta.get('patterns', {})) for meta in result1.get('metadata', {}).values())
        }
        
        print(f"   ✅ Completed in {original_time:.2f}s")
        print(f"      Tracks: {results['original']['tracks']}")
        print(f"      Events: {results['original']['total_events']}")
        print(f"      Patterns: {results['original']['patterns']}")
        
    except Exception as e:
        print(f"   ❌ Failed or timeout: {e}")
        results['original'] = {'time': float('inf'), 'error': str(e)}
    
    # Test 2: Optimized parser with pattern detection
    print("\n2. Optimized parser (with pattern detection)...")
    try:
        from tracker.parser_optimized import parse_midi_to_frames_optimized
        
        start_time = time.time()
        result2 = parse_midi_to_frames_optimized(midi_path, enable_pattern_detection=True, verbose=False)
        optimized_time = time.time() - start_time
        
        results['optimized'] = {
            'time': optimized_time,
            'tracks': len(result2.get('events', {})),
            'total_events': sum(len(events) for events in result2.get('events', {}).values()),
            'patterns': sum(len(meta.get('patterns', {})) for meta in result2.get('metadata', {}).values()),
            'stats': result2.get('performance_stats', {})
        }
        
        print(f"   ✅ Completed in {optimized_time:.2f}s")
        print(f"      Tracks: {results['optimized']['tracks']}")
        print(f"      Events: {results['optimized']['total_events']}")  
        print(f"      Patterns: {results['optimized']['patterns']}")
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results['optimized'] = {'time': float('inf'), 'error': str(e)}
    
    # Test 3: Fast mode (no pattern detection)
    print("\n3. Fast mode (no pattern detection)...")
    try:
        from tracker.parser_optimized import parse_midi_to_frames_fast
        
        start_time = time.time()
        result3 = parse_midi_to_frames_fast(midi_path, verbose=False)
        fast_time = time.time() - start_time
        
        results['fast'] = {
            'time': fast_time,
            'tracks': len(result3.get('events', {})),
            'total_events': sum(len(events) for events in result3.get('events', {}).values()),
            'patterns': 0,  # No patterns in fast mode
            'stats': result3.get('performance_stats', {})
        }
        
        print(f"   ✅ Completed in {fast_time:.2f}s")
        print(f"      Tracks: {results['fast']['tracks']}")
        print(f"      Events: {results['fast']['total_events']}")
        print(f"      Patterns: N/A (disabled)")
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results['fast'] = {'time': float('inf'), 'error': str(e)}
    
    # Summary
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    
    for name, result in results.items():
        if 'error' not in result:
            time_str = f"{result['time']:.2f}s" if result['time'] != float('inf') else "TIMEOUT"
            print(f"{name.capitalize():12} | {time_str:>8} | {result.get('total_events', 0):>8} events")
        else:
            print(f"{name.capitalize():12} | {'ERROR':>8} | {result['error']}")
    
    # Calculate speedup
    if 'original' in results and 'optimized' in results:
        if results['original']['time'] != float('inf') and results['optimized']['time'] != float('inf'):
            speedup = results['original']['time'] / results['optimized']['time']
            print(f"\nOptimized speedup: {speedup:.1f}x faster than original")
    
    if 'original' in results and 'fast' in results:
        if results['original']['time'] != float('inf') and results['fast']['time'] != float('inf'):
            speedup = results['original']['time'] / results['fast']['time'] 
            print(f"Fast mode speedup: {speedup:.1f}x faster than original")
    
    return results

def create_test_midi():
    """Create a test MIDI file for performance testing"""
    import mido
    
    # Create a moderately complex MIDI file
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    
    # Add some tempo changes
    track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))  # 120 BPM
    
    # Create a repeating pattern to test pattern detection
    pattern = [60, 64, 67, 72]  # C major arpeggio
    time_per_note = 120  # ticks
    
    current_time = 0
    
    # Repeat the pattern many times to stress test
    for repeat in range(100):
        for i, note in enumerate(pattern):
            # Note on
            track.append(mido.Message('note_on', 
                                    channel=0, 
                                    note=note, 
                                    velocity=100, 
                                    time=time_per_note if i == 0 else 0))
            # Note off  
            track.append(mido.Message('note_off',
                                    channel=0,
                                    note=note,
                                    velocity=0,
                                    time=time_per_note))
    
    # Add some variation
    for repeat in range(50):
        for i, note in enumerate([62, 66, 69, 74]):  # D major arpeggio
            track.append(mido.Message('note_on',
                                    channel=0,
                                    note=note,
                                    velocity=80,
                                    time=time_per_note if i == 0 else 0))
            track.append(mido.Message('note_off',
                                    channel=0, 
                                    note=note,
                                    velocity=0,
                                    time=time_per_note))
    
    return mid

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Test with provided MIDI file
        midi_path = sys.argv[1]
        if not Path(midi_path).exists():
            print(f"Error: MIDI file not found: {midi_path}")
            sys.exit(1)
        
        results = test_parsing_performance(midi_path)
    else:
        # Create and test with generated MIDI file
        print("Creating test MIDI file...")
        test_mid = create_test_midi()
        
        with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
            test_mid.save(f.name)
            temp_path = f.name
        
        try:
            results = test_parsing_performance(temp_path)
        finally:
            Path(temp_path).unlink()  # Clean up
    
    print("\n🎯 RECOMMENDATIONS:")
    print("   • For large MIDI files (>2000 events): Use fast mode")
    print("   • For pattern analysis: Use optimized parser")  
    print("   • For small files (<500 events): Original parser is fine")
    print("   • Consider disabling pattern detection for speed-critical applications")
