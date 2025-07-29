import json
from .dpcm_sample_manager import DPCMSampleManager

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
