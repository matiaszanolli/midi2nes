"""
Pipeline Integration for NES Arranger.

Bridges the arranger module with the existing MIDI2NES pipeline,
providing drop-in replacements for track mapping and frame generation.
"""

from collections import Counter
from typing import Dict, List, Tuple

from .role_analyzer import VoiceRoleAnalyzer, NoteInfo, ArrangementPlan
from .voice_allocator import allocate_with_arpeggiation
from nes.pitch_table import NES_NOTE_TABLE, NES_TRIANGLE_TABLE, CHANNEL_RANGES
from core.events import event_velocity


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


def _split_events_by_channel(events: List[Dict]) -> List[Tuple[object, List[Dict]]]:
    """Split one track's events into per-channel groups, in first-seen order.

    parser_fast groups events by MIDI *track* only, never by channel, so a
    Type-0 MIDI (one track carrying all 16 channels, including channel-9
    drums) -- or any multi-channel Type-1 track -- reached role analysis as
    a single merged voice: the drum flag was sampled from only the first
    event that had a channel, and one GM program was derived via
    Counter(programs) across every mixed channel. Splitting here means
    channel-9 events become their own drum track and each pitched channel
    gets its own GM program/role instead of one skewed by the others
    (#329/ARR-NEW-5).

    Events with no channel info at all are kept in a single group keyed by
    None, so the existing name-heuristic drum fallback still applies
    unchanged for inputs that carry no channel data whatsoever.
    """
    groups: Dict[object, List[Dict]] = {}
    order: List[object] = []
    for event in events:
        channel = event.get('channel')
        if channel not in groups:
            groups[channel] = []
            order.append(channel)
        groups[channel].append(event)
    return [(channel, groups[channel]) for channel in order]


