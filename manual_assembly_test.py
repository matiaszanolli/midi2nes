#!/usr/bin/env python3
"""Generate assembly file manually to debug CC65 compilation issue."""

from pathlib import Path
from exporter.exporter_ca65 import CA65Exporter

def generate_assembly_for_debugging():
    """Generate assembly file to debug the CC65 compilation truncation issue."""
    
    # Simulate the data that caused 931 frames in the reference table
    frames = {'pulse1': {}}
    
    # Create frame data for expected range 
    key_frames = [30, 210, 570, 930]
    for frame in key_frames:
        frames['pulse1'][str(frame)] = {'note': 60, 'volume': 8}
    
    patterns = {
        'pattern_0': {
            'events': [
                {'note': 60, 'volume': 8}
            ]
        }
    }
    
    references = {
        '30': ('pattern_0', 0),
        '210': ('pattern_0', 1),
        '570': ('pattern_0', 2),
        '930': ('pattern_0', 3)
    }
    
    print("Generating assembly for debugging CC65 issue...")
    print(f"References: {references}")
    print(f"Expected max frame: {max(int(k) for k in references.keys())}")
    
    # Generate assembly
    exporter = CA65Exporter()
    output_file = Path("debug_music.asm")
    
    exporter.export_tables_with_patterns(
        frames, patterns, references, output_file, standalone=True
    )
    
    # Analyze the generated assembly
    with open(output_file, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # Find pattern reference section
    in_pattern_refs = False
    pattern_ref_lines = []
    pattern_refs_start = None
    
    for i, line in enumerate(lines):
        if line.strip() == 'pattern_refs:':
            in_pattern_refs = True
            pattern_refs_start = i
            continue
        elif in_pattern_refs and line.strip() == '':
            break
        elif in_pattern_refs:
            pattern_ref_lines.append(line.strip())
    
    word_lines = [line for line in pattern_ref_lines if line.startswith('.word')]
    byte_lines = [line for line in pattern_ref_lines if line.startswith('.byte')]
    
    frame_count = min(len(word_lines), len(byte_lines))
    
    print(f"\nGenerated assembly analysis:")
    print(f"  Total lines in file: {len(lines)}")
    print(f"  Pattern refs start at line: {pattern_refs_start}")
    print(f"  Pattern ref entries: {len(pattern_ref_lines)}")
    print(f"  Calculated frames: {frame_count}")
    print(f"  File size: {len(content)} characters")
    
    # Check specific frames
    print(f"\nChecking specific frame references:")
    for i, ref_frame in enumerate([30, 210, 570, 930]):
        if i * 2 < len(word_lines) and i * 2 < len(byte_lines):
            word_line = word_lines[ref_frame] if ref_frame < len(word_lines) else "MISSING"
            byte_line = byte_lines[ref_frame] if ref_frame < len(byte_lines) else "MISSING"
            print(f"  Frame {ref_frame}: {word_line}, {byte_line}")
        else:
            print(f"  Frame {ref_frame}: BEYOND GENERATED DATA")
    
    print(f"\nFirst 10 pattern ref entries:")
    for i in range(min(10, len(pattern_ref_lines))):
        print(f"  {i}: {pattern_ref_lines[i]}")
    
    print(f"\nLast 10 pattern ref entries:")
    start_idx = max(0, len(pattern_ref_lines) - 10)
    for i in range(start_idx, len(pattern_ref_lines)):
        print(f"  {i}: {pattern_ref_lines[i]}")
    
    return output_file

if __name__ == "__main__":
    output_file = generate_assembly_for_debugging()
    print(f"\nGenerated assembly file: {output_file}")
    print("You can examine the full content with: cat debug_music.asm")
