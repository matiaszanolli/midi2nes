import json

# Default MIDI drum note mapping
DEFAULT_MIDI_DRUM_MAPPING = {
    36: "kick",
    38: "snare",
    40: "snare",
    42: "hihat_closed",
    46: "hihat_open",
    49: "crash",
    51: "ride"
}

def map_drums_to_dpcm(midi_events, dpcm_index_path):
    with open(dpcm_index_path, 'r') as f:
        sample_index = json.load(f)

    dpcm_events = []
    noise_events = []

    for ch, events in midi_events.items():
        for e in events:
            if e.get('velocity', 0) == 0:
                continue  # Skip note-off

            midi_note = e['note']
            velocity = e['velocity']
            sample_name = DEFAULT_MIDI_DRUM_MAPPING.get(midi_note)

            if sample_name and sample_name in sample_index:
                dpcm_events.append({
                    "frame": e['frame'],
                    "sample_id": sample_index[sample_name]['id'],
                    "velocity": velocity
                })
            else:
                # Fallback to noise
                noise_events.append({
                    "frame": e['frame'],
                    "velocity": velocity
                })

    return dpcm_events, noise_events


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python drum_engine.py <parsed_midi.json> <dpcm_index.json>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        midi_data = json.load(f)

    events = map_drums_to_dpcm(midi_data, sys.argv[2])
    print(json.dumps(events, indent=2))
