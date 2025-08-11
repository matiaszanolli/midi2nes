#!/usr/bin/env python3
"""Comprehensive music structure analysis utilities for NES ROMs."""

import sys
import math
from pathlib import Path


def freq_to_note_name(freq):
    """Convert frequency to approximate note name."""
    if freq <= 0:
        return "?"
        
    # A4 = 440 Hz
    A4 = 440.0
    
    try:
        # Calculate semitones from A4
        semitones_from_a4 = round(12 * math.log2(freq / A4))
        
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        # A4 is 9 semitones above C4
        semitones_from_c = (semitones_from_a4 + 9) % 12
        octave = 4 + (semitones_from_a4 + 9) // 12
        
        if octave < 0 or octave > 8:
            return f"~{freq:.0f}Hz"
            
        return f"{note_names[semitones_from_c]}{octave}"
    except:
        return f"~{freq:.0f}Hz"


def analyze_music_structure(rom_path):
    """Comprehensive analysis of music structure in NES ROM."""
    try:
        with open(rom_path, 'rb') as f:
            rom_data = f.read()
        
        print(f"🎵 Music Structure Analysis: {Path(rom_path).name}")
        print("=" * 60)
        
        # Find pattern data by looking for sequences of volume + timer data
        print("🔍 Searching for pattern data...")
        
        # Look for sequences that look like pattern data: volume, timer_low, timer_high
        pattern_candidates = []
        for i in range(len(rom_data) - 20):
            # Look for sequences of 3-byte entries that could be patterns
            if (rom_data[i] > 0 and rom_data[i] <= 15 and  # Volume 1-15
                i + 2 < len(rom_data)):
                
                volume = rom_data[i]
                timer_low = rom_data[i+1] 
                timer_high = rom_data[i+2] & 0x07  # Only low 3 bits matter
                
                # Calculate approximate frequency from timer value
                if timer_low > 0 or timer_high > 0:
                    timer_val = timer_low | (timer_high << 8)
                    if timer_val > 0:
                        # NES APU frequency calculation: freq = 1789773 / (16 * (timer + 1))
                        try:
                            freq = 1789773 / (16 * (timer_val + 1))
                            if 80 <= freq <= 4000:  # Reasonable music frequency range
                                pattern_candidates.append({
                                    'offset': i,
                                    'volume': volume,
                                    'timer': timer_val,
                                    'freq': freq,
                                    'data': rom_data[i:i+3].hex()
                                })
                        except:
                            pass
        
        # Group consecutive pattern entries
        if pattern_candidates:
            print(f"📊 Found {len(pattern_candidates)} potential pattern entries")
            
            # Show first 10 entries
            print("\n🎼 Pattern Data Sample:")
            for i, entry in enumerate(pattern_candidates[:10]):
                note_name = freq_to_note_name(entry['freq'])
                print(f"  #{i+1:2d} @ 0x{entry['offset']:04X}: Vol={entry['volume']:2d}, "
                      f"Timer={entry['timer']:3d}, Freq={entry['freq']:6.1f}Hz ({note_name}), "
                      f"Data={entry['data']}")
            
            if len(pattern_candidates) > 10:
                print(f"     ... and {len(pattern_candidates) - 10} more entries")
        
        # Look for pattern reference table
        print("\n🔗 Searching for pattern reference table...")
        
        # In the NES ROM, look for the specific pattern reference structure
        # Based on the hexdump, it should be around offset 0x78
        pattern_refs_start = None
        
        # Look for the characteristic pattern reference structure
        for i in range(0x70, min(0x200, len(rom_data))):
            if i + 8 < len(rom_data):
                # Check if we see the pattern: 08 d6 00 08 d6 00 (repeating pattern refs)
                # Pattern: low_byte, high_byte, offset
                if (rom_data[i] == 0x08 and rom_data[i + 1] == 0xd6 and rom_data[i + 2] == 0x00 and
                    rom_data[i + 3] == 0x08 and rom_data[i + 4] == 0xd6 and rom_data[i + 5] == 0x00):
                    pattern_refs_start = i
                    print(f"📍 Found pattern reference table at offset 0x{i:04X}")
                    break
        
        ref_candidates = []
        if pattern_refs_start is not None:
            # Parse the reference table until we hit the end marker
            i = pattern_refs_start
            frame_num = 0
            
            while i + 2 < len(rom_data):
                # Read 3 bytes: pattern_id_low, pattern_id_high, offset
                pattern_low = rom_data[i]
                pattern_high = rom_data[i + 1]
                offset_byte = rom_data[i + 2]
                
                # Check for end marker (common patterns: 0x6D 0x80 or similar)
                if ((pattern_low == 0x6d or pattern_low == 0x00) and 
                    (pattern_high == 0x80 or pattern_high == 0x00)):
                    print(f"🛑 End marker found at 0x{i:04X}: {pattern_low:02X} {pattern_high:02X} {offset_byte:02X}")
                    break
                
                pattern_addr = pattern_low | (pattern_high << 8)
                
                ref_candidates.append({
                    'frame': frame_num,
                    'word': pattern_addr,
                    'offset': offset_byte,
                    'addr': i
                })
                
                frame_num += 1
                i += 3
                
                # Safety limit
                if frame_num > 1000:
                    print("⚠️  Hit safety limit of 1000 frames")
                    break
        
        if ref_candidates:
            # Find the most promising reference table (longest consecutive sequence)
            print(f"📋 Found pattern reference table with {len(ref_candidates)} entries")
            
            # Show structure
            non_null_refs = [r for r in ref_candidates if r['word'] != 0]
            null_refs = [r for r in ref_candidates if r['word'] == 0]
            
            print(f"   Non-null references: {len(non_null_refs)}")
            print(f"   Null references: {len(null_refs)}")
            
            if non_null_refs:
                print("\n🎯 Active Pattern References:")
                for ref in non_null_refs[:15]:  # Show first 15
                    print(f"     Frame {ref['frame']:2d}: Pattern @ 0x{ref['word']:04X}, Offset {ref['offset']}")
                    
                if len(non_null_refs) > 15:
                    print(f"     ... and {len(non_null_refs) - 15} more references")
        
        # Analyze timing and loop structure
        print("\n⏱️  Music Timing Analysis:")
        if ref_candidates:
            total_frames = len(ref_candidates)
            active_frames = len([r for r in ref_candidates if r['word'] != 0])
            
            print(f"   Total song length: {total_frames} frames")
            print(f"   Active frames: {active_frames}")
            print(f"   Silent frames: {total_frames - active_frames}")
            
            # Calculate timing (assuming 60 FPS)
            duration_seconds = total_frames / 60.0
            print(f"   Estimated duration: {duration_seconds:.1f} seconds")
            
            # Look for loop patterns
            if non_null_refs:
                frame_pattern = [r['frame'] for r in non_null_refs]
                if len(frame_pattern) >= 2:
                    intervals = [frame_pattern[i+1] - frame_pattern[i] for i in range(len(frame_pattern)-1)]
                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        print(f"   Average note interval: {avg_interval:.1f} frames ({avg_interval/60:.2f}s)")
        
        # Look for potential issues
        print("\n⚠️  Potential Issues:")
        issues_found = []
        
        if not pattern_candidates:
            issues_found.append("No pattern data found")
        elif len(pattern_candidates) < 5:
            issues_found.append(f"Very few pattern entries ({len(pattern_candidates)}) - might be too short")
            
        if not ref_candidates:
            issues_found.append("No pattern reference table found")
        elif len(ref_candidates) < 10:
            issues_found.append(f"Very short reference table ({len(ref_candidates)} frames)")
            
        if ref_candidates and len(ref_candidates) < 60:  # Less than 1 second
            issues_found.append("Song appears very short (less than 1 second)")
            
        if pattern_candidates and len(set(entry['volume'] for entry in pattern_candidates[:10])) == 1:
            vol = pattern_candidates[0]['volume']
            if vol == 0:
                issues_found.append("All pattern entries have volume 0 (silence)")
            else:
                print(f"   All visible patterns use volume {vol} (might be intentional)")
        
        if issues_found:
            for issue in issues_found:
                print(f"   ❌ {issue}")
        else:
            print("   ✅ No obvious structural issues detected")
            
        return True
        
    except FileNotFoundError:
        print(f"❌ ROM file not found: {rom_path}")
        return False
    except Exception as e:
        print(f"❌ Error analyzing ROM: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """CLI entry point for music structure analysis."""
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "test_midi/simple_loop.nes"
    analyze_music_structure(rom_path)


if __name__ == "__main__":
    main()
