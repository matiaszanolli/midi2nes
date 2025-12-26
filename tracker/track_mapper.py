import random
from collections import defaultdict
from dpcm_sampler.drum_engine import map_drums_to_dpcm


# Simplified initial mapping strategy
NES_CHANNELS = ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']


def group_notes_by_frame(events):
    """Group note-on events by frame, ignoring note-offs (volume/velocity = 0)."""
    grouped = defaultdict(list)
    for e in events:
        # Handle both 'volume' and 'velocity' field names for compatibility
        vel = e.get('volume', e.get('velocity', 0))
        if vel > 0:
            grouped[e['frame']].append(e['note'])
    return grouped


def apply_arpeggio_fallback(events, max_notes=3, style="default"):
    """Convert simultaneous notes into arpeggio bundles with chord detection."""
    grouped_notes = group_notes_by_frame(events)
    arpeggiated = []

    for frame, notes in sorted(grouped_notes.items()):
        if len(notes) <= 1:
            arpeggiated.append({
                "frame": frame,
                "note": notes[0],
                "velocity": 100,
                "arpeggio": False
            })
        else:
            notes = notes[:max_notes]  # Limit to max_notes
            
            # Detect chord and get appropriate pattern
            chord_info = detect_chord(notes)
            pattern_type = get_arpeggio_pattern(chord_info, style)
            pattern_notes = apply_arpeggio_pattern(notes, pattern_type)
            
            for i, note in enumerate(pattern_notes):
                arpeggiated.append({
                    "frame": frame + i,
                    "note": note,
                    "velocity": 100 - (i * 5),  # Slight velocity variation
                    "arpeggio": True,
                    "arpeggio_index": i,
                    "arpeggio_total": len(pattern_notes),
                    "chord_type": chord_info["type"] if chord_info else "unknown"
                })

    return sorted(arpeggiated, key=lambda x: x['frame'])


def apply_arpeggio_pattern(notes, pattern="up"):
    """
    Apply an arpeggio pattern to a list of notes.
    Some patterns intentionally repeat notes for musical effect.
    
    Args:
        notes: List of MIDI note numbers
        pattern: One of "up", "down", "up_down", "down_up", "random"
        
    Returns:
        List of notes in the specified pattern
    """
    if not notes:
        return []
        
    if len(notes) == 1:
        return notes
        
    PATTERNS = {
        "up": lambda notes: notes,                          # [C, E, G]
        "down": lambda notes: list(reversed(notes)),        # [G, E, C]
        "up_down": lambda notes: notes + list(reversed(notes[1:-1])),  # [C, E, G, E]
        "down_up": lambda notes: list(reversed(notes)) + notes[1:],    # [G, E, C, E, G]
        "random": lambda notes: random.sample(notes, len(notes)),  # Random order, no duplicates
    }
    
    return PATTERNS.get(pattern, PATTERNS["up"])(notes)

def detect_chord(notes):
    """Detect chord type from notes"""
    if len(notes) < 2:
        return None
        
    # Sort notes and get intervals
    sorted_notes = sorted(notes)
    intervals = [sorted_notes[i+1] - sorted_notes[i] for i in range(len(sorted_notes)-1)]
    
    # Basic chord detection
    if len(notes) == 3:
        if intervals == [4, 3]:  # Major
            return {"type": "major", "root": sorted_notes[0]}
        elif intervals == [3, 4]:  # Minor
            return {"type": "minor", "root": sorted_notes[0]}
        elif intervals == [4, 4]:  # Augmented
            return {"type": "augmented", "root": sorted_notes[0]}
        elif intervals == [3, 3]:  # Diminished
            return {"type": "diminished", "root": sorted_notes[0]}
    
    return {"type": "unknown", "root": sorted_notes[0]}


def get_arpeggio_pattern(chord_info, style="default"):
    """Get appropriate arpeggio pattern based on chord type"""
    PATTERNS = {
        "major": {
            "default": "up",
            "heroic": "up_down",
            "mysterious": "random"
        },
        "minor": {
            "default": "down",
            "heroic": "down_up",
            "mysterious": "random"
        },
        "augmented": {
            "default": "up_down",
            "mysterious": "random"
        },
        "diminished": {
            "default": "down_up",
            "mysterious": "random"
        }
    }
    
    chord_type = chord_info["type"] if chord_info else "unknown"
    return PATTERNS.get(chord_type, {}).get(style, "up")


