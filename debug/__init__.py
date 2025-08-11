"""
MIDI2NES Debug Tools
==================

Comprehensive ROM diagnostics and validation tools for MIDI2NES generated ROMs.

This module provides:
- ROM health checking and corruption detection
- Header validation and size checking
- APU code pattern analysis
- Assembly code analysis
- Reset vector validation
- Actionable recommendations for fixes

Main Tools:
- rom_diagnostics.py: Comprehensive ROM analysis
- check_rom.py: Quick health checking

Usage:
    from debug.rom_diagnostics import ROMDiagnostics
    
    diagnostics = ROMDiagnostics(verbose=True)
    result = diagnostics.diagnose_rom("example.nes")
    diagnostics.print_report(result)
"""

__version__ = "2.0.0"
__author__ = "MIDI2NES Team"

# Make key classes available at package level
try:
    from .rom_diagnostics import ROMDiagnostics, ROMDiagnosticResult
    __all__ = ['ROMDiagnostics', 'ROMDiagnosticResult']
except ImportError:
    # Handle case where dependencies might not be available
    __all__ = []

# Convenience function for quick checking
def quick_check_rom(rom_path: str, verbose: bool = False) -> bool:
    """
    Quick ROM health check that returns True if ROM is healthy/good.
    
    Args:
        rom_path: Path to ROM file
        verbose: Enable verbose output
        
    Returns:
        bool: True if ROM is healthy/good, False otherwise
    """
    try:
        diagnostics = ROMDiagnostics(verbose=verbose)
        result = diagnostics.diagnose_rom(rom_path)
        return result.overall_health in ['HEALTHY', 'GOOD']
    except Exception:
        return False
