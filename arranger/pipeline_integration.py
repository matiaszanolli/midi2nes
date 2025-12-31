"""
Pipeline Integration for NES Arranger.

Bridges the arranger module with the existing MIDI2NES pipeline,
providing drop-in replacements for track mapping and frame generation.
"""

from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from .gm_instruments import get_instrument_mapping, get_drum_mapping, NESChannel
from .role_analyzer import VoiceRoleAnalyzer, NoteInfo, ArrangementPlan
from .voice_allocator import (
    FrameByFrameAllocator,
    VoiceAllocator,
    allocate_with_arpeggiation,
    ArpStyle,
)


def _apply_sustain(notes: List[NoteInfo], max_gap: int) -> List[NoteInfo]:
    """
    Extend notes to fill small gaps for smoother arpeggiation.

    This helps with MIDI files that have staccato chords by extending
    each note to connect with the next occurrence of the same pitch,
    or to match the longest note in a chord.
    """
    if not notes:
        return notes

    # Sort by start frame, then pitch
    notes = sorted(notes, key=lambda n: (n.start_frame, n.pitch))

    # Group notes by approximate start time (within 2 frames = same chord)
    chord_tolerance = 2
    chords = []
    current_chord = [notes[0]]

    for note in notes[1:]:
        if note.start_frame - current_chord[0].start_frame <= chord_tolerance:
            current_chord.append(note)
        else:
            chords.append(current_chord)
            current_chord = [note]
    chords.append(current_chord)

    # For each chord, extend all notes to the end of the longest note
    # Also bridge gaps between consecutive chords
    extended_notes = []

    for i, chord in enumerate(chords):
        # Find the longest note in this chord
        max_end = max(n.end_frame for n in chord)

        # Check if next chord starts within gap threshold
        if i + 1 < len(chords):
            next_start = min(n.start_frame for n in chords[i + 1])
            gap = next_start - max_end
            if 0 < gap <= max_gap:
                # Extend to bridge the gap
                max_end = next_start

        # Create extended notes
        for note in chord:
            extended_notes.append(NoteInfo(
                pitch=note.pitch,
                velocity=note.velocity,
                start_frame=note.start_frame,
                end_frame=max_end,
                channel=note.channel,
                program=note.program,
            ))

    return extended_notes


def analyze_midi_events(
    midi_events: Dict[str, List[Dict]],
    ticks_per_beat: int = 480,
    tempo: int = 500000,  # microseconds per beat (120 BPM default)
    fps: int = 60,
    sustain: bool = True,
    sustain_gap: int = 12,  # Frames to bridge gaps (200ms at 60fps)
) -> Tuple[ArrangementPlan, Dict[int, List[NoteInfo]], int]:
    """
    Analyze MIDI events using the arranger.

    Args:
        midi_events: Dict of track_name -> list of event dicts with frame, note, velocity
        ticks_per_beat: MIDI ticks per beat
        tempo: Microseconds per beat
        fps: Frames per second
        sustain: If True, extend notes to fill small gaps (better for arpeggiation)
        sustain_gap: Maximum gap in frames to bridge with sustain

    Returns:
        Tuple of (ArrangementPlan, notes_by_track, total_frames)
    """
    analyzer = VoiceRoleAnalyzer()
    notes_by_track: Dict[int, List[NoteInfo]] = {}

    # Convert events to NoteInfo objects
    for track_idx, (track_name, events) in enumerate(midi_events.items()):
        analyzer.set_track_name(track_idx, str(track_name))

        # Check for drum track
        if 'drum' in str(track_name).lower() or track_name == '9' or track_name == 9:
            analyzer.mark_drum_track(track_idx)

        # Group note_on and note_off events
        active_notes: Dict[int, Tuple[int, int]] = {}  # note -> (start_frame, velocity)
        track_notes: List[NoteInfo] = []
        program = 0

        for event in events:
            frame = event.get('frame', 0)
            note = event.get('note', 60)
            velocity = event.get('velocity', event.get('volume', 100))

            if velocity > 0:
                # Note on
                active_notes[note] = (frame, velocity)
            else:
                # Note off
                if note in active_notes:
                    start_frame, start_vel = active_notes.pop(note)
                    note_info = NoteInfo(
                        pitch=note,
                        velocity=start_vel,
                        start_frame=start_frame,
                        end_frame=frame,
                        program=program,
                    )
                    track_notes.append(note_info)
                    analyzer.add_note(track_idx, note_info)

        # Handle notes that never got a note-off (use default duration)
        for note, (start_frame, velocity) in active_notes.items():
            # Estimate end frame (e.g., 15 frames = 0.25 seconds)
            note_info = NoteInfo(
                pitch=note,
                velocity=velocity,
                start_frame=start_frame,
                end_frame=start_frame + 15,
                program=program,
            )
            track_notes.append(note_info)
            analyzer.add_note(track_idx, note_info)

        if track_notes:
            # Apply sustain if enabled - extend notes to fill gaps
            if sustain:
                track_notes = _apply_sustain(track_notes, sustain_gap)
            notes_by_track[track_idx] = track_notes

    # Get arrangement plan
    plan = analyzer.create_arrangement_plan()

    # Calculate total frames
    total_frames = 0
    for notes in notes_by_track.values():
        for note in notes:
            total_frames = max(total_frames, note.end_frame)

    return plan, notes_by_track, total_frames


