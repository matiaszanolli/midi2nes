#!/usr/bin/env python3
"""Script to inspect CA65 exporter output in detail."""

from pathlib import Path
from exporter.exporter_ca65 import CA65Exporter

def inspect_ca65_output():
    """Inspect the actual CA65 exporter output."""
    
    # Sample data
    frames = {
        'pulse1': {
            '30': {'note': 60, 'volume': 15},
            '210': {'note': 67, 'volume': 12},
            '390': {'note': 72, 'volume': 10},
            '570': {'note': 60, 'volume': 8}
        }
    }
    
    patterns = {
        'pattern_0': {
            'events': [
                {'note': 60, 'volume': 15},
                {'note': 67, 'volume': 12}
            ]
        },
        'pattern_1': {
            'events': [
                {'note': 72, 'volume': 10},
                {'note': 60, 'volume': 8}
            ]
        }
    }
    
    references = {
        '30': ('pattern_0', 0),
        '210': ('pattern_0', 1),
        '390': ('pattern_1', 0),
        '570': ('pattern_1', 1)
    }
    
    print("Generating CA65 assembly with actual exporter...")
    
    exporter = CA65Exporter()
    output_file = Path("inspect_ca65_output.asm")
    
    # Generate the output
    exporter.export_tables_with_patterns(
        frames, patterns, references, output_file, standalone=False
    )
    
    # Read the full content
    with open(output_file, 'r') as f:
        content = f.read()
    
    # Split into lines and find pattern_refs section
    lines = content.split('\n')
    
    # Find the pattern_refs section
    pattern_refs_start = None
    pattern_refs_end = None
    
    for i, line in enumerate(lines):
        if line.strip() == 'pattern_refs:':
            pattern_refs_start = i + 1
        elif pattern_refs_start is not None and line.strip() == '' and not lines[i-1].strip().startswith('.'):
            pattern_refs_end = i
            break
    
    if pattern_refs_start is None:
        print("ERROR: Could not find pattern_refs section!")
        return
    
    if pattern_refs_end is None:
        pattern_refs_end = len(lines)
    
    # Extract pattern reference entries
    pattern_ref_lines = []
    for i in range(pattern_refs_start, pattern_refs_end):
        line = lines[i].strip()
        if line.startswith('.word') or line.startswith('.byte'):
            pattern_ref_lines.append(line)
    
    print(f"Found pattern_refs section from line {pattern_refs_start} to {pattern_refs_end}")
    print(f"Pattern reference entries: {len(pattern_ref_lines)}")
    
    # Calculate number of frames (each frame = 3 lines: .word, .word, .byte)
    # Wait, that's wrong - each frame should be 3 bytes total, not 3 lines
    # Let me recheck the format...
    
    print(f"\\nFirst 30 pattern reference lines:")
    for i, line in enumerate(pattern_ref_lines[:30]):
        print(f"  {i:3d}: {line}")
    
    print(f"\\nLast 10 pattern reference lines:")
    start_idx = max(0, len(pattern_ref_lines) - 10)
    for i, line in enumerate(pattern_ref_lines[start_idx:], start_idx):
        print(f"  {i:3d}: {line}")
    
    # Try to parse the frame structure
    print(f"\\nFrame structure analysis:")
    
    # Look for the pattern in lines: should be groups of 3 bytes per frame
    # But the format is: .word pattern_id, .byte offset for each frame
    # So it's actually 2 lines per frame in the assembly (.word takes 2 bytes, .byte takes 1)
    
    word_lines = [line for line in pattern_ref_lines if line.startswith('.word')]
    byte_lines = [line for line in pattern_ref_lines if line.startswith('.byte')]
    
    print(f"  .word lines: {len(word_lines)}")
    print(f"  .byte lines: {len(byte_lines)}")
    
    # Each frame should have 1 .word and 1 .byte, so frames = min(word_lines, byte_lines)
    estimated_frames = min(len(word_lines), len(byte_lines))
    print(f"  Estimated frames: {estimated_frames}")
    
    # Check specific frame entries
    print(f"\\nFrame content check:")
    
    # Group lines into frame entries (assuming .word followed by .byte)
    frame_entries = []
    i = 0
    while i < len(pattern_ref_lines) - 1:
        if (pattern_ref_lines[i].startswith('.word') and 
            i + 1 < len(pattern_ref_lines) and 
            pattern_ref_lines[i + 1].startswith('.byte')):
            frame_entries.append((pattern_ref_lines[i], pattern_ref_lines[i + 1]))
            i += 2
        else:
            i += 1
    
    print(f"  Parsed frame entries: {len(frame_entries)}")
    
    # Check key frames
    key_frames = [30, 210, 390, 570]
    for frame_num in key_frames:
        if frame_num < len(frame_entries):
            word_line, byte_line = frame_entries[frame_num]
            print(f"  Frame {frame_num}: {word_line}, {byte_line}")
        else:
            print(f"  Frame {frame_num}: OUT OF RANGE (only {len(frame_entries)} frames)")
    
    # Cleanup
    output_file.unlink()

if __name__ == "__main__":
    inspect_ca65_output()
