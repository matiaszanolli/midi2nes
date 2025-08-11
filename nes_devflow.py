#!/usr/bin/env python3
"""
NES Development Workflow for MIDI2NES
Integrated development and testing pipeline
"""

import subprocess
import sys
import argparse
from pathlib import Path

def run_analysis(rom_path: str):
    """Run comprehensive ROM analysis"""
    print("🔍 Running comprehensive ROM analysis...")
    result = subprocess.run([
        sys.executable, 'debug/nes_devtools.py', rom_path
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(result.stdout)
        return True
    else:
        print(f"❌ Analysis failed: {result.stderr}")
        return False

def run_diagnostic(rom_path: str):
    """Run basic ROM diagnostic"""
    print("🏥 Running basic ROM diagnostic...")
    result = subprocess.run([
        sys.executable, 'debug/rom_diagnostics.py', rom_path
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(result.stdout)
        return True
    else:
        print(f"❌ Diagnostic failed: {result.stderr}")
        return False

def test_emulator(rom_path: str, emulator: str = "nestopia"):
    """Test ROM in emulator"""
    print(f"🎮 Testing ROM in {emulator.title()}...")
    
    if emulator.lower() == "nestopia":
        try:
            subprocess.run(['open', '-a', 'Nestopia', rom_path], timeout=5)
            print("✅ ROM launched in Nestopia!")
            return True
        except subprocess.TimeoutExpired:
            print("✅ ROM launched in Nestopia (emulator started)")
            return True
        except Exception as e:
            print(f"❌ Failed to launch Nestopia: {e}")
            return False
    else:
        print(f"❌ Unsupported emulator: {emulator}")
        return False

def hex_dump_analysis(rom_path: str, offset: int = 16, length: int = 64):
    """Show hex dump of ROM for manual analysis"""
    print(f"🔢 Hex dump analysis (offset: {offset}, length: {length})...")
    
    try:
        # Use Python to do hex dump for cross-platform compatibility
        with open(rom_path, 'rb') as f:
            f.seek(offset)
            data = f.read(length)
            
        # Format as hex dump
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            addr = f"{offset + i:08x}"
            hex_part = ' '.join(f"{b:02x}" for b in chunk).ljust(47)
            ascii_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
            lines.append(f"{addr}  {hex_part}  |{ascii_part}|")
        
        print('\n'.join(lines))
        return True
        
    except Exception as e:
        print(f"❌ Hex dump failed: {e}")
        return False

def validate_build_tools():
    """Validate that NES build tools are available"""
    tools_status = {}
    
    # Check CA65/LD65
    for tool in ['ca65', 'ld65']:
        try:
            result = subprocess.run([tool, '--version'], capture_output=True, text=True)
            tools_status[tool] = result.returncode == 0
        except FileNotFoundError:
            tools_status[tool] = False
    
    # Check emulators
    emulators = ['nestopia']
    for emu in emulators:
        try:
            result = subprocess.run(['which', emu], capture_output=True, text=True)
            if result.returncode != 0:
                # Try macOS app
                result = subprocess.run(['ls', f'/Applications/{emu.title()}.app'], 
                                      capture_output=True, text=True)
            tools_status[emu] = result.returncode == 0
        except:
            tools_status[emu] = False
    
    print("🔧 NES Development Tools Status:")
    print("-" * 40)
    for tool, available in tools_status.items():
        status = "✅" if available else "❌"
        print(f"   {tool}: {status}")
    
    return all(tools_status.values())

def development_recommendations(rom_path: str):
    """Provide development recommendations"""
    rom_file = Path(rom_path)
    size = rom_file.stat().st_size if rom_file.exists() else 0
    
    print("💡 DEVELOPMENT RECOMMENDATIONS")
    print("-" * 50)
    
    # Size recommendations
    if size == 32784:
        print("✅ ROM size is perfect (32,784 bytes)")
    else:
        print(f"⚠️  ROM size {size:,} bytes (expected 32,784)")
        if size < 32784:
            print("   → ROM may be missing data or have linker issues")
        else:
            print("   → ROM may have extra data or padding issues")
    
    # MMC1 recommendations
    print("🔧 MMC1 Configuration:")
    print("   → Ensure control register uses $0A for 32KB PRG mode")
    print("   → Check that reset sequence uses $80 then $0A")
    print("   → Verify vectors are at $FFFA-$FFFF")
    
    # Audio recommendations  
    print("🎵 Audio Development:")
    print("   → Test NMI timing (should be 60Hz)")
    print("   → Verify APU register writes ($4000-$4017)")
    print("   → Check frame counter configuration ($4017)")
    print("   → Test in multiple emulators for compatibility")
    
    # Testing recommendations
    print("🧪 Testing Workflow:")
    print("   1. python nes_devflow.py <rom> --analyze")
    print("   2. python nes_devflow.py <rom> --test-emulator")
    print("   3. Listen for audio output and timing")
    print("   4. Compare against reference ROM if available")

def main():
    parser = argparse.ArgumentParser(description="NES Development Workflow for MIDI2NES")
    parser.add_argument("rom", help="Path to NES ROM file")
    parser.add_argument("--analyze", "-a", action="store_true", 
                       help="Run comprehensive ROM analysis")
    parser.add_argument("--diagnostic", "-d", action="store_true",
                       help="Run basic ROM diagnostic")  
    parser.add_argument("--test-emulator", "-e", metavar="EMULATOR", 
                       nargs='?', const="nestopia",
                       help="Test ROM in emulator (default: nestopia)")
    parser.add_argument("--hex-dump", "-x", action="store_true",
                       help="Show hex dump of ROM start")
    parser.add_argument("--validate-tools", "-v", action="store_true",
                       help="Validate development tools installation")
    parser.add_argument("--recommendations", "-r", action="store_true",
                       help="Show development recommendations")
    parser.add_argument("--all", action="store_true",
                       help="Run all available tests and analysis")
    
    args = parser.parse_args()
    
    if not Path(args.rom).exists() and not args.validate_tools:
        print(f"❌ ROM file not found: {args.rom}")
        sys.exit(1)
    
    print("=" * 70)
    print("🛠️  NES DEVELOPMENT WORKFLOW - MIDI2NES")
    print("=" * 70)
    
    success = True
    
    if args.validate_tools or args.all:
        success &= validate_build_tools()
        print()
    
    if args.diagnostic or args.all:
        success &= run_diagnostic(args.rom)
        print()
    
    if args.analyze or args.all:
        success &= run_analysis(args.rom)
        print()
    
    if args.hex_dump or args.all:
        success &= hex_dump_analysis(args.rom)
        print()
    
    if args.test_emulator or args.all:
        emulator = args.test_emulator if isinstance(args.test_emulator, str) else "nestopia"
        success &= test_emulator(args.rom, emulator)
        print()
    
    if args.recommendations or args.all:
        development_recommendations(args.rom)
        print()
    
    # Default: run basic analysis if no specific options
    if not any([args.analyze, args.diagnostic, args.test_emulator, 
               args.hex_dump, args.validate_tools, args.recommendations, args.all]):
        success &= run_analysis(args.rom)
    
    print("=" * 70)
    print(f"🎯 Overall Status: {'✅ SUCCESS' if success else '❌ ISSUES FOUND'}")
    print("=" * 70)
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
