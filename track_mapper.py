from collections import defaultdict
from drum_engine import map_drums_to_dpcm

# Simplified initial mapping strategy
NES_CHANNELS = ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']

def group_notes_by_frame(events):
    """Group note-on events by frame, ignoring note-offs (velocity = 0)."""
    grouped = defaultdict(list)
    for e in events:
        if e.get('velocity', 0) > 0:
            grouped[e['frame']].append(e['note'])
    return grouped

def apply_arpeggio_fallback(events, max_notes=3, chord_window=1):
    """Convert simultaneous notes into arpeggio bundles for pulse2."""
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
            notes = notes[:max_notes]  # Limit to 3 notes
            for i, note in enumerate(notes):
                arpeggiated.append({
                    "frame": frame + i % chord_window,
                    "note": note,
                    "velocity": 100,
                    "arpeggio": True,
                    "arpeggio_index": i
                })

    return sorted(arpeggiated, key=lambda x: x['frame'])

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

    # Basic heuristic: choose based on pitch and density
    def average_pitch(events):
        notes = [e['note'] for e in events if e.get('velocity', 0) > 0]
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

    # Assign harmony to pulse2
    if channel_scores:
        ch, _ = channel_scores.pop(0)
        nes_tracks['pulse2'] = apply_arpeggio_fallback(midi_events[ch])

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