def get_arpeggio_timing(pattern, base_frame, speed=1):
    """Calculate frame timings for arpeggio notes"""
    TIMING_PATTERNS = {
        "even": lambda i: i * speed,
        "accelerating": lambda i: i * (speed - i * 0.1),
        "decelerating": lambda i: i * (speed + i * 0.1),
        "swing": lambda i: i * speed + (0.5 if i % 2 else 0)
    }
    
    return base_frame + TIMING_PATTERNS["even"](pattern)


def split_polyphonic_track(events):
    """
    Split a single polyphonic MIDI track into multiple NES channels by pitch range.
    Returns dict with pulse1, pulse2, triangle events.
    """
    pulse1_events = []  # High notes (melody): >= 60
    pulse2_events = []  # Mid notes (harmony): 48-59
    triangle_events = []  # Low notes (bass): < 48

    for event in events:
        note = event['note']
        vel = event.get('volume', event.get('velocity', 0))

        # Skip note-off events
        if vel == 0:
            continue

        # Split by pitch range
        if note >= 60:
            pulse1_events.append(event.copy())
        elif note >= 48:
            pulse2_events.append(event.copy())
        else:
            triangle_events.append(event.copy())

    return {
        'pulse1': pulse1_events,
        'pulse2': pulse2_events,
        'triangle': triangle_events
    }


def assign_tracks_to_nes_channels(midi_events, dpcm_index_path):
    """
    midi_events: dict[channel] = list of events {frame, note, velocity}
    """
    nes_tracks = {
        'pulse1': [],
        'pulse2': [],
        'triangle': [],
        'noise': [],
        'dpcm': []
    }

    # Check if we have a single polyphonic track that needs splitting
    if len(midi_events) == 1:
        # Single track - likely polyphonic, split by pitch
        track_name, events = next(iter(midi_events.items()))
        print(f"  Detected single polyphonic track '{track_name}' with {len(events)} events")
        print(f"  Splitting by pitch range: High→Pulse1, Mid→Pulse2, Low→Triangle")

        split_tracks = split_polyphonic_track(events)
        nes_tracks['pulse1'] = split_tracks['pulse1']
        nes_tracks['pulse2'] = split_tracks['pulse2']
        nes_tracks['triangle'] = split_tracks['triangle']

        print(f"  Split result: Pulse1={len(nes_tracks['pulse1'])}, Pulse2={len(nes_tracks['pulse2'])}, Triangle={len(nes_tracks['triangle'])}")
    else:
        # Multiple tracks - use original logic
        # Basic heuristic: choose based on pitch and density
        def average_pitch(events):
            # Handle both 'volume' and 'velocity' field names for compatibility
            notes = [e['note'] for e in events if e.get('volume', e.get('velocity', 0)) > 0]
            return sum(notes) / len(notes) if notes else 0

        channel_scores = [
            (channel, average_pitch(events))
            for channel, events in midi_events.items()
        ]

        # Sort by pitch: high → low
        channel_scores.sort(key=lambda x: -x[1])

        # Assign melody to pulse1
        if channel_scores:
            ch, _ = channel_scores.pop(0)
            nes_tracks['pulse1'] = midi_events[ch]

        # Assign harmony to pulse2 with intelligent arpeggio
        if channel_scores:
            ch, _ = channel_scores.pop(0)
            nes_tracks['pulse2'] = apply_arpeggio_fallback(midi_events[ch], style="default")

        # Assign bass (lowest avg pitch) to triangle
        if channel_scores:
            ch, _ = min(channel_scores, key=lambda x: x[1])
            channel_scores.remove((ch, average_pitch(midi_events[ch])))
            nes_tracks['triangle'] = midi_events[ch]

        # Remaining: try noise + dpcm if drum-like or just fill up
        for ch, _ in channel_scores:
            if 'drum' in str(ch).lower():
                nes_tracks['noise'] = midi_events[ch]
            elif not nes_tracks['dpcm']:
                nes_tracks['dpcm'] = midi_events[ch]

    # Fallback for DPCM: look for drums
    dpcm_events, noise_events = map_drums_to_dpcm(midi_events, dpcm_index_path)

    if dpcm_events:
        nes_tracks['dpcm'] = dpcm_events

    if noise_events and not nes_tracks['noise']:
        nes_tracks['noise'] = noise_events

    return nes_tracks

if __name__ == "__main__":
    import sys, json

    if len(sys.argv) < 3:
        print("Usage: python track_mapper.py <parsed_midi.json> <dpcm_index.json>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        midi_data = json.load(f)

    dpcm_index_path = sys.argv[2]
    mapped = assign_tracks_to_nes_channels(midi_data, dpcm_index_path)

    with open("mapped.json", "w") as out:
        json.dump(mapped, out, indent=2)
