"""
Pipeline Integration for NES Arranger.

Bridges the arranger module with the existing MIDI2NES pipeline,
providing drop-in replacements for track mapping and frame generation.
"""

from typing import Dict, List, Tuple

from .role_analyzer import VoiceRoleAnalyzer, NoteInfo, ArrangementPlan
from .voice_allocator import allocate_with_arpeggiation
from nes.pitch_table import NES_NOTE_TABLE, NES_TRIANGLE_TABLE


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
        # A close onset alone isn't enough to call two notes a chord: a fast
        # sequential monophonic run (e.g. a 32nd-note passage) also has notes
        # starting within `chord_tolerance` of each other, but they don't
        # overlap in time. Merging those manufactured false polyphony that
        # the arpeggiator then silently dropped every other note of, once
        # extended to share one end_frame (#296/ARR-NEW-4). Require actual
        # overlap with an existing chord member's *original* end_frame too
        # (strict `<`, so two notes that merely touch -- one ends exactly as
        # the next begins -- count as sequential, not simultaneous).
        starts_close = note.start_frame - current_chord[0].start_frame <= chord_tolerance
        overlaps_chord = any(note.start_frame < member.end_frame for member in current_chord)
        if starts_close and overlaps_chord:
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

        # Check for drum track. GM percussion lives on MIDI channel 10 (index 9),
        # which parser_fast now preserves on each event (#85); fall back to the
        # track-name heuristic only when no event carries channel info -- a
        # known, non-percussion channel is authoritative and must not be
        # overridden by a name that merely happens to contain "drum" (e.g. a
        # reference/scratch track name), which used to reroute a pitched
        # track's actual content through the drum/noise path (#206/ARR-11).
        track_channel = next(
            (e['channel'] for e in events if e.get('channel') is not None), None
        )
        if track_channel is not None:
            is_drum_track = track_channel == 9
        else:
            is_drum_track = ('drum' in str(track_name).lower()
                              or track_name == '9' or track_name == 9)
        if is_drum_track:
            analyzer.mark_drum_track(track_idx)

        # GM program hint for role/timbre analysis (#86): parser_fast now
        # carries each channel's active program on every note event; use the
        # first note's program as the track's representative instrument
        # (GM programs are conventionally set once per track before any notes).
        track_program = next(
            (e['program'] for e in events if e.get('program') is not None), 0
        )
        analyzer.set_track_program(track_idx, track_program)

        # Group note_on and note_off events
        # note -> (start_frame, velocity, channel, program)
        active_notes: Dict[int, Tuple[int, int, int, int]] = {}
        track_notes: List[NoteInfo] = []

        for event in events:
            frame = event.get('frame', 0)
            note = event.get('note', 60)
            velocity = event.get('velocity', event.get('volume', 100))
            channel = event.get('channel', 0) or 0
            program = event.get('program', 0) or 0

            if velocity > 0:
                # Note on
                active_notes[note] = (frame, velocity, channel, program)
            else:
                # Note off
                if note in active_notes:
                    start_frame, start_vel, start_chan, start_program = active_notes.pop(note)
                    note_info = NoteInfo(
                        pitch=note,
                        velocity=start_vel,
                        start_frame=start_frame,
                        end_frame=frame,
                        channel=start_chan,
                        program=start_program,
                    )
                    track_notes.append(note_info)
                    analyzer.add_note(track_idx, note_info)

        # Handle notes that never got a note-off (use default duration)
        for note, (start_frame, velocity, channel, start_program) in active_notes.items():
            # Estimate end frame (e.g., 15 frames = 0.25 seconds)
            note_info = NoteInfo(
                pitch=note,
                velocity=velocity,
                start_frame=start_frame,
                end_frame=start_frame + 15,
                channel=channel,
                program=start_program,
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

    # Convert noise. Match the canonical process_all_tracks contract (#9, #84):
    # the exporters read the 4-bit period from `note` (low nibble) and the mode
    # bit from `control` bit 6 — there is no `period` key. Period 0 is the
    # bytecode rest sentinel, so floor an active hit at 1; floor volume likewise
    # so a hit is never silent. Consequence: a drum curated with noise_period=0
    # (closed hi-hat) renders at period 1, one step below the top frequency it
    # asked for — accepted rather than remapping the sentinel scheme (#253).
    for frame, data in frames['noise'].items():
        period = max(1, data['period'] & 0x0F)
        volume = max(1, min(15, data['volume']))
        mode = data.get('mode', 0) & 1
        output['noise'][frame] = {
            'note': period,
            'control': mode << 6,
            'volume': volume,
        }

    # Convert DPCM. The exporters gate emission on `volume` and recover the
    # sample id from `note` = sample_id + 1 (note 0 is the rest sentinel) — they
    # never read a `sample` key (#84).
    for frame, data in frames['dpcm'].items():
        output['dpcm'][frame] = {
            'note': min(255, data['sample'] + 1),
            'volume': 15,
        }

    return output


def midi_note_to_nes_pitch(midi_note: int, channel: str) -> int:
    """
    Convert MIDI note number to NES APU timer value.

    Delegates to the canonical nes/pitch_table.py tables (#89/ARR-06) instead
    of a hand-rolled float formula, so there is a single authoritative pitch
    source shared with the exporter's midi_note_to_timer_value -- including
    the floor-8 clamp (pulse/triangle are silenced below timer 8,
    APU_PULSE_REFERENCE §3/§7), which the old formula's floor-0 clamp did not
    enforce and could violate for extreme high notes.

    Noise has no timer -- its period comes from the voice allocator's 0-15
    clamp, never from this function (#90/ARR-07); only 'pulse1'/'pulse2'/
    'triangle' are meaningful `channel` values here.

    Args:
        midi_note: MIDI note number (0-127)
        channel: 'pulse1', 'pulse2', or 'triangle'

    Returns:
        NES timer value (11-bit, floored at 8)
    """
    midi_note = max(0, min(127, midi_note))
    if channel == 'triangle':
        return NES_TRIANGLE_TABLE[midi_note]
    return NES_NOTE_TABLE[midi_note]


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
