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

# Role names DEFAULT_MIDI_DRUM_MAPPING produces that have no identically
# named entry in the shipped dpcm_index.json catalog, but do have a real
# sample under a different filename (#315/DP-07). Extended for #340/DP-DPCM-01:
# triangle_mute/triangle_open alias to the catalog's one actual triangle
# instrument sample ("DPCM triangle"; both MIDI states share it -- the DMC
# is a single-voice channel, so mute vs. open can't be layered differently
# here anyway), and splash aliases to crash (a splash cymbal is a small,
# quick crash -- the closest timbre the catalog has). Vibraslap has no
# reasonably-close sample anywhere in the catalog (a distinctive rattling
# buzz unlike anything else here) and is deliberately left unaliased -- a
# genuine remaining asset gap, not a naming mismatch.
DPCM_ROLE_ALIASES = {
    "tambourine": "tamborin",
    "whistle_short": "whistle1",
    "whistle_long": "whistle2",
    "guiro_short": "guiro1",
    "guiro_long": "guiro2",
    "cuica_mute": "cuica1",
    "cuica_open": "cuica2",
    "woodblock_hi": "mario_2_woodblock",
    "woodblock_lo": "mario_2_woodblock",
    "side_stick": "stickrim",
    "splash": "crash",
    "triangle_mute": "DPCM triangle",
    "triangle_open": "DPCM triangle",
}

ADVANCED_MIDI_DRUM_MAPPING = {
    36: {  # Kick
        "primary": "kick",
        "velocity_ranges": {
            (0, 64): "kick_soft",
            (65, 127): "kick_hard"
        }
    },
    38: {  # Snare
        "primary": "snare",
        "velocity_ranges": {
            (0, 64): "snare_soft",
            (65, 127): "snare_hard"
        }
    },
    # Every other GM percussion note falls back to DEFAULT_MIDI_DRUM_MAPPING
    # (see EnhancedDrumMapper._resolve_dpcm_sample_name, #73/D-10) rather than
    # needing a hand-tuned velocity-split entry here.
    #
    # No "layers" key here (removed, #300/DP-05): the DMC is a single-voice
    # channel (docs/APU_DMC_REFERENCE.md §1) and cannot play two samples at
    # once, so "layering" could only ever (a) duplicate the primary sample on
    # the same frame -- silently discarded by the same-frame collapse with a
    # misleading "note dropped" warning -- or (b) reference a name absent from
    # the shipped catalog (kick_sub/snare_rattle), which was silently skipped.
}


def map_drums_to_dpcm(midi_events, dpcm_index_path, use_advanced=True):
    """Use the enhanced drum mapper for proper DPCM mapping."""
    from .enhanced_drum_mapper import map_drums_to_dpcm as enhanced_map_drums
    return enhanced_map_drums(midi_events, dpcm_index_path, use_advanced)


# optimize_dpcm_samples and DrumPatternAnalyzer were removed here (#368/
# DP-DPCM-06): both were imported only by tests, never by any production
# caller (confirmed by grep -- no docs/ROADMAP.md entry planned wiring
# either in). DrumPatternAnalyzer's detect_patterns/detect_groove/
# optimize_mapping were empty stub bodies (implicit `return None`);
# analyze_drum_track just fed those Nones forward, so the class could not
# do anything. optimize_dpcm_samples's noise fallback built
# {"frame": ..., "velocity": ...} with no 'note' key, contradicting the
# live noise-event contract map_drums honors (#195/NH-26:
# process_all_tracks derives the noise period from 'note' via
# midi_to_nes_pitch()) -- reachable only as a KeyError/mis-pitch if this
# had ever been wired in. Removed rather than fixed since nothing consumes
# either; see git history for the prior implementation if a real
# consumer materializes.


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python drum_engine.py <parsed_midi.json> <dpcm_index.json>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        midi_data = json.load(f)

    events = map_drums_to_dpcm(midi_data, sys.argv[2])
    print(json.dumps(events, indent=2))
