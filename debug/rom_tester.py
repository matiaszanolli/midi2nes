#!/usr/bin/env python3
"""
Simple ROM Tester for MIDI2NES
Tests ROM functionality and provides emulator integration
"""

import subprocess
import sys
from pathlib import Path

def test_with_nestopia(rom_path: str):
    """Test ROM with Nestopia emulator"""
    rom_file = Path(rom_path)
    if not rom_file.exists():
        print(f"❌ ROM file not found: {rom_path}")
        return False
    
    print(f"🎮 Testing ROM with Nestopia: {rom_file.name}")
    
    try:
        # Try to launch Nestopia with the ROM
        result = subprocess.run([
            'open', '-a', 'Nestopia', rom_path
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ ROM launched successfully in Nestopia!")
            print("   Check the emulator window to verify audio playback")
            return True
        else:
            print(f"❌ Failed to launch Nestopia: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("✅ ROM launched (timeout reached, emulator probably started)")
        return True
    except FileNotFoundError:
        print("❌ Nestopia not found. Install with: brew install nestopia")
        return False
    except Exception as e:
        print(f"❌ Error launching emulator: {e}")
        return False

def generate_test_summary(rom_path: str) -> str:
    """Generate test summary for ROM"""
    rom_file = Path(rom_path)
    size = rom_file.stat().st_size if rom_file.exists() else 0
    
    summary = []
    summary.append("=" * 60)
    summary.append("🧪 ROM TEST SUMMARY")
    summary.append("=" * 60)
    summary.append(f"📁 ROM: {rom_file.name}")
    summary.append(f"📊 Size: {size:,} bytes")
    
    # Check expected size
    expected_size = 32784  # 16-byte header + 32KB PRG
    size_ok = size == expected_size
    summary.append(f"📏 Size check: {'✅' if size_ok else '❌'} (expected {expected_size:,})")
    
    # Check file extension
    ext_ok = rom_file.suffix.lower() == '.nes'
    summary.append(f"📎 Extension: {'✅' if ext_ok else '❌'} (.nes)")
    
    # Basic header validation
    header_ok = False
    if rom_file.exists():
        try:
            header = rom_file.read_bytes()[:4]
            header_ok = header == b'NES\x1a'
        except:
            pass
    summary.append(f"📋 Header: {'✅' if header_ok else '❌'} (iNES)")
    
    summary.append("")
    summary.append("🎯 RECOMMENDED TESTS:")
    summary.append("   1. Run: python debug/nes_devtools.py <rom_file>")
    summary.append("   2. Test in emulator: Nestopia, FCEUX, or Mesen")
    summary.append("   3. Verify audio output")
    summary.append("   4. Check timing accuracy")
    summary.append("")
    summary.append("=" * 60)
    
    return "\\n".join(summary)

def main():
    if len(sys.argv) < 2:
        print("Usage: python rom_tester.py <rom_file> [test_type]")
        print("Test types: nestopia, summary, all")
        sys.exit(1)
    
    rom_path = sys.argv[1]
    test_type = sys.argv[2] if len(sys.argv) > 2 else "summary"
    
    if test_type in ["nestopia", "all"]:
        test_with_nestopia(rom_path)
        print()
    
    if test_type in ["summary", "all"]:
        print(generate_test_summary(rom_path))

if __name__ == '__main__':
    main()
