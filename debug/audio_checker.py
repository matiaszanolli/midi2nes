#!/usr/bin/env python3
"""Simple audio pattern checking utilities for NES ROMs."""

import sys


def check_audio_simple(rom_path):
    """Quick check for APU-related values in NES ROM."""
    try:
        with open(rom_path, 'rb') as f:
            rom_data = f.read()
        
        print(f"🎵 Simple Audio Check: {rom_path}")
        print("=" * 50)
        print(f"ROM size: {len(rom_data):,} bytes")
        
        # Look for specific APU initialization patterns
        patterns_to_find = [
            (b'\xA9\x0F\x8D\x15\x40', "APU Enable ($0F -> $4015)"),
            (b'\xA9\xBF\x8D\x00\x40', "Pulse1 Init ($BF -> $4000) - GOOD"),
            (b'\xA9\x30\x8D\x00\x40', "Pulse1 Init ($30 -> $4000) - BAD"),
            (b'\xA9\xBF\x8D\x04\x40', "Pulse2 Init ($BF -> $4004) - GOOD"),  
            (b'\xA9\x30\x8D\x04\x40', "Pulse2 Init ($30 -> $4004) - BAD"),
            (b'\xA9\x08', "Volume 8 data"),
        ]
        
        found_any = False
        for pattern, description in patterns_to_find:
            count = rom_data.count(pattern)
            if count > 0:
                found_any = True
                status = "✅" if "GOOD" in description or "APU Enable" in description or "Volume" in description else ("❌" if "BAD" in description else "ℹ️")
                print(f"{status} {description}: {count} occurrences")
        
        if not found_any:
            print("⚠️  No APU patterns found")
            
        # Check for volume data patterns
        volume_8_count = rom_data.count(b'\x08')
        print(f"ℹ️  Byte $08 (volume 8): {volume_8_count} occurrences")
        
        return found_any
        
    except FileNotFoundError:
        print(f"❌ ROM file not found: {rom_path}")
        return False
    except Exception as e:
        print(f"❌ Error reading ROM: {e}")
        return False


def check_audio_in_rom(rom_path):
    """Legacy function name for compatibility."""
    return check_audio_simple(rom_path)


def main():
    """CLI entry point for audio checking."""
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "simple_loop.nes"
    check_audio_simple(rom_path)


if __name__ == "__main__":
    main()
