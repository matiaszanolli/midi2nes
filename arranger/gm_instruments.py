"""
General MIDI Instrument Mapping for NES.

Maps GM program numbers to NES handling strategies including:
- Musical role (bass, melody, pad, percussion)
- Preferred NES channel
- Playback style (sustain, staccato, arpeggiate)
- Duty cycle suggestions for pulse waves
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional, List


class MusicalRole(Enum):
    """The musical function an instrument typically serves."""
    BASS = auto()        # Low-end foundation
    MELODY = auto()      # Lead voice, prominent
    HARMONY = auto()     # Chords, pads, accompaniment
    PERCUSSION = auto()  # Drums, hits
    SFX = auto()         # Sound effects, one-shots
    DECORATIVE = auto()  # Flourishes, can be dropped


class NESChannel(Enum):
    """NES APU channel preference."""
    PULSE1 = "pulse1"      # Lead, bright
    PULSE2 = "pulse2"      # Harmony, echo
    TRIANGLE = "triangle"  # Bass, smooth
    NOISE = "noise"        # Percussion, hats
    DPCM = "dpcm"          # Samples, kicks
    ANY_PULSE = "any_pulse"  # Either pulse works
    FLEXIBLE = "flexible"    # Allocator decides


class PlayStyle(Enum):
    """How notes should be rendered on NES."""
    SUSTAIN = auto()      # Hold notes full duration
    STACCATO = auto()     # Short, punchy notes
    ARPEGGIATE = auto()   # Fast note cycling for chords
    SAMPLE = auto()       # Use DPCM sample if available
    LEGATO = auto()       # Smooth transitions, no retriggering


class DutyCycle(Enum):
    """Pulse wave duty cycle (timbre)."""
    DUTY_12 = 0   # 12.5% - Thin, nasal, reedy
    DUTY_25 = 1   # 25% - Hollow, clarinet-like
    DUTY_50 = 2   # 50% - Pure, full square wave
    DUTY_75 = 3   # 75% - Same as 25% (inverted)


@dataclass
class InstrumentMapping:
    """How a GM instrument maps to NES capabilities."""
    name: str
    role: MusicalRole
    channel: NESChannel
    style: PlayStyle
    duty: Optional[DutyCycle] = None  # For pulse channels
    priority: int = 5  # 1-10, higher = more important to keep
    transpose: int = 0  # Octave adjustment for NES range
    notes: str = ""  # Implementation notes


# =============================================================================
# General MIDI Program Number Mappings (0-127)
# Organized by GM categories
# =============================================================================

GM_INSTRUMENT_MAP: Dict[int, InstrumentMapping] = {
    # =========================================================================
    # PIANO (0-7) - Generally melodic, good for leads
    # =========================================================================
    0: InstrumentMapping(
        name="Acoustic Grand Piano",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=8,
        notes="Classic lead sound"
    ),
    1: InstrumentMapping(
        name="Bright Acoustic Piano",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=8,
        notes="Brighter timbre with 25% duty"
    ),
    2: InstrumentMapping(
        name="Electric Grand Piano",
        role=MusicalRole.MELODY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=7
    ),
    3: InstrumentMapping(
        name="Honky-tonk Piano",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=5,
        notes="Detuned feel with thin duty"
    ),
    4: InstrumentMapping(
        name="Electric Piano 1",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    5: InstrumentMapping(
        name="Electric Piano 2",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=6
    ),
    6: InstrumentMapping(
        name="Harpsichord",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=7,
        notes="Plucky, thin sound"
    ),
    7: InstrumentMapping(
        name="Clavinet",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=6,
        notes="Funky, percussive"
    ),

    # =========================================================================
    # CHROMATIC PERCUSSION (8-15)
    # =========================================================================
    8: InstrumentMapping(
        name="Celesta",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=4,
        notes="Sparkly, can be dropped"
    ),
    9: InstrumentMapping(
        name="Glockenspiel",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=4,
        transpose=12,  # Often written low
        notes="Bell-like, high register"
    ),
    10: InstrumentMapping(
        name="Music Box",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=3
    ),
    11: InstrumentMapping(
        name="Vibraphone",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=5,
        notes="Mellow, sustained"
    ),
    12: InstrumentMapping(
        name="Marimba",
        role=MusicalRole.MELODY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    13: InstrumentMapping(
        name="Xylophone",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=6,
        transpose=12
    ),
    14: InstrumentMapping(
        name="Tubular Bells",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=4,
        notes="Low bell, triangle works"
    ),
    15: InstrumentMapping(
        name="Dulcimer",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.ARPEGGIATE,
        duty=DutyCycle.DUTY_25,
        priority=4
    ),

    # =========================================================================
    # ORGAN (16-23)
    # =========================================================================
    16: InstrumentMapping(
        name="Drawbar Organ",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=6,
        notes="Full sustained chords"
    ),
    17: InstrumentMapping(
        name="Percussive Organ",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=7,
        notes="Attack transient important"
    ),
    18: InstrumentMapping(
        name="Rock Organ",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=7
    ),
    19: InstrumentMapping(
        name="Church Organ",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=5,
        notes="Big sustained sound"
    ),
    20: InstrumentMapping(
        name="Reed Organ",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=5
    ),
    21: InstrumentMapping(
        name="Accordion",
        role=MusicalRole.MELODY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    22: InstrumentMapping(
        name="Harmonica",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=7,
        notes="Expressive lead"
    ),
    23: InstrumentMapping(
        name="Tango Accordion",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),

    # =========================================================================
    # GUITAR (24-31)
    # =========================================================================
    24: InstrumentMapping(
        name="Acoustic Guitar (nylon)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.ARPEGGIATE,
        duty=DutyCycle.DUTY_25,
        priority=5,
        notes="Arpeggiated chords work well"
    ),
    25: InstrumentMapping(
        name="Acoustic Guitar (steel)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.ARPEGGIATE,
        duty=DutyCycle.DUTY_12,
        priority=5,
        notes="Brighter than nylon"
    ),
    26: InstrumentMapping(
        name="Electric Guitar (jazz)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=7,
        notes="Smooth lead tone"
    ),
    27: InstrumentMapping(
        name="Electric Guitar (clean)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=7
    ),
    28: InstrumentMapping(
        name="Electric Guitar (muted)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=5,
        notes="Rhythmic, short"
    ),
    29: InstrumentMapping(
        name="Overdriven Guitar",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=8,
        notes="Aggressive lead"
    ),
    30: InstrumentMapping(
        name="Distortion Guitar",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=8,
        notes="Heavy, sustained"
    ),
    31: InstrumentMapping(
        name="Guitar Harmonics",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=3,
        transpose=12
    ),

    # =========================================================================
    # BASS (32-39) - Critical for NES, typically Triangle
    # =========================================================================
    32: InstrumentMapping(
        name="Acoustic Bass",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=9,
        notes="Foundation, always keep"
    ),
    33: InstrumentMapping(
        name="Electric Bass (finger)",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=9,
        notes="Standard NES bass"
    ),
    34: InstrumentMapping(
        name="Electric Bass (pick)",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.STACCATO,
        priority=9,
        notes="Punchy attack"
    ),
    35: InstrumentMapping(
        name="Fretless Bass",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.LEGATO,
        priority=9,
        notes="Smooth slides"
    ),
    36: InstrumentMapping(
        name="Slap Bass 1",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.STACCATO,
        priority=9,
        notes="Can use DPCM for slap hits"
    ),
    37: InstrumentMapping(
        name="Slap Bass 2",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.STACCATO,
        priority=9
    ),
    38: InstrumentMapping(
        name="Synth Bass 1",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=9,
        notes="Classic synth bass"
    ),
    39: InstrumentMapping(
        name="Synth Bass 2",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.STACCATO,
        priority=9,
        notes="Punchy synth"
    ),

    # =========================================================================
    # STRINGS (40-47)
    # =========================================================================
    40: InstrumentMapping(
        name="Violin",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=7,
        notes="Expressive lead"
    ),
    41: InstrumentMapping(
        name="Viola",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=5
    ),
    42: InstrumentMapping(
        name="Cello",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=7,
        notes="Can double bass or be melodic"
    ),
    43: InstrumentMapping(
        name="Contrabass",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=8
    ),
    44: InstrumentMapping(
        name="Tremolo Strings",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=5,
        notes="Use volume tremolo"
    ),
    45: InstrumentMapping(
        name="Pizzicato Strings",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=4
    ),
    46: InstrumentMapping(
        name="Orchestral Harp",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.ARPEGGIATE,
        duty=DutyCycle.DUTY_12,
        priority=4,
        notes="Arpeggiated runs"
    ),
    47: InstrumentMapping(
        name="Timpani",
        role=MusicalRole.PERCUSSION,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.STACCATO,
        priority=6,
        notes="Pitched percussion"
    ),

    # =========================================================================
    # ENSEMBLE (48-55)
    # =========================================================================
    48: InstrumentMapping(
        name="String Ensemble 1",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=5,
        notes="Pad-like, arpeggiate if needed"
    ),
    49: InstrumentMapping(
        name="String Ensemble 2",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=4
    ),
    50: InstrumentMapping(
        name="Synth Strings 1",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=5
    ),
    51: InstrumentMapping(
        name="Synth Strings 2",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=4
    ),
    52: InstrumentMapping(
        name="Choir Aahs",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3,
        notes="Background, can drop"
    ),
    53: InstrumentMapping(
        name="Voice Oohs",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3
    ),
    54: InstrumentMapping(
        name="Synth Voice",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3
    ),
    55: InstrumentMapping(
        name="Orchestra Hit",
        role=MusicalRole.SFX,
        channel=NESChannel.DPCM,
        style=PlayStyle.SAMPLE,
        priority=6,
        notes="Big stab, use sample"
    ),

    # =========================================================================
    # BRASS (56-63)
    # =========================================================================
    56: InstrumentMapping(
        name="Trumpet",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=8,
        notes="Bright, prominent lead"
    ),
    57: InstrumentMapping(
        name="Trombone",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=6
    ),
    58: InstrumentMapping(
        name="Tuba",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=7,
        notes="Low brass on triangle"
    ),
    59: InstrumentMapping(
        name="Muted Trumpet",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_12,
        priority=7,
        notes="Thinner, muted sound"
    ),
    60: InstrumentMapping(
        name="French Horn",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=6
    ),
    61: InstrumentMapping(
        name="Brass Section",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_50,
        priority=6,
        notes="Stabs, punchy"
    ),
    62: InstrumentMapping(
        name="Synth Brass 1",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=7
    ),
    63: InstrumentMapping(
        name="Synth Brass 2",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=5
    ),

    # =========================================================================
    # REED (64-71)
    # =========================================================================
    64: InstrumentMapping(
        name="Soprano Sax",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=7
    ),
    65: InstrumentMapping(
        name="Alto Sax",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=7,
        notes="Classic lead instrument"
    ),
    66: InstrumentMapping(
        name="Tenor Sax",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_50,
        priority=7
    ),
    67: InstrumentMapping(
        name="Baritone Sax",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=6,
        notes="Low sax can be bass"
    ),
    68: InstrumentMapping(
        name="Oboe",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_12,
        priority=7,
        notes="Thin, reedy"
    ),
    69: InstrumentMapping(
        name="English Horn",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    70: InstrumentMapping(
        name="Bassoon",
        role=MusicalRole.BASS,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=6
    ),
    71: InstrumentMapping(
        name="Clarinet",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=7,
        notes="Hollow, clarinet-like duty"
    ),

    # =========================================================================
    # PIPE (72-79)
    # =========================================================================
    72: InstrumentMapping(
        name="Piccolo",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=4,
        transpose=12
    ),
    73: InstrumentMapping(
        name="Flute",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_50,
        priority=7,
        notes="Pure, clear tone"
    ),
    74: InstrumentMapping(
        name="Recorder",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    75: InstrumentMapping(
        name="Pan Flute",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=6
    ),
    76: InstrumentMapping(
        name="Blown Bottle",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=3
    ),
    77: InstrumentMapping(
        name="Shakuhachi",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    78: InstrumentMapping(
        name="Whistle",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=4,
        notes="Triangle gives pure tone"
    ),
    79: InstrumentMapping(
        name="Ocarina",
        role=MusicalRole.MELODY,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.SUSTAIN,
        priority=6,
        notes="Pure, flute-like"
    ),

    # =========================================================================
    # SYNTH LEAD (80-87)
    # =========================================================================
    80: InstrumentMapping(
        name="Lead 1 (square)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=8,
        notes="Native NES sound!"
    ),
    81: InstrumentMapping(
        name="Lead 2 (sawtooth)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=8,
        notes="Approximate with 25% duty"
    ),
    82: InstrumentMapping(
        name="Lead 3 (calliope)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_12,
        priority=7
    ),
    83: InstrumentMapping(
        name="Lead 4 (chiff)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=7
    ),
    84: InstrumentMapping(
        name="Lead 5 (charang)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=7
    ),
    85: InstrumentMapping(
        name="Lead 6 (voice)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_50,
        priority=6
    ),
    86: InstrumentMapping(
        name="Lead 7 (fifths)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=7,
        notes="Could arpeggiate the fifth"
    ),
    87: InstrumentMapping(
        name="Lead 8 (bass + lead)",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=8
    ),

    # =========================================================================
    # SYNTH PAD (88-95)
    # =========================================================================
    88: InstrumentMapping(
        name="Pad 1 (new age)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=4
    ),
    89: InstrumentMapping(
        name="Pad 2 (warm)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=4
    ),
    90: InstrumentMapping(
        name="Pad 3 (polysynth)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.ARPEGGIATE,
        duty=DutyCycle.DUTY_25,
        priority=5,
        notes="Arpeggiate for poly feel"
    ),
    91: InstrumentMapping(
        name="Pad 4 (choir)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3
    ),
    92: InstrumentMapping(
        name="Pad 5 (bowed)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=4
    ),
    93: InstrumentMapping(
        name="Pad 6 (metallic)",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_12,
        priority=4
    ),
    94: InstrumentMapping(
        name="Pad 7 (halo)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3
    ),
    95: InstrumentMapping(
        name="Pad 8 (sweep)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=3
    ),

    # =========================================================================
    # SYNTH EFFECTS (96-103)
    # =========================================================================
    96: InstrumentMapping(
        name="FX 1 (rain)",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=2
    ),
    97: InstrumentMapping(
        name="FX 2 (soundtrack)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3
    ),
    98: InstrumentMapping(
        name="FX 3 (crystal)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=3
    ),
    99: InstrumentMapping(
        name="FX 4 (atmosphere)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=2
    ),
    100: InstrumentMapping(
        name="FX 5 (brightness)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_12,
        priority=3
    ),
    101: InstrumentMapping(
        name="FX 6 (goblins)",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=2
    ),
    102: InstrumentMapping(
        name="FX 7 (echoes)",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3
    ),
    103: InstrumentMapping(
        name="FX 8 (sci-fi)",
        role=MusicalRole.SFX,
        channel=NESChannel.ANY_PULSE,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=3
    ),

    # =========================================================================
    # ETHNIC (104-111)
    # =========================================================================
    104: InstrumentMapping(
        name="Sitar",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_12,
        priority=6,
        notes="Twangy, thin"
    ),
    105: InstrumentMapping(
        name="Banjo",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.ARPEGGIATE,
        duty=DutyCycle.DUTY_12,
        priority=5
    ),
    106: InstrumentMapping(
        name="Shamisen",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=6
    ),
    107: InstrumentMapping(
        name="Koto",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=6
    ),
    108: InstrumentMapping(
        name="Kalimba",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_25,
        priority=5
    ),
    109: InstrumentMapping(
        name="Bag pipe",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    110: InstrumentMapping(
        name="Fiddle",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.LEGATO,
        duty=DutyCycle.DUTY_25,
        priority=7
    ),
    111: InstrumentMapping(
        name="Shanai",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_12,
        priority=5
    ),

    # =========================================================================
    # PERCUSSIVE (112-119)
    # =========================================================================
    112: InstrumentMapping(
        name="Tinkle Bell",
        role=MusicalRole.DECORATIVE,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=2
    ),
    113: InstrumentMapping(
        name="Agogo",
        role=MusicalRole.PERCUSSION,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=4
    ),
    114: InstrumentMapping(
        name="Steel Drums",
        role=MusicalRole.MELODY,
        channel=NESChannel.PULSE1,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_25,
        priority=6
    ),
    115: InstrumentMapping(
        name="Woodblock",
        role=MusicalRole.PERCUSSION,
        channel=NESChannel.NOISE,
        style=PlayStyle.STACCATO,
        priority=4
    ),
    116: InstrumentMapping(
        name="Taiko Drum",
        role=MusicalRole.PERCUSSION,
        channel=NESChannel.DPCM,
        style=PlayStyle.SAMPLE,
        priority=7,
        notes="Big drum, use sample"
    ),
    117: InstrumentMapping(
        name="Melodic Tom",
        role=MusicalRole.PERCUSSION,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.STACCATO,
        priority=5
    ),
    118: InstrumentMapping(
        name="Synth Drum",
        role=MusicalRole.PERCUSSION,
        channel=NESChannel.TRIANGLE,
        style=PlayStyle.STACCATO,
        priority=5
    ),
    119: InstrumentMapping(
        name="Reverse Cymbal",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=3
    ),

    # =========================================================================
    # SOUND EFFECTS (120-127)
    # =========================================================================
    120: InstrumentMapping(
        name="Guitar Fret Noise",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.STACCATO,
        priority=1
    ),
    121: InstrumentMapping(
        name="Breath Noise",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=1
    ),
    122: InstrumentMapping(
        name="Seashore",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=1
    ),
    123: InstrumentMapping(
        name="Bird Tweet",
        role=MusicalRole.SFX,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_12,
        priority=1
    ),
    124: InstrumentMapping(
        name="Telephone Ring",
        role=MusicalRole.SFX,
        channel=NESChannel.PULSE2,
        style=PlayStyle.STACCATO,
        duty=DutyCycle.DUTY_50,
        priority=1
    ),
    125: InstrumentMapping(
        name="Helicopter",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=1
    ),
    126: InstrumentMapping(
        name="Applause",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.SUSTAIN,
        priority=1
    ),
    127: InstrumentMapping(
        name="Gunshot",
        role=MusicalRole.SFX,
        channel=NESChannel.NOISE,
        style=PlayStyle.STACCATO,
        priority=2
    ),
}


# =============================================================================
# GM Drum Map (Channel 10)
# Standard GM drum notes
# =============================================================================

@dataclass
class DrumMapping:
    """How a GM drum sound maps to NES."""
    name: str
    channel: NESChannel
    style: PlayStyle
    priority: int = 5
    noise_period: Optional[int] = None  # For noise channel (0-15)
    use_sample: bool = False
    notes: str = ""


GM_DRUM_MAP: Dict[int, DrumMapping] = {
    # Bass drums - DPCM preferred, Triangle fallback
    35: DrumMapping("Acoustic Bass Drum", NESChannel.DPCM, PlayStyle.SAMPLE, 9, use_sample=True),
    36: DrumMapping("Bass Drum 1", NESChannel.DPCM, PlayStyle.SAMPLE, 9, use_sample=True),

    # Snares - DPCM or Noise
    38: DrumMapping("Acoustic Snare", NESChannel.DPCM, PlayStyle.SAMPLE, 8, use_sample=True),
    40: DrumMapping("Electric Snare", NESChannel.NOISE, PlayStyle.STACCATO, 8, noise_period=4),

    # Hi-hats - Noise channel
    42: DrumMapping("Closed Hi-Hat", NESChannel.NOISE, PlayStyle.STACCATO, 6, noise_period=0),
    44: DrumMapping("Pedal Hi-Hat", NESChannel.NOISE, PlayStyle.STACCATO, 5, noise_period=1),
    46: DrumMapping("Open Hi-Hat", NESChannel.NOISE, PlayStyle.SUSTAIN, 6, noise_period=2),

    # Toms - Triangle
    41: DrumMapping("Low Floor Tom", NESChannel.TRIANGLE, PlayStyle.STACCATO, 5),
    43: DrumMapping("High Floor Tom", NESChannel.TRIANGLE, PlayStyle.STACCATO, 5),
    45: DrumMapping("Low Tom", NESChannel.TRIANGLE, PlayStyle.STACCATO, 5),
    47: DrumMapping("Low-Mid Tom", NESChannel.TRIANGLE, PlayStyle.STACCATO, 5),
    48: DrumMapping("Hi-Mid Tom", NESChannel.TRIANGLE, PlayStyle.STACCATO, 5),
    50: DrumMapping("High Tom", NESChannel.TRIANGLE, PlayStyle.STACCATO, 5),

    # Cymbals - Noise
    49: DrumMapping("Crash Cymbal 1", NESChannel.NOISE, PlayStyle.SUSTAIN, 4, noise_period=6),
    51: DrumMapping("Ride Cymbal 1", NESChannel.NOISE, PlayStyle.STACCATO, 4, noise_period=3),
    52: DrumMapping("Chinese Cymbal", NESChannel.NOISE, PlayStyle.SUSTAIN, 3, noise_period=5),
    53: DrumMapping("Ride Bell", NESChannel.NOISE, PlayStyle.STACCATO, 4, noise_period=2),
    55: DrumMapping("Splash Cymbal", NESChannel.NOISE, PlayStyle.SUSTAIN, 3, noise_period=4),
    57: DrumMapping("Crash Cymbal 2", NESChannel.NOISE, PlayStyle.SUSTAIN, 4, noise_period=6),
    59: DrumMapping("Ride Cymbal 2", NESChannel.NOISE, PlayStyle.STACCATO, 4, noise_period=3),

    # Claps, sticks, etc - Noise
    37: DrumMapping("Side Stick", NESChannel.NOISE, PlayStyle.STACCATO, 5, noise_period=0),
    39: DrumMapping("Hand Clap", NESChannel.NOISE, PlayStyle.STACCATO, 6, noise_period=3),
    54: DrumMapping("Tambourine", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=1),
    56: DrumMapping("Cowbell", NESChannel.NOISE, PlayStyle.STACCATO, 4, noise_period=8),

    # Latin percussion
    60: DrumMapping("Hi Bongo", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=1),
    61: DrumMapping("Low Bongo", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=3),
    62: DrumMapping("Mute Hi Conga", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=2),
    63: DrumMapping("Open Hi Conga", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=4),
    64: DrumMapping("Low Conga", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=6),
    65: DrumMapping("High Timbale", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=1),
    66: DrumMapping("Low Timbale", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=3),
    67: DrumMapping("High Agogo", NESChannel.PULSE2, PlayStyle.STACCATO, 2),
    68: DrumMapping("Low Agogo", NESChannel.PULSE2, PlayStyle.STACCATO, 2),
    69: DrumMapping("Cabasa", NESChannel.NOISE, PlayStyle.STACCATO, 2, noise_period=0),
    70: DrumMapping("Maracas", NESChannel.NOISE, PlayStyle.STACCATO, 2, noise_period=0),

    # Whistles
    71: DrumMapping("Short Whistle", NESChannel.TRIANGLE, PlayStyle.STACCATO, 2),
    72: DrumMapping("Long Whistle", NESChannel.TRIANGLE, PlayStyle.SUSTAIN, 2),

    # Guiro, claves
    73: DrumMapping("Short Guiro", NESChannel.NOISE, PlayStyle.STACCATO, 2, noise_period=1),
    74: DrumMapping("Long Guiro", NESChannel.NOISE, PlayStyle.SUSTAIN, 2, noise_period=1),
    75: DrumMapping("Claves", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=0),
    76: DrumMapping("Hi Wood Block", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=0),
    77: DrumMapping("Low Wood Block", NESChannel.NOISE, PlayStyle.STACCATO, 3, noise_period=2),

    # Cuica, triangle
    78: DrumMapping("Mute Cuica", NESChannel.PULSE2, PlayStyle.STACCATO, 2),
    79: DrumMapping("Open Cuica", NESChannel.PULSE2, PlayStyle.SUSTAIN, 2),
    80: DrumMapping("Mute Triangle", NESChannel.PULSE2, PlayStyle.STACCATO, 2),
    81: DrumMapping("Open Triangle", NESChannel.PULSE2, PlayStyle.SUSTAIN, 2),
}


def get_instrument_mapping(program: int) -> InstrumentMapping:
    """Get the NES mapping for a GM program number."""
    if program in GM_INSTRUMENT_MAP:
        return GM_INSTRUMENT_MAP[program]
    # Default fallback
    return InstrumentMapping(
        name=f"Unknown ({program})",
        role=MusicalRole.HARMONY,
        channel=NESChannel.PULSE2,
        style=PlayStyle.SUSTAIN,
        duty=DutyCycle.DUTY_50,
        priority=3
    )


def get_drum_mapping(note: int) -> DrumMapping:
    """Get the NES mapping for a GM drum note."""
    if note in GM_DRUM_MAP:
        return GM_DRUM_MAP[note]
    # Default fallback - generic noise hit
    return DrumMapping(
        name=f"Unknown Drum ({note})",
        channel=NESChannel.NOISE,
        style=PlayStyle.STACCATO,
        priority=3,
        noise_period=5
    )


def get_role_priority() -> Dict[MusicalRole, int]:
    """Get priority ordering for musical roles."""
    return {
        MusicalRole.BASS: 1,        # Foundation first
        MusicalRole.PERCUSSION: 2,  # Rhythm section
        MusicalRole.MELODY: 3,      # Lead voice
        MusicalRole.HARMONY: 4,     # Supporting
        MusicalRole.DECORATIVE: 5,  # Can drop
        MusicalRole.SFX: 6,         # Optional
    }
