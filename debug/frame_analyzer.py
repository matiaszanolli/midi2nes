#!/usr/bin/env python3
"""Frame generation debugging utilities."""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from nes.emulator_core import NESEmulatorCore


def analyze_frames(mapped_file='simple_loop_mapped.json'):
    """Analyze frame generation from mapped data."""
    try:
        # Load the mapped data
        with open(mapped_file, 'r') as f:
            mapped_data = json.load(f)
        
        print("Mapped data loaded:")
        for channel, events in mapped_data.items():
            print(f"  {channel}: {len(events)} events")
            if events:
                print(f"    First event: {events[0]}")
                print(f"    Last event: {events[-1]}")
        
        # Create emulator and process tracks
        emulator = NESEmulatorCore()
        frames = emulator.process_all_tracks(mapped_data)
        
        print("\nProcessed frames:")
        for channel, channel_frames in frames.items():
            print(f"  {channel}: {len(channel_frames)} frames")
            if channel_frames:
                frame_keys = sorted(channel_frames.keys())
                print(f"    Frame range: {frame_keys[0]} - {frame_keys[-1]}")
                print(f"    First frame: {channel_frames[frame_keys[0]]}")
        
        # Debug: Process just pulse1 manually to see what happens
        if 'pulse1' in mapped_data:
            print("\nDebugging pulse1 manually:")
            pulse1_events = mapped_data['pulse1']
            print(f"Input events: {len(pulse1_events)}")
            
            # Filter only note_on events with volume > 0
            note_on_events = [e for e in pulse1_events if e.get('volume', 0) > 0]
            print(f"Note_on events with volume > 0: {len(note_on_events)}")
            
            for i, event in enumerate(note_on_events[:3]):  # Show first 3 events
                print(f"  Event {i}: frame={event['frame']}, note={event['note']}, volume={event['volume']}")
            
            # Call compile_channel_to_frames directly
            pulse1_frames = emulator.compile_channel_to_frames(pulse1_events, 'pulse1')
            print(f"Generated pulse1 frames: {len(pulse1_frames)}")
            
            if pulse1_frames:
                frame_keys = sorted(pulse1_frames.keys())
                print(f"Frame range: {frame_keys[0]} - {frame_keys[-1]}")
                print(f"First frame data: {pulse1_frames[frame_keys[0]]}")
        
        return frames
        
    except FileNotFoundError:
        print(f"❌ Mapped file not found: {mapped_file}")
        return None
    except Exception as e:
        print(f"❌ Error analyzing frames: {e}")
        return None


def debug_frame_generation(mapped_file='simple_loop_mapped.json'):
    """Legacy function name for compatibility."""
    return analyze_frames(mapped_file)


def main():
    """CLI entry point for frame analysis."""
    mapped_file = sys.argv[1] if len(sys.argv) > 1 else 'simple_loop_mapped.json'
    analyze_frames(mapped_file)


if __name__ == "__main__":
    main()
