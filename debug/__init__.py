"""
Debug tools and utilities for MIDI2NES development and troubleshooting.

This module contains various debugging, analysis, and diagnostic tools used
during development and for troubleshooting issues in the MIDI2NES pipeline.
"""

__version__ = "1.0.0"

# Import commonly used debug utilities
try:
    from .pattern_analysis import analyze_patterns
    from .ca65_inspector import inspect_ca65_output
    from .frame_analyzer import analyze_frames
    from .music_structure_analyzer import analyze_music_structure
    from .pattern_reference_debugger import debug_pattern_references
    from .performance_analyzer import analyze_performance
    from .audio_checker import check_audio_simple
    from .rom_tester import test_rom_generation
except ImportError:
    # Graceful fallback if some dependencies are missing
    pass

__all__ = [
    'analyze_patterns',
    'inspect_ca65_output', 
    'analyze_frames',
    'analyze_music_structure',
    'debug_pattern_references',
    'analyze_performance',
    'check_audio_simple',
    'test_rom_generation'
]
