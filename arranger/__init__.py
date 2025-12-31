"""
NES Arranger Module for MIDI2NES.

Provides intelligent MIDI-to-NES arrangement including:
- GM instrument mapping to NES capabilities
- Voice role detection (bass, melody, harmony, etc.)
- Smart channel allocation
- Arpeggiation detection for polyphonic content

Usage:
    from arranger import VoiceRoleAnalyzer, get_instrument_mapping

    # Analyze MIDI tracks
    analyzer = VoiceRoleAnalyzer()
    for note in midi_notes:
        analyzer.add_note(track_id, NoteInfo(...))
    analyzer.set_track_program(track_id, gm_program)

    # Get arrangement plan
    plan = analyzer.create_arrangement_plan()
    analyzer.print_analysis(plan)
"""

from .gm_instruments import (
    # Enums
    MusicalRole,
    NESChannel,
    PlayStyle,
    DutyCycle,
    # Data classes
    InstrumentMapping,
    DrumMapping,
    # Functions
    get_instrument_mapping,
    get_drum_mapping,
    get_role_priority,
    # Maps
    GM_INSTRUMENT_MAP,
    GM_DRUM_MAP,
)

from .role_analyzer import (
    NoteInfo,
    TrackAnalysis,
    ArrangementPlan,
    VoiceRoleAnalyzer,
)

from .voice_allocator import (
    ChannelState,
    FrameAllocation,
    ArpStyle,
    VoiceAllocator,
    FrameByFrameAllocator,
    allocate_with_arpeggiation,
)

from .pipeline_integration import (
    analyze_midi_events,
    arrange_for_nes,
    midi_note_to_nes_pitch,
    enhanced_track_mapper,
)

__all__ = [
    # Enums
    "MusicalRole",
    "NESChannel",
    "PlayStyle",
    "DutyCycle",
    # Data classes
    "InstrumentMapping",
    "DrumMapping",
    "NoteInfo",
    "TrackAnalysis",
    "ArrangementPlan",
    # Main analyzer
    "VoiceRoleAnalyzer",
    # Functions
    "get_instrument_mapping",
    "get_drum_mapping",
    "get_role_priority",
    # Maps
    "GM_INSTRUMENT_MAP",
    "GM_DRUM_MAP",
    # Voice allocator
    "ChannelState",
    "FrameAllocation",
    "ArpStyle",
    "VoiceAllocator",
    "FrameByFrameAllocator",
    "allocate_with_arpeggiation",
    # Pipeline integration
    "analyze_midi_events",
    "arrange_for_nes",
    "midi_note_to_nes_pitch",
    "enhanced_track_mapper",
]
