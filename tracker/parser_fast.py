import mido
import json
from collections import defaultdict
from constants import FRAME_RATE_HZ
from tracker.tempo_map import EnhancedTempoMap, TempoValidationConfig, TempoChangeType, TempoValidationError
from core.exceptions import InvalidMIDIError


def _open_midi_file(midi_path):
    """Open a MIDI file, converting parse/IO failures to InvalidMIDIError.

    Used by `_parse_frames_and_tempo_map`, the shared implementation behind
    both `parse_midi_to_frames` and `parse_midi_to_frames_with_analysis`
    (#221/SAFE-10).
    """
    try:
        return mido.MidiFile(midi_path)
    except FileNotFoundError:
        raise  # file does not exist — not a MIDI validity issue
    except (EOFError, OSError, ValueError) as e:
        raise InvalidMIDIError(str(midi_path), str(e)) from e


def _build_tempo_map(mid, config):
    """Build a tempo map from an already-opened MIDI file's `set_tempo`
    events, counting and warning on any rejected change instead of dropping
    it silently (#94/TEMPO-02).

    Shared by `parse_midi_to_frames` and `parse_midi_to_frames_with_analysis`
    so their two tempo-collection passes (previously duplicated, one fixed
    and one not) can't drift out of sync again (#259/TEMPO-12,
    #260/TEMPO-13) -- this also fixes the analysis path never having passed
    `ticks_per_beat`, since the caller now always constructs the map here
    from the real `mid.ticks_per_beat`.
    """
    tempo_map = EnhancedTempoMap(
        initial_tempo=500000,  # 120 BPM
        ticks_per_beat=mid.ticks_per_beat,  # Use actual MIDI resolution
        validation_config=config,
        optimization_strategy=None  # Disable expensive optimization
    )

    dropped_tempo_changes = 0
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                try:
                    # Use IMMEDIATE tempo changes for speed
                    tempo_map.add_tempo_change(
                        current_tick,
                        msg.tempo,
                        TempoChangeType.IMMEDIATE
                    )
                except TempoValidationError:
                    # With the widened config this should be rare; never drop a
                    # tempo change silently (the song would play at the wrong
                    # tempo from here on) — count it and warn after the pass (#94).
                    dropped_tempo_changes += 1
                    continue

    if dropped_tempo_changes:
        print(f"Warning: dropped {dropped_tempo_changes} out-of-range tempo "
              f"change(s); affected sections will play at the preceding tempo.")

    return tempo_map


def _parse_frames_and_tempo_map(midi_path):
    """Open the MIDI file once, build its tempo map once, and parse note
    events once. Shared by `parse_midi_to_frames` and
    `parse_midi_to_frames_with_analysis` so the latter no longer re-opens the
    file and rebuilds an identical tempo map from scratch (#335/PERF-15) --
    both entry points use the same widened-band, ratio-gate-disabled
    `TempoValidationConfig` (#94), so a second build was pure redundant work,
    not a behavior difference.

    Returns (events_by_track, tempo_map).
    """
    mid = _open_midi_file(midi_path)

    # SMPTE-division MIDI (division word bit 15 set) makes mido report
    # ticks_per_beat as a negative value; zero is equally degenerate. Either
    # makes us_per_tick <= 0 and yields negative frame indices that silently
    # scramble the whole song (#93). Reject early with an actionable message
    # rather than compiling garbage. (TempoMap.__init__ also guards this, but a
    # parse-stage message points the user at the real cause.)
    if mid.ticks_per_beat is None or mid.ticks_per_beat < 1:
        raise ValueError(
            f"Unsupported MIDI timing division: ticks_per_beat="
            f"{mid.ticks_per_beat!r}. This file uses SMPTE frame/sub-frame "
            f"timing; re-export it with metrical (PPQ) timing."
        )

    # Initialize tempo map with minimal validation for performance.
    # CRITICAL: Use the MIDI file's ticks_per_beat for accurate timing.
    # The tempo range is widened to the full musically-valid band and the
    # change-ratio gate is disabled: those are authoring heuristics, not parse
    # constraints, and the narrow 40-250 BPM / ratio-3.0 limits silently dropped
    # legitimate largo/presto tempos and normal section-boundary jumps, leaving
    # the song at the wrong tempo (#94).
    config = TempoValidationConfig(
        min_tempo_bpm=1.0,
        max_tempo_bpm=2000.0,
        min_duration_frames=2,
        max_duration_frames=FRAME_RATE_HZ * 300,  # Allow up to 5 minutes
        max_tempo_change_ratio=float('inf')
    )
    tempo_map = _build_tempo_map(mid, config)

    track_events = defaultdict(list)

    # Second pass: process notes efficiently
    dropped_note_events = 0
    last_drop_reason = None
    for i, track in enumerate(mid.tracks):
        current_tick = 0
        track_name = f"track_{i}"
        # GM program is channel-scoped and can change mid-track; track each
        # channel's currently active program so it can be carried on every
        # note event for the arranger's GM role/timbre hint (#86) -- without
        # this, program is unreachable and every track defaults to Acoustic
        # Grand Piano.
        channel_programs = {}

        for msg in track:
            current_tick += msg.time

            if msg.type == 'track_name':
                track_name = msg.name.strip().replace(" ", "_")
            elif msg.type == 'program_change':
                channel_programs[msg.channel] = msg.program
            elif msg.type in ['note_on', 'note_off']:
                try:
                    # Fast frame calculation
                    frame = tempo_map.get_frame_for_tick(current_tick)
                    note = msg.note
                    velocity = msg.velocity if msg.type == 'note_on' else 0

                    # Handle note_on with velocity 0 as note_off
                    msg_type = 'note_off' if (msg.type == 'note_on' and velocity == 0) else msg.type

                    track_events[track_name].append({
                        "frame": frame,
                        "note": note,
                        "volume": velocity,
                        "type": msg_type,
                        # Retain the MIDI channel so downstream stages can detect
                        # GM percussion (channel 10 / index 9). Without it the
                        # arranger can only guess drums from the track name (#85).
                        "channel": msg.channel,
                        # GM program active on this channel at note time (#86).
                        "program": channel_programs.get(msg.channel, 0),
                        "tempo": tempo_map.get_tempo_at_tick(current_tick)
                    })
                except Exception as e:
                    # Nothing on this path is expected to raise today (frame
                    # math is pure arithmetic, tempo lookup returns a stored
                    # value) -- this is defense against a future regression,
                    # not a known failure mode. A dropped note changes the
                    # song, so it must never vanish silently; count and warn
                    # rather than swallow it (#124/SAFE-07).
                    dropped_note_events += 1
                    last_drop_reason = f"{type(e).__name__}: {e}"
                    continue

    if dropped_note_events:
        print(f"Warning: dropped {dropped_note_events} note event(s) due to "
              f"unexpected parse error(s) (last: {last_drop_reason}); "
              f"the ROM may be missing notes.")

    return dict(track_events), tempo_map


