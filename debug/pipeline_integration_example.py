#!/usr/bin/env python3
"""
MIDI2NES Pipeline Integration Example
====================================

This script demonstrates how to integrate ROM validation into your MIDI2NES
build pipeline for automated quality assurance.

Usage:
    python debug/pipeline_integration_example.py input.mid output.nes
"""

import sys
import os
import subprocess
from pathlib import Path

# Add debug directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from rom_diagnostics import ROMDiagnostics


def run_midi2nes_with_validation(midi_file: str, output_rom: str, verbose: bool = False) -> bool:
    """
    Run the MIDI2NES pipeline with integrated ROM validation.
    
    Args:
        midi_file: Path to input MIDI file
        output_rom: Path for output ROM file
        verbose: Enable verbose validation output
        
    Returns:
        bool: True if pipeline succeeded and ROM is healthy
    """
    
    print(f"🎵 MIDI2NES Pipeline with Validation")
    print("=" * 50)
    
    # Step 1: Run MIDI2NES conversion
    print(f"📁 Input MIDI: {midi_file}")
    print(f"📁 Output ROM: {output_rom}")
    print(f"⚙️  Running MIDI2NES conversion...")
    
    try:
        # Run the main MIDI2NES pipeline
        result = subprocess.run([
            sys.executable, 'main.py', midi_file, output_rom
        ], capture_output=True, text=True, check=True)
        
        print("✅ MIDI2NES conversion completed")
        if verbose:
            print("   Conversion output:", result.stdout.split('\n')[-2] if result.stdout else "No output")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ MIDI2NES conversion failed: {e}")
        if verbose:
            print(f"   Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ MIDI2NES main.py not found. Run from project root directory.")
        return False
    
    # Step 2: Validate generated ROM
    print(f"🔍 Validating generated ROM...")
    
    if not os.path.exists(output_rom):
        print(f"❌ Output ROM file not found: {output_rom}")
        return False
    
    # Perform ROM validation
    diagnostics = ROMDiagnostics(verbose=False)  # Keep validation quiet for pipeline
    result = diagnostics.diagnose_rom(output_rom)
    
    # Report validation results
    health_icons = {
        "HEALTHY": "🟢",
        "GOOD": "🟡",
        "FAIR": "🟠",
        "POOR": "🔴",
        "ERROR": "❌"
    }
    
    icon = health_icons.get(result.overall_health, "❓")
    print(f"{icon} ROM Health: {result.overall_health}")
    print(f"   📊 Size: {result.file_size:,} bytes ({result.prg_banks} PRG banks)")
    
    # Show critical issues
    if result.issues:
        critical_issues = [
            issue for issue in result.issues 
            if any(keyword in issue.lower() for keyword in ['invalid', 'excessive', 'corrupted'])
        ]
        
        if critical_issues:
            print(f"   ⚠️  Critical Issues: {len(critical_issues)}")
            for issue in critical_issues[:2]:  # Show first 2 critical issues
                print(f"      • {issue}")
        
        if len(result.issues) > len(critical_issues):
            print(f"   ℹ️  Minor Issues: {len(result.issues) - len(critical_issues)}")
    
    # Determine pipeline success
    success = result.overall_health in ['HEALTHY', 'GOOD']
    
    if success:
        print("✅ Pipeline completed successfully!")
        if verbose and result.recommendations:
            print("💡 Optional improvements:")
            for rec in result.recommendations[:2]:
                print(f"   • {rec}")
    else:
        print("❌ Pipeline completed with issues.")
        print("💡 Recommendations:")
        for rec in result.recommendations[:3]:
            print(f"   • {rec}")
        
        if verbose:
            print(f"\n🔍 For detailed analysis, run:")
            print(f"   python debug/rom_diagnostics.py {output_rom} --verbose")
    
    print("=" * 50)
    return success


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 3:
        print("Usage: python debug/pipeline_integration_example.py input.mid output.nes [--verbose]")
        print("Example: python debug/pipeline_integration_example.py song.mid song.nes")
        sys.exit(1)
    
    midi_file = sys.argv[1]
    output_rom = sys.argv[2]
    verbose = '--verbose' in sys.argv
    
    # Check input file exists
    if not os.path.exists(midi_file):
        print(f"❌ Input MIDI file not found: {midi_file}")
        sys.exit(1)
    
    # Run pipeline with validation
    success = run_midi2nes_with_validation(midi_file, output_rom, verbose)
    
    # Exit with appropriate code for CI/CD
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
