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

ADVANCED_MIDI_DRUM_MAPPING = {
    36: {  # Kick
        "primary": "kick",
        "velocity_ranges": {
            (0, 64): "kick_soft",
            (65, 127): "kick_hard"
        },
        "layers": ["kick", "kick_sub"]  # For layered samples
    },
    38: {  # Snare
        "primary": "snare",
        "velocity_ranges": {
            (0, 64): "snare_soft",
            (65, 127): "snare_hard"
        },
        "layers": ["snare", "snare_rattle"]
    },
    # Add more mappings...
}


def map_drums_to_dpcm(midi_events, dpcm_index_path, use_advanced=True):
    """
    Map MIDI drum events to DPCM samples
    
    Args:
        midi_events: Dictionary of MIDI events
        dpcm_index_path: Path to DPCM sample index
        use_advanced: Whether to use advanced mapping features
    
    Returns:
        tuple: (dpcm_events, noise_events)
        
    Raises:
        FileNotFoundError: If dpcm_index_path doesn't exist
        json.JSONDecodeError: If dpcm_index_path contains invalid JSON
    """
    try:
        with open(dpcm_index_path, 'r') as f:
            sample_index = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"DPCM index file not found: {dpcm_index_path}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in DPCM index: {dpcm_index_path}", e.doc, e.pos)

    dpcm_events = []
    noise_events = []
    
    mapping = ADVANCED_MIDI_DRUM_MAPPING if use_advanced else DEFAULT_MIDI_DRUM_MAPPING

    for ch, events in midi_events.items():
        for e in events:
            if e.get('velocity', 0) == 0:
                continue

            midi_note = e['note']
            velocity = e['velocity']
            sample_name = None
            
            if use_advanced and midi_note in mapping:
                drum_config = mapping[midi_note]
                
                # Handle velocity ranges
                sample_name = drum_config["primary"]
                for (v_min, v_max), v_sample in drum_config["velocity_ranges"].items():
                    if v_min <= velocity <= v_max:
                        sample_name = v_sample
                        break
                
                # Handle layered samples
                if "layers" in drum_config:
                    for layer in drum_config["layers"]:
                        if layer in sample_index:
                            dpcm_events.append({
                                "frame": e['frame'],
                                "sample_id": sample_index[layer]['id'],
                                "velocity": velocity
                            })
            else:
                # Fallback to basic mapping
                sample_name = DEFAULT_MIDI_DRUM_MAPPING.get(midi_note)
            
            # Add main sample if valid
            if sample_name and sample_name in sample_index:
                dpcm_events.append({
                    "frame": e['frame'],
                    "sample_id": sample_index[sample_name]['id'],
                    "velocity": velocity
                })
            else:
                noise_events.append({
                    "frame": e['frame'],
                    "velocity": velocity
                })

    return dpcm_events, noise_events


def optimize_dpcm_samples(dpcm_events, max_samples=16):
    """
    Optimize DPCM sample usage based on frequency and importance
    
    Args:
        dpcm_events: List of DPCM events
        max_samples: Maximum number of samples to use
    """
    sample_usage = {}
    for event in dpcm_events:
        sample_id = event['sample_id']
        sample_usage[sample_id] = sample_usage.get(sample_id, 0) + 1
    
    # Sort by usage frequency
    sorted_samples = sorted(sample_usage.items(), 
                          key=lambda x: x[1], 
                          reverse=True)
    
    # Keep only most used samples
    allowed_samples = set(s[0] for s in sorted_samples[:max_samples])
    
    # Filter events
    optimized_events = []
    noise_fallback = []
    
    for event in dpcm_events:
        if event['sample_id'] in allowed_samples:
            optimized_events.append(event)
        else:
            noise_fallback.append({
                "frame": event['frame'],
                "velocity": event['velocity']
            })
    
    return optimized_events, noise_fallback


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python drum_engine.py <parsed_midi.json> <dpcm_index.json>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        midi_data = json.load(f)

    events = map_drums_to_dpcm(midi_data, sys.argv[2])
    print(json.dumps(events, indent=2))