def arrange_for_nes(
    midi_events: Dict[str, List[Dict]],
    arp_speed: int = 3,
    verbose: bool = False,
) -> Dict[str, Dict[int, Dict]]:
    """
    Arrange MIDI events for NES with intelligent voice allocation and arpeggiation.

    This is a drop-in replacement for the existing frame generation,
    producing output compatible with the CA65 exporter.

    Args:
        midi_events: Dict of track_name -> list of event dicts
        arp_speed: Arpeggiation speed in frames (3 = 20Hz, classic NES)
        verbose: Print arrangement analysis

    Returns:
        Dict with channel names as keys, each containing frame_number -> frame_data
    """
    # Analyze the MIDI
    plan, notes_by_track, total_frames = analyze_midi_events(midi_events)

    if verbose:
        # Print arrangement analysis
        print("\n" + "=" * 60)
        print("NES ARRANGEMENT ANALYSIS")
        print("=" * 60)
        for track in plan.tracks:
            print(f"\nTrack {track.track_id}: {track.name}")
            print(f"  Role: {track.role.name} (confidence: {track.confidence:.0%})")
            print(f"  Max Polyphony: {track.max_polyphony}")
            if track.needs_arpeggiation:
                print(f"  → Will arpeggiate at {60 // arp_speed}Hz")
        print("=" * 60)

    # Allocate with arpeggiation
    frames = allocate_with_arpeggiation(
        notes_by_track,
        plan,
        total_frames + 60,  # Add a second of buffer
        arp_speed=arp_speed,
    )

    # Convert to format expected by existing pipeline
    # The existing format uses 'pitch' not 'note', and needs additional fields
    output = {
        'pulse1': {},
        'pulse2': {},
        'triangle': {},
        'noise': {},
        'dpcm': {},
    }

    # Convert pulse channels
    for channel in ['pulse1', 'pulse2']:
        for frame, data in frames[channel].items():
            output[channel][frame] = {
                'note': data['note'],
                'pitch': midi_note_to_nes_pitch(data['note'], channel),
                'volume': data['volume'],
                'control': (data.get('duty', 2) << 6) | 0x30 | data['volume'],
            }

    # Convert triangle
    for frame, data in frames['triangle'].items():
        output['triangle'][frame] = {
            'note': data['note'],
            'pitch': midi_note_to_nes_pitch(data['note'], 'triangle'),
            'volume': data['volume'],
            'control': 0x81,  # Triangle linear counter
        }

    # Convert noise
    for frame, data in frames['noise'].items():
        output['noise'][frame] = {
            'period': data['period'],
            'volume': data['volume'],
            'control': 0x30 | data['volume'],
        }

    # DPCM (simplified)
    for frame, data in frames['dpcm'].items():
        output['dpcm'][frame] = {
            'sample': data['sample'],
        }

    return output


def midi_note_to_nes_pitch(midi_note: int, channel: str) -> int:
    """
    Convert MIDI note number to NES APU timer value.

    Args:
        midi_note: MIDI note number (0-127)
        channel: 'pulse1', 'pulse2', 'triangle', or 'noise'

    Returns:
        NES timer value (11-bit for pulse/triangle)
    """
    # NES CPU clock (NTSC)
    CPU_CLOCK = 1789773

    # MIDI note to frequency
    # A4 (MIDI 69) = 440 Hz
    frequency = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

    if frequency <= 0:
        return 0

    if channel in ['pulse1', 'pulse2']:
        # Pulse period = CPU / (16 * frequency) - 1
        period = int(CPU_CLOCK / (16 * frequency) - 1)
    elif channel == 'triangle':
        # Triangle period = CPU / (32 * frequency) - 1
        period = int(CPU_CLOCK / (32 * frequency) - 1)
    else:
        # Noise - use direct period
        return midi_note

    # Clamp to valid range
    return max(0, min(2047, period))


def enhanced_track_mapper(
    midi_events: Dict[str, List[Dict]],
    dpcm_index_path: str = '',
    arp_speed: int = 3,
    verbose: bool = False,
) -> Dict[str, List[Dict]]:
    """
    Enhanced track mapper using the arranger.

    Compatible with existing pipeline but with smarter allocation.

    Returns events in the original format for compatibility.
    """
    frames = arrange_for_nes(midi_events, arp_speed=arp_speed, verbose=verbose)

    # Convert back to event list format
    output = {}
    for channel in ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']:
        events = []
        for frame, data in sorted(frames[channel].items()):
            event = {'frame': frame}
            event.update(data)
            events.append(event)
        output[channel] = events

    return output
