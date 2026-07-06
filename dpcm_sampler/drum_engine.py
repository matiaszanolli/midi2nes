import json

# Default MIDI drum note mapping. Covers the full GM percussion key range
# (35-81) with simple, generic role names, not just kick/snare (#73/D-10) --
# used both when use_advanced=False and as the last-resort fallback for any
# GM percussion note ADVANCED_MIDI_DRUM_MAPPING doesn't (fully) define.
DEFAULT_MIDI_DRUM_MAPPING = {
    35: "kick",           # Acoustic Bass Drum
    36: "kick",           # Bass Drum 1
    37: "side_stick",
    38: "snare",          # Acoustic Snare
    39: "clap",
    40: "snare",          # Electric Snare
    41: "tom_low",        # Low Floor Tom
    42: "hihat_closed",
    43: "tom_low",        # High Floor Tom
    44: "hihat_pedal",
    45: "tom_low",        # Low Tom
    46: "hihat_open",
    47: "tom_mid",        # Low-Mid Tom
    48: "tom_mid",        # Hi-Mid Tom
    49: "crash",          # Crash Cymbal 1
    50: "tom_high",       # High Tom
    51: "ride",           # Ride Cymbal 1
    52: "china",
    53: "ride_bell",
    54: "tambourine",
    55: "splash",
    56: "cowbell",
    57: "crash",          # Crash Cymbal 2
    58: "vibraslap",
    59: "ride",           # Ride Cymbal 2
    60: "bongo_hi",
    61: "bongo_lo",
    62: "conga_mute",
    63: "conga_open",
    64: "conga_lo",
    65: "timbale_hi",
    66: "timbale_lo",
    67: "agogo_hi",
    68: "agogo_lo",
    69: "cabasa",
    70: "maracas",
    71: "whistle_short",
    72: "whistle_long",
    73: "guiro_short",
    74: "guiro_long",
    75: "claves",
    76: "woodblock_hi",
    77: "woodblock_lo",
    78: "cuica_mute",
    79: "cuica_open",
    80: "triangle_mute",
    81: "triangle_open",
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
    # Every other GM percussion note falls back to DEFAULT_MIDI_DRUM_MAPPING
    # (see EnhancedDrumMapper._resolve_dpcm_sample_name, #73/D-10) rather than
    # needing a hand-tuned velocity-split entry here.
}


def map_drums_to_dpcm(midi_events, dpcm_index_path, use_advanced=True):
    """Use the enhanced drum mapper for proper DPCM mapping."""
    from .enhanced_drum_mapper import map_drums_to_dpcm as enhanced_map_drums
    return enhanced_map_drums(midi_events, dpcm_index_path, use_advanced)


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


class DrumPatternAnalyzer:
    def __init__(self):
        self.pattern_cache = {}
        self.groove_patterns = []
        
    def analyze_drum_track(self, midi_events):
        """Analyzes drum patterns and returns optimized mapping suggestions"""
        patterns = self.detect_patterns(midi_events)
        groove = self.detect_groove(midi_events)
        return self.optimize_mapping(patterns, groove)
        
    def detect_patterns(self, midi_events):
        """Detects common drum patterns and fills"""
        # Implementation here
        
    def detect_groove(self, midi_events):
        """Analyzes groove patterns and timing variations"""
        # Implementation here
        
    def optimize_mapping(self, patterns, groove):
        """Returns optimized channel and sample assignments"""
        # Implementation here


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python drum_engine.py <parsed_midi.json> <dpcm_index.json>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        midi_data = json.load(f)

    events = map_drums_to_dpcm(midi_data, sys.argv[2])
    print(json.dumps(events, indent=2))
