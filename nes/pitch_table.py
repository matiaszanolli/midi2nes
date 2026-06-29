"""
NES Pitch Table Generator and Constants

The NES APU uses timer values to generate different pitches. The timer value is inversely 
proportional to the frequency. For the pulse and triangle channels, the formula is:
    timer_value = CPU_CLOCK_RATE / (16 * frequency) - 1

Where:
- CPU_CLOCK_RATE is 1,789,773 Hz (NTSC)
- frequency is the desired note frequency in Hz
"""

# NES CPU Clock Rate (NTSC)
CPU_CLOCK_RATE = 1789773

def generate_note_table():
    """Generate a complete NES pitch table for all MIDI notes."""
    # Standard MIDI note frequencies (A4 = 440Hz)
    def midi_to_freq(note):
        return 440 * (2 ** ((note - 69) / 12))
    
    note_table = {}
    
    # Generate for full MIDI range (0-127)
    for midi_note in range(128):
        freq = midi_to_freq(midi_note)
        # Calculate timer value
        timer = int(CPU_CLOCK_RATE / (16 * freq) - 1)
        # Clamp to valid range (0x0000 to 0x07FF)
        timer = max(0, min(timer, 0x07FF))
        note_table[midi_note] = timer
    
    return note_table

# Pre-calculated note table
NES_NOTE_TABLE = generate_note_table()

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
        
        # Generate the note table using the CPU clock rate
        self.note_table = self._generate_note_table()
        
    def _generate_note_table(self):
        """Generate a complete NES pitch table for all MIDI notes."""
        CPU_CLOCK_RATE = 1789773  # NTSC
        
        def midi_to_freq(note):
            return 440 * (2 ** ((note - 69) / 12))
        
        note_table = {}
        for midi_note in range(128):
            freq = midi_to_freq(midi_note)
            timer = int(CPU_CLOCK_RATE / (16 * freq) - 1)
            timer = max(0, min(timer, 0x07FF))
            note_table[midi_note] = timer
        
        return note_table
        
    def get_channel_pitch(self, midi_note, channel_type):
        """Convert MIDI note to NES pitch value with channel-specific limitations."""
        if channel_type not in self.channel_ranges:
            return 0
            
        min_note, max_note = self.channel_ranges[channel_type]
        midi_note = max(min_note, min(midi_note, max_note))
        
        if channel_type == "noise":
            return self._get_noise_period(midi_note)
            
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
        
        # Calculate new timer value (inverse relationship with frequency)
        new_timer = int(base_pitch / multiplier)
        return max(0, min(new_timer, 0x07FF))
        
    def note_to_timer(self, midi_note):
        """Convert MIDI note to NES timer value."""
        if midi_note < 0 or midi_note >= 128:
            raise ValueError(f"MIDI note {midi_note} out of valid range (0-127)")
        if midi_note < 24 or midi_note >= 96:
            raise ValueError(f"MIDI note {midi_note} out of NES range (24-95)")
        return self.note_table[midi_note]