def parse_midi_to_frames(midi_path):
    """
    Fast MIDI parser that only does basic MIDI-to-frames conversion.
    Pattern detection, loop detection, and other expensive analysis
    is moved to separate pipeline steps.
    """
    events, _tempo_map = _parse_frames_and_tempo_map(midi_path)

    # Return ONLY events - no expensive pattern/loop analysis
    # Pattern detection should be done in a separate step if needed
    return {
        "events": events,
        "metadata": {}  # Empty metadata - analysis moved to separate steps
    }


def parse_midi_to_frames_with_analysis(midi_path):
    """
    Full parser that includes pattern and loop detection.
    This should only be used when analysis is specifically needed.
    """
    # Parse events and build the tempo map in one pass (#335/PERF-15) --
    # both this function and parse_midi_to_frames used an identical widened
    # tempo-validation band (#94), so re-opening the file and rebuilding a
    # second, functionally-identical tempo map was pure redundant work.
    events, tempo_map = _parse_frames_and_tempo_map(midi_path)

    # Then add expensive analysis if needed
    from tracker.pattern_detector import EnhancedPatternDetector
    from tracker.loop_manager import EnhancedLoopManager

    # Now do expensive analysis
    pattern_detector = EnhancedPatternDetector(tempo_map)
    loop_manager = EnhancedLoopManager(tempo_map)

    track_metadata = defaultdict(dict)

    for track_name, track_events in events.items():
        # Filter only note_on events for pattern detection
        note_on_events = [
            event for event in track_events
            if event['type'] == 'note_on' and event['volume'] > 0
        ]

        if note_on_events:  # Only analyze tracks with actual notes
            # Detect patterns
            pattern_data = pattern_detector.detect_patterns(note_on_events)
            
            # Detect loops based on compressed patterns
            loops = loop_manager.detect_loops(
                note_on_events, pattern_data['patterns']
            )
            
            # Generate jump table
            jump_table = loop_manager.generate_jump_table(loops)
            
            # Store metadata for this track
            track_metadata[track_name] = {
                "patterns": pattern_data['patterns'],
                "pattern_refs": pattern_data['references'],
                "compression_stats": pattern_data['stats'],
                "loops": loops,
                "jump_table": jump_table
            }
    
    # Return events with metadata
    return {
        "events": events,
        "metadata": dict(track_metadata)
    }


if __name__ == "__main__":
    import sys
    import time
    
    if len(sys.argv) < 3:
        print("Usage: python parser_fast.py <input.mid> <output.json> [--with-analysis]")
        sys.exit(1)

    midi_path = sys.argv[1]
    output_path = sys.argv[2]
    with_analysis = '--with-analysis' in sys.argv
    
    print(f"Parsing {midi_path} ({'with' if with_analysis else 'without'} analysis)...")
    
    start_time = time.time()
    
    if with_analysis:
        parsed = parse_midi_to_frames_with_analysis(midi_path)
        print("Used full parser with pattern/loop analysis")
    else:
        parsed = parse_midi_to_frames(midi_path)
        print("Used fast parser without expensive analysis")
    
    end_time = time.time()
    
    with open(output_path, 'w') as f:
        json.dump(parsed, f, indent=2)
    
    events_count = sum(len(events) for events in parsed['events'].values())
    tracks_count = len(parsed['events'])
    
    print(f"Parsing completed in {end_time - start_time:.3f} seconds")
    print(f"Results: {tracks_count} tracks, {events_count:,} events")
    print(f"Parsed MIDI saved to {output_path}")
