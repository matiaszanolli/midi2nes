#!/usr/bin/env python3
"""Advanced pattern reference table analysis utilities for NES ROMs."""

import sys
import struct
from pathlib import Path


def debug_pattern_references(rom_path):
    """Analyze the pattern reference table structure in detail."""
    
    print(f"🔍 Advanced Pattern Reference Analysis: {rom_path}")
    print("=" * 60)
    
    try:
        with open(rom_path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        print(f"❌ ROM file not found: {rom_path}")
        return False
    
    # Verify NES ROM structure
    if len(data) < 16 or data[0:4] != b'NES\x1a':
        print("❌ Invalid NES ROM file")
        return False
    
    header = data[0:16]
    prg_banks = header[4]
    chr_banks = header[5]
    mapper = ((header[7] & 0xF0) | (header[6] >> 4))
    prg_size = prg_banks * 16384
    
    print(f"📋 ROM Header:")
    print(f"   Total size: {len(data):,} bytes")
    print(f"   PRG banks: {prg_banks} ({prg_size//1024}KB)")
    print(f"   CHR banks: {chr_banks}")
    print(f"   Mapper: {mapper}")
    print()
    
    # Extract PRG ROM data
    prg_data = data[16:16+prg_size] if len(data) >= 16+prg_size else data[16:]
    print(f"📊 PRG ROM: {len(prg_data):,} bytes")
    
    # Search for pattern reference table patterns
    print(f"🔗 Searching for Pattern Reference Tables...")
    print()
    
    # Look for the specific sequence we expect from our test
    # Pattern refs should be mostly zeros with specific non-zero entries at frames 30, 210, 570, 930
    
    found_tables = []
    
    # Search for long sequences of pattern reference entries (3 bytes each: word + byte)
    for offset in range(0, len(prg_data) - 100, 1):
        # Check if this could be start of pattern ref table
        zero_count = 0
        non_zero_positions = []
        
        # Check up to 1000 pattern refs (3000 bytes) to find long sequences
        for i in range(0, min(1000, (len(prg_data) - offset) // 3)):
            pos = offset + i * 3
            if pos + 2 >= len(prg_data):
                break
                
            word_val = struct.unpack('<H', prg_data[pos:pos+2])[0]  # Little-endian word
            byte_val = prg_data[pos+2]
            
            if word_val == 0 and byte_val == 0:
                zero_count += 1
            else:
                non_zero_positions.append((i, word_val, byte_val))
                
            # If we have mostly zeros with some non-zero entries, this could be our table
            if i > 50 and zero_count > i * 0.95:  # 95% or more zeros
                if len(non_zero_positions) > 0:
                    found_tables.append({
                        'offset': offset,
                        'entries': i + 1,
                        'zero_count': zero_count,
                        'non_zero': non_zero_positions[:10],  # First 10 non-zero entries
                        'zero_percent': (zero_count / (i + 1)) * 100
                    })
                break
    
    # Report findings
    if found_tables:
        print(f"📍 Found {len(found_tables)} potential pattern reference tables:")
        print()
        
        for i, table in enumerate(found_tables):
            print(f"Table #{i+1}:")
            print(f"   Location: 0x{table['offset']+16:04X} (file offset 0x{table['offset']:04X})")
            print(f"   Entries: {table['entries']:,}")
            print(f"   Zero entries: {table['zero_count']:,} ({table['zero_percent']:.1f}%)")
            print(f"   Non-zero entries: {len(table['non_zero'])}")
            
            if table['non_zero']:
                print(f"   Non-zero pattern refs:")
                for frame, word, byte in table['non_zero']:
                    print(f"      Frame {frame:3d}: word=0x{word:04X}, byte=0x{byte:02X}")
            
            # Check specific frames we expect (30, 210, 570, 930)
            print(f"   Checking expected frames:")
            expected_frames = [30, 210, 570, 930]
            for frame in expected_frames:
                if frame < table['entries']:
                    pos = table['offset'] + frame * 3
                    if pos + 2 < len(prg_data):
                        word_val = struct.unpack('<H', prg_data[pos:pos+2])[0]
                        byte_val = prg_data[pos+2]
                        status = "✅" if word_val != 0 or byte_val != 0 else "❌"
                        print(f"      Frame {frame:3d}: word=0x{word_val:04X}, byte=0x{byte_val:02X} {status}")
            print()
    else:
        print("❌ No pattern reference tables found")
        print()
    
    # Search for pattern data
    print(f"🎼 Searching for Pattern Data...")
    
    # Look for the pattern_0 signature we expect: $08, $D6, $00
    pattern_signature = bytes([0x08, 0xD6, 0x00])
    pattern_positions = []
    
    for i in range(len(prg_data) - 2):
        if prg_data[i:i+3] == pattern_signature:
            pattern_positions.append(i)
    
    if pattern_positions:
        print(f"📍 Found pattern_0 signature at {len(pattern_positions)} locations:")
        for pos in pattern_positions:
            print(f"   0x{pos+16:04X} (file offset 0x{pos:04X}): {prg_data[pos:pos+3].hex()}")
    else:
        print("❌ Pattern signature not found")
    
    print()
    
    # Look for music engine code signatures
    print(f"🎵 Searching for Music Engine Code...")
    
    # Look for common 6502 instructions that might be in the music engine
    engine_signatures = [
        (b'\xa9\x0c', "LDA #$0C (MMC1 init)"),
        (b'\x8d\x00\x80', "STA $8000 (MMC1 write)"),
        (b'\x4c', "JMP instruction"),
        (b'\x20', "JSR instruction")
    ]
    
    for sig_bytes, description in engine_signatures:
        count = prg_data.count(sig_bytes)
        if count > 0:
            print(f"   Found {count} instances of {description}")
    
    print()
    print("🏁 Analysis Complete")
    return True


def analyze_pattern_refs(rom_path):
    """Legacy function name for compatibility."""
    return debug_pattern_references(rom_path)


def main():
    """CLI entry point for pattern reference debugging."""
    if len(sys.argv) != 2:
        print("Usage: python pattern_reference_debugger.py <rom_file>")
        sys.exit(1)
    
    rom_file = sys.argv[1]
    debug_pattern_references(rom_file)


if __name__ == "__main__":
    main()
