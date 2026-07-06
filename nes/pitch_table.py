"""
NES Pitch Table Generator and Constants

The NES APU uses timer values to generate different pitches. The timer value is
inversely proportional to the frequency, but the divider differs per channel:
    pulse:    frequency = CPU_CLOCK_RATE / (16 * (timer + 1))
    triangle: frequency = CPU_CLOCK_RATE / (32 * (timer + 1))

So for the same timer the triangle sounds one octave below a pulse, and the
triangle needs its own table built with divider 32 (docs/APU_TRIANGLE_REFERENCE.md
§3, docs/APU_PITCH_TABLE_REFERENCE.md §1).

Where:
- CPU_CLOCK_RATE is 1,789,773 Hz (NTSC)
- frequency is the desired note frequency in Hz
"""

# NES CPU Clock Rate (NTSC)
CPU_CLOCK_RATE = 1789773

# APU timer dividers per channel family.
PULSE_DIVIDER = 16
TRIANGLE_DIVIDER = 32

def generate_note_table(divider=PULSE_DIVIDER):
    """Generate a complete NES pitch table for all MIDI notes.

    ``divider`` selects the channel family: 16 for pulse, 32 for triangle
    (triangle plays an octave lower than pulse for the same timer).
    """
    # Standard MIDI note frequencies (A4 = 440Hz)
    def midi_to_freq(note):
        return 440 * (2 ** ((note - 69) / 12))

    note_table = {}

    # Generate for full MIDI range (0-127)
    for midi_note in range(128):
        freq = midi_to_freq(midi_note)
        # Calculate timer value
        timer = int(CPU_CLOCK_RATE / (divider * freq) - 1)
        # Clamp to the audible 11-bit range. The lower bound is 8, NOT 0:
        # pulse/triangle are silenced whenever timer t < 8 (APU_PULSE_REFERENCE
        # §3/§7), so the highest MIDI notes must floor at 8 instead of muting.
        timer = max(8, min(timer, 0x07FF))
        note_table[midi_note] = timer

    return note_table

# Pre-calculated note tables (pulse uses /16, triangle uses /32).
NES_NOTE_TABLE = generate_note_table(PULSE_DIVIDER)
NES_TRIANGLE_TABLE = generate_note_table(TRIANGLE_DIVIDER)

# Channel-specific note ranges
CHANNEL_RANGES = {
    "pulse1": (24, 108),   # C1 to C8
    "pulse2": (24, 108),   # C1 to C8
    "triangle": (24, 96),  # C1 to C7
    "noise": (24, 60)      # C1 to C4 (approximate)
}

def get_noise_period(midi_note):
    """Convert a MIDI note to a 4-bit NES noise period index ($400E low nibble).

    Lower index = shorter period = higher frequency (docs/APU_NOISE_REFERENCE.md
    §3), so a higher note must map to a *lower* index. The note is clamped to the
    noise channel range first. This is the single source of truth for noise
    pitch; PitchProcessor._get_noise_period delegates here.
    """
    min_note, max_note = CHANNEL_RANGES["noise"]
    midi_note = max(min_note, min(midi_note, max_note))
    note_range = max_note - min_note
    scaled = int(((midi_note - min_note) * 15) / note_range)
    # Invert: higher note -> lower period index -> higher pitch.
    return 15 - max(0, min(15, scaled))


class PitchProcessor:
    def __init__(self):
        # Channel pitch ranges (MIDI note numbers)
        self.channel_ranges = {
            "pulse1": (24, 108),  # C1 to C8
            "pulse2": (24, 108),  # C1 to C8
            "triangle": (24, 96), # C1 to C7
            "noise": (24, 60)     # C1 to C4
        }
        
        # Per-channel pitch tables from the single source of truth: pulse uses
        # the /16 table, triangle the /32 table (an octave lower for the same
        # timer, so it needs distinct periods to play the intended note).
        self.note_table = NES_NOTE_TABLE
        self.triangle_table = NES_TRIANGLE_TABLE

    def get_channel_pitch(self, midi_note, channel_type):
        """Convert MIDI note to NES pitch value with channel-specific limitations."""
        if channel_type not in self.channel_ranges:
            return 0

        min_note, max_note = self.channel_ranges[channel_type]
        midi_note = max(min_note, min(midi_note, max_note))

        if channel_type == "noise":
            return self._get_noise_period(midi_note)

        if channel_type == "triangle":
            return self.triangle_table[midi_note]

        return self.note_table[midi_note]
        
    def _get_noise_period(self, midi_note):
        """Convert MIDI note to a 4-bit noise period index (0-15).

        Delegates to the module-level get_noise_period so both impls stay in
        lockstep (higher note -> lower index -> higher pitch).
        """
        return get_noise_period(midi_note)
        
    def apply_pitch_bend(self, base_pitch, bend_amount, channel_type):
        """Apply pitch bend to a base pitch value."""
        if channel_type == "noise":
            return base_pitch
            
        # Convert bend to a multiplier (2 semitone range)
        bend_semitones = (bend_amount / 8192) * 2
        multiplier = 2 ** (bend_semitones / 12)
        
        # Calculate new timer value (inverse relationship with frequency).
        # Floor at 8 so an upward bend can't push the timer below the audible
        # threshold and silence the channel.
        new_timer = int(base_pitch / multiplier)
        return max(8, min(new_timer, 0x07FF))
        
    def note_to_timer(self, midi_note):
        """Convert a MIDI note to an NES pulse timer value.

        Clamps to the pulse channel range (``channel_ranges["pulse1"]`` = 24-108)
        rather than raising, matching the clamp policy every other entry point in
        this module uses (``get_channel_pitch``, ``get_noise_period``) and the
        exporter's ``midi_note_to_timer_value`` (#41/NH-11). The old guard raised
        for notes >= 96, wrongly rejecting the legal pulse notes 96-108 the same
        class treats as valid everywhere else. ``NES_NOTE_TABLE`` already floors
        each entry at 8 and clamps to 11 bits, so the returned timer is always a
        valid, audible period.
        """
        min_note, max_note = self.channel_ranges["pulse1"]
        midi_note = max(min_note, min(midi_note, max_note))
        return self.note_table[midi_note]