def analyze_midi_events(
    midi_events: Dict[str, List[Dict]],
    sustain: bool = True,
    sustain_gap: int = 12,  # Frames to bridge gaps (200ms at 60fps)
) -> Tuple[ArrangementPlan, Dict[int, List[NoteInfo]], int]:
    """
    Analyze MIDI events using the arranger.

    Frame numbers arrive pre-computed from parser_fast (``event['frame']``) and
    note density uses ``VoiceRoleAnalyzer.tempo_fps`` (a fixed 60.0), so this
    function does no tempo/tick/fps math itself — the former ticks_per_beat/
    tempo/fps parameters were never referenced and were dropped as misleading
    dead knobs (#360/ARR-2026-07-19-2). No caller passed them.

    Args:
        midi_events: Dict of track_name -> list of event dicts with frame, note, velocity
        sustain: If True, extend notes to fill small gaps (better for arpeggiation)
        sustain_gap: Maximum gap in frames to bridge with sustain

    Returns:
        Tuple of (ArrangementPlan, notes_by_track, total_frames)
    """
    analyzer = VoiceRoleAnalyzer()
    notes_by_track: Dict[int, List[NoteInfo]] = {}

    # Convert events to NoteInfo objects. Each (MIDI track, channel) pair
    # becomes its own analyzer track_id -- see _split_events_by_channel for
    # why (#329/ARR-NEW-5): a Type-0 MIDI or multi-channel Type-1 track must
    # not reach role analysis as one merged voice.
    track_idx = 0
    for track_name, events in midi_events.items():
        channel_groups = _split_events_by_channel(events)
        # A single group means this track carries only one channel (or no
        # channel info at all) -- the common Type-1 case -- so keep its name
        # unchanged for byte-for-byte-identical output/logging. Only a real
        # split gets a "chN" suffix, so debug/verbose output can still tell
        # the sub-tracks apart.
        multi = len(channel_groups) > 1

        for channel, ch_events in channel_groups:
            sub_track_idx = track_idx
            track_idx += 1
            sub_name = (f"{track_name} ch{channel}" if multi and channel is not None
                        else str(track_name))
            analyzer.set_track_name(sub_track_idx, sub_name)

            # Check for drum track. GM percussion lives on MIDI channel 10
            # (index 9), which parser_fast now preserves on each event
            # (#85); fall back to the track-name heuristic only when no
            # event in this group carries channel info at all -- a known,
            # non-percussion channel is authoritative and must not be
            # overridden by a name that merely happens to contain "drum"
            # (e.g. a reference/scratch track name), which used to reroute a
            # pitched track's actual content through the drum/noise path
            # (#206/ARR-11).
            if channel is not None:
                is_drum_track = channel == 9
            else:
                is_drum_track = ('drum' in str(track_name).lower()
                                  or track_name == '9' or track_name == 9)
            if is_drum_track:
                analyzer.mark_drum_track(sub_track_idx)

            # GM program hint for role/timbre analysis (#86), now computed
            # per-channel instead of across every channel this track mixed
            # together -- a drum channel's program 0 no longer skews a
            # pitched channel's representative instrument, and vice versa
            # (#329/ARR-NEW-5). Use the most frequently-occurring program in
            # this channel's own events rather than the first note's -- a
            # program_change that arrives after the first note-on (e.g. a
            # leading pickup note, common in DAW exports) would otherwise
            # misidentify the channel as program 0 (#308).
            programs = [e['program'] for e in ch_events if e.get('program') is not None]
            track_program = Counter(programs).most_common(1)[0][0] if programs else 0
            analyzer.set_track_program(sub_track_idx, track_program)

            # Group note_on and note_off events
            # note -> (start_frame, velocity, channel, program)
            active_notes: Dict[int, Tuple[int, int, int, int]] = {}
            track_notes: List[NoteInfo] = []

            for event in ch_events:
                frame = event.get('frame', 0)
                note = event.get('note', 60)
                # Default 0 (#460/TD-40, dropped from a divergent 100 at
                # migration): the default only fires when an event is
                # missing both keys entirely (malformed/synthetic), and 0
                # makes that read as a note-off/no-op like every other
                # velocity-reading site, rather than a spurious note-on.
                velocity = event_velocity(event)
                ev_channel = event.get('channel', 0) or 0
                program = event.get('program', 0) or 0

                if velocity > 0:
                    # Note on. A note-on for a pitch that's already active
                    # (legato/repeated hits, doubled unison voices -- all
                    # routine in real MIDI, and parser_fast delivers them in
                    # chronological order) used to silently overwrite the
                    # active slot: the first note never became a NoteInfo at
                    # all, and the eventual note-off closed the *second*
                    # onset, truncating it to the overlap window. Close the
                    # still-active note at this new onset instead (implicit
                    # note-off / re-trigger semantics) before re-arming the
                    # slot (#449/ARR-2026-08-21-2).
                    if note in active_notes:
                        start_frame, start_vel, start_chan, start_program = active_notes[note]
                        if frame > start_frame:
                            note_info = NoteInfo(
                                pitch=note,
                                velocity=start_vel,
                                start_frame=start_frame,
                                end_frame=frame,
                                channel=start_chan,
                                program=start_program,
                            )
                            track_notes.append(note_info)
                            analyzer.add_note(sub_track_idx, note_info)
                    active_notes[note] = (frame, velocity, ev_channel, program)
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
                        analyzer.add_note(sub_track_idx, note_info)

            # Handle notes that never got a note-off (use default duration)
            for note, (start_frame, velocity, ev_channel, start_program) in active_notes.items():
                # Estimate end frame (e.g., 15 frames = 0.25 seconds)
                note_info = NoteInfo(
                    pitch=note,
                    velocity=velocity,
                    start_frame=start_frame,
                    end_frame=start_frame + 15,
                    channel=ev_channel,
                    program=start_program,
                )
                track_notes.append(note_info)
                analyzer.add_note(sub_track_idx, note_info)

            if track_notes:
                # Apply sustain if enabled - extend notes to fill gaps
                if sustain:
                    track_notes = _apply_sustain(track_notes, sustain_gap)
                notes_by_track[sub_track_idx] = track_notes

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
    dpcm_index_path: str = "dpcm_index.json",
) -> Dict[str, Dict[int, Dict]]:
    """
    Arrange MIDI events for NES with intelligent voice allocation and arpeggiation.

    This is a drop-in replacement for the existing frame generation,
    producing output compatible with the CA65 exporter.

    Args:
        midi_events: Dict of track_name -> list of event dicts
        arp_speed: Arpeggiation speed in frames (3 = 20Hz, classic NES)
        verbose: Print arrangement analysis
        dpcm_index_path: Path to dpcm_index.json, used to resolve kick/snare
            hits to real catalog ids (#445/DPCM-2026-08-21-2)

    Returns:
        Dict with channel names as keys, each containing frame_number -> frame_data
    """
    # Analyze the MIDI
    plan, notes_by_track, total_frames = analyze_midi_events(midi_events)

    # Surface dropped tracks unconditionally, not just under --verbose: an
    # entire musical part can silently vanish from the ROM whenever more
    # than 4 pitched voices compete for NES's channels, and nothing on this
    # path used to show plan.notes/plan.dropped_tracks at all -- unlike the
    # legacy front-end's unconditional same-frame-drop warnings
    # (#451/ARR-2026-08-21-4).
    for note in plan.notes:
        print(f"Warning: {note}")

    if verbose:
        # print_analysis already covers everything the old inline block did
        # (per-track role/confidence/polyphony) plus GM instrument name,
        # pitch range, note density, channel assignments, and the dropped-
        # track/notes diagnostics above in more detail -- no reason to keep
        # a second, narrower copy of the same printout (#451).
        VoiceRoleAnalyzer.print_analysis(plan)

    # Allocate with arpeggiation
    frames = allocate_with_arpeggiation(
        notes_by_track,
        plan,
        total_frames + 60,  # Add a second of buffer
        arp_speed=arp_speed,
        dpcm_index_path=dpcm_index_path,
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
    # sample id from `note` = sample_id + 1 (note 0 is the rest sentinel) —
    # they never read a `sample` key (#84). `data['sample']` is now a raw
    # dpcm_index.json catalog id (0-1922 in the shipped index, #445/
    # DPCM-2026-08-21-2), too wide for the single-byte `note` field, so
    # remap the catalog ids this song actually references to a dense,
    # song-local 0..N-1 range before encoding -- the same convention
    # NESEmulatorCore.process_all_tracks uses (nes/emulator_core.py),
    # whose `dpcm_sample_map` side table the export/pack stage already
    # reads (#200/D-14).
    referenced_ids = sorted({data['sample'] for data in frames['dpcm'].values()})
    dense_id_of = {raw_id: i for i, raw_id in enumerate(referenced_ids)}
    if len(referenced_ids) > 255:
        print(f"Warning: {len(referenced_ids)} distinct DPCM samples "
              f"referenced, exceeding the 255-sample dense-id ceiling — "
              f"samples beyond the 255th will silently alias onto the "
              f"255th sample.")
    for frame, data in frames['dpcm'].items():
        dense_id = dense_id_of[data['sample']]
        output['dpcm'][frame] = {
            'note': min(255, dense_id + 1),
            'volume': 15,
        }
    if referenced_ids:
        output['dpcm_sample_map'] = {
            str(dense_id): raw_id for raw_id, dense_id in dense_id_of.items()
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

    Clamps to CHANNEL_RANGES[channel] before the table lookup, mirroring
    PitchProcessor.get_channel_pitch (nes/pitch_table.py) exactly. This
    matters beyond hardware range: the bytecode serializer
    (exporter/exporter_ca65.py) floors the *stream* note to the channel's
    range floor (24) and derives its macro base from `table[24]`, on the
    assumption that any out-of-range frame `pitch` was already clamped the
    same way. The legacy front-end satisfies that via get_channel_pitch; this
    function used to only clamp to the full MIDI 0-127 range and index the
    raw table, so a sub-C1 note's `pitch` (e.g. table[21]) disagreed with the
    serializer's `table[24]` base by more than the macro offset encoding can
    represent, clamping to a detuned pitch that was neither the note asked
    for nor the intended clamp target (#431/NH-HW-2026-08-21-4).

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
    min_note, max_note = CHANNEL_RANGES.get(channel, (0, 127))
    midi_note = max(min_note, min(max_note, midi_note))
    if channel == 'triangle':
        return NES_TRIANGLE_TABLE[midi_note]
    return NES_NOTE_TABLE[midi_note]
