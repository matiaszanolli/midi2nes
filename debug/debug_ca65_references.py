#!/usr/bin/env python3
"""Debug script to test CA65 exporter reference table generation."""

from pathlib import Path
from exporter.exporter_ca65 import CA65Exporter

def test_ca65_reference_table():
    """Test how the CA65 exporter handles reference table generation."""
    
    # Sample frames data (simulate the full frame data)
    frames = {
        'pulse1': {
            '30': {'note': 60, 'volume': 15},
            '210': {'note': 67, 'volume': 12},
            '390': {'note': 72, 'volume': 10},
            '570': {'note': 60, 'volume': 8}
        }
    }
    
    # Sample patterns
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
    
    # Sample references (the format that comes from main.py after position mapping)
    references = {
        '30': ('pattern_0', 0),    # Frame 30 -> pattern_0, offset 0
        '210': ('pattern_0', 1),   # Frame 210 -> pattern_0, offset 1  
        '390': ('pattern_1', 0),   # Frame 390 -> pattern_1, offset 0
        '570': ('pattern_1', 1)    # Frame 570 -> pattern_1, offset 1
    }
    
    print("Input data:")
    print(f"  Frames: {list(frames['pulse1'].keys())}")
    print(f"  References: {references}")
    
    # Test the exporter
    exporter = CA65Exporter()
    output_file = Path("test_ca65_output.asm")
    
    exporter.export_tables_with_patterns(
        frames, patterns, references, output_file, standalone=False
    )
    
    # Read and analyze the output
    with open(output_file, 'r') as f:
        content = f.read()
    
    print("\nAnalyzing generated assembly:")
    
    # Find pattern reference table
    lines = content.split('\n')
    in_pattern_refs = False
    pattern_ref_entries = []
    
    for line in lines:
        line = line.strip()
        if line == 'pattern_refs:':
            in_pattern_refs = True
            continue
        elif in_pattern_refs and (line.startswith('.word') or line.startswith('.byte')):
            pattern_ref_entries.append(line)
        elif in_pattern_refs and line == '':
            break
    
    print(f"  Pattern reference entries: {len(pattern_ref_entries)}")
    print("  First 20 entries:")
    for i, entry in enumerate(pattern_ref_entries[:20]):
        frame_num = i // 3  # 3 bytes per entry (.word + .word + .byte)
        if i % 3 == 0:
            print(f"    Frame {frame_num}: {entry}")
        else:
            print(f"      {entry}")
    
    if len(pattern_ref_entries) > 20:
        print(f"  ... and {len(pattern_ref_entries) - 20} more entries")
    
    # Calculate expected vs actual frame range
    expected_max_frame = max(int(k) for k in references.keys())
    actual_entries = len(pattern_ref_entries) // 3  # 3 bytes per frame
    
    print(f"\nFrame range analysis:")
    print(f"  Expected max frame: {expected_max_frame}")
    print(f"  Actual frame entries: {actual_entries}")
    print(f"  Missing frames: {expected_max_frame + 1 - actual_entries}")
    
    # Check if the references are correctly placed
    print(f"\nReference placement check:")
    for frame_str, (pattern_id, offset) in references.items():
        frame_num = int(frame_str)
        if frame_num < actual_entries:
            entry_start = frame_num * 3
            if entry_start < len(pattern_ref_entries):
                word_entry = pattern_ref_entries[entry_start]
                byte_entry = pattern_ref_entries[entry_start + 2] if entry_start + 2 < len(pattern_ref_entries) else "N/A"
                print(f"  Frame {frame_num}: {word_entry}, {byte_entry}")
            else:
                print(f"  Frame {frame_num}: Entry index {entry_start} out of range")
        else:
            print(f"  Frame {frame_num}: Beyond generated table (max: {actual_entries - 1})")
    
    # Cleanup
    output_file.unlink()

if __name__ == "__main__":
    test_ca65_reference_table()
