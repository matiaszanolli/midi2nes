#!/usr/bin/env python3
"""Enhanced debug script for CA65 exporter logic."""

from pathlib import Path

def debug_ca65_logic():
    """Debug the CA65 exporter logic step by step."""
    
    # Sample references (the format that comes from main.py after position mapping)
    references = {
        '30': ('pattern_0', 0),    # Frame 30 -> pattern_0, offset 0
        '210': ('pattern_0', 1),   # Frame 210 -> pattern_0, offset 1  
        '390': ('pattern_1', 0),   # Frame 390 -> pattern_1, offset 0
        '570': ('pattern_1', 1)    # Frame 570 -> pattern_1, offset 1
    }
    
    print("Debugging CA65 exporter logic:")
    print(f"Input references: {references}")
    
    # Replicate the logic from export_tables_with_patterns
    frame_to_pattern = {}
    max_frame = 0
    
    if references:
        for frame_str, pattern_info in references.items():
            # Convert string frame to integer
            frame_num = int(frame_str)
            pattern_id, offset = pattern_info
            frame_to_pattern[frame_num] = (pattern_id, offset)
            max_frame = max(max_frame, frame_num)
            print(f"  Processing: frame {frame_num} -> {pattern_info}")
    
    print(f"\nCalculated max_frame: {max_frame}")
    print(f"Frame range to generate: 0 to {max_frame} (inclusive)")
    print(f"Total frames to generate: {max_frame + 1}")
    
    # Simulate the reference table generation
    entries = []
    for frame in range(max_frame + 1):
        if frame in frame_to_pattern:
            pattern_id, offset = frame_to_pattern[frame]
            entries.append(f"Frame {frame}: .word {pattern_id}, .byte {offset}")
        else:
            entries.append(f"Frame {frame}: .word 0, .byte 0")
    
    print(f"\nGenerated entries: {len(entries)}")
    print("First 10 entries:")
    for entry in entries[:10]:
        print(f"  {entry}")
    
    print("...")
    print("Last 10 entries:")
    for entry in entries[-10:]:
        print(f"  {entry}")
    
    # Check specific frames
    print("\nSpecific frame checks:")
    for frame_str in references.keys():
        frame_num = int(frame_str)
        if frame_num < len(entries):
            print(f"  Frame {frame_num}: {entries[frame_num]}")
        else:
            print(f"  Frame {frame_num}: OUT OF RANGE (entries: {len(entries)})")

if __name__ == "__main__":
    debug_ca65_logic()
