#!/usr/bin/env python3
"""
Simple ROM Health Checker
=========================

Quick and easy ROM validation for MIDI2NES generated files.
This is a simplified interface to the comprehensive rom_diagnostics tool.

Usage:
    python debug/check_rom.py [ROM_FILE]
    
Examples:
    python debug/check_rom.py corrected.nes
    python debug/check_rom.py input.nes
"""

import sys
import os

# Add the debug directory to the path so we can import rom_diagnostics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rom_diagnostics import ROMDiagnostics


def quick_check(rom_path: str) -> bool:
    """Perform a quick ROM health check with simplified output."""
    diagnostics = ROMDiagnostics(verbose=False)
    result = diagnostics.diagnose_rom(rom_path)
    
    # Quick status indicator
    if result.overall_health == "ERROR":
        print(f"❌ {rom_path}: {result.issues[0]}")
        return False
    
    health_icons = {
        "HEALTHY": "🟢",
        "GOOD": "🟡",
        "FAIR": "🟠", 
        "POOR": "🔴"
    }
    
    icon = health_icons.get(result.overall_health, "❓")
    print(f"{icon} {rom_path}: {result.overall_health}")
    
    # Show key stats
    print(f"   📊 {result.file_size:,} bytes ({result.prg_banks} PRG banks)")
    
    # Show critical issues only
    critical_issues = [
        issue for issue in result.issues 
        if any(keyword in issue.lower() for keyword in ['invalid', 'excessive', 'no apu', 'corrupted'])
    ]
    
    if critical_issues:
        print(f"   ⚠️  Critical: {critical_issues[0]}")
    
    # Show quick recommendations for poor ROMs
    if result.overall_health in ["POOR", "FAIR"] and result.recommendations:
        print(f"   💡 Tip: {result.recommendations[0]}")
    
    print()
    return result.overall_health in ["HEALTHY", "GOOD"]


def main():
    """Main entry point for quick ROM checking."""
    if len(sys.argv) < 2:
        print("Usage: python debug/check_rom.py [ROM_FILE]")
        print("Example: python debug/check_rom.py corrected.nes")
        sys.exit(1)
    
    rom_file = sys.argv[1]
    
    print("🔍 Quick ROM Health Check")
    print("=" * 40)
    
    success = quick_check(rom_file)
    
    if not success:
        print("💡 For detailed analysis, run:")
        print(f"   python debug/rom_diagnostics.py {rom_file} --verbose")
        sys.exit(1)
    else:
        print("✅ ROM appears healthy!")
        sys.exit(0)


if __name__ == "__main__":
    main()
