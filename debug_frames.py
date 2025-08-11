#!/usr/bin/env python3

import json
from nes.emulator_core import NESEmulatorCore

def debug_frame_generation():
    # Load the mapped data
    with open('simple_loop_mapped.json', 'r') as f:
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

if __name__ == "__main__":
    debug_frame_generation()
