import math

class EnvelopeProcessor:
    """Engine-driven ADSR/effects model for the pulse channels
    (docs/APU_ENVELOPE_REFERENCE.md §4/§5).

    INERT SCAFFOLDING (#166): no pipeline stage currently sets ``envelope_type``
    or passes ``effects``, so on the live path ``get_envelope_value`` always uses
    the ``default`` (flat) envelope and the vibrato/duty-sequence effects are
    unreachable. The non-default envelopes and ``effect_definitions`` below are
    kept deliberately — they are the format a future GM-based producer (the
    arranger's instrument table is the natural home; NH-19 drum decay would be
    the first real user) will drive without re-plumbing this class. Do not treat
    their presence as evidence that timbre variety is wired up today.
    """

    def __init__(self):
        self.envelope_definitions = {
            # Original envelopes (keep these as they are in tests)
            "default": (0, 0, 15, 0),  # Default: no attack/decay, full sustain
            "piano": (1, 3, 10, 2),    # Piano-like: quick attack, some decay
            "pad": (5, 10, 8, 5),      # Pad-like: slow attack, long decay
            "pluck": (0, 8, 0, 0),     # Pluck: no attack, quick decay
            "percussion": (0, 15, 0, 0) # Percussion: no attack, immediate decay
        }
        
        # Store effect definitions separately to not interfere with tests
        self.effect_definitions = {
            "vibrato": {
                "speeds": [2, 3, 4, 6],
                "depths": [2, 4, 8],
                "delay_frames": [0, 4, 8, 16]
            },
            "duty_sequences": {
                "follin_lead": [(2, 4), (1, 4), (2, 4), (3, 4)],
                "follin_sweep": [(0, 2), (1, 2), (2, 2), (3, 2)],
                "follin_pulse": [(2, 8), (3, 8)]
            }
        }

    def get_envelope_value(self, envelope_type, frame_offset, note_duration, effects=None):
        """Calculate envelope value for a specific frame offset within a note."""
        if envelope_type not in self.envelope_definitions:
            envelope_type = "default"
            
        attack, decay, sustain, release = self.envelope_definitions[envelope_type]
        
        # Calculate envelope phases in frames
        attack_end = attack
        # For percussion envelopes with no sustain, decay should end at note duration
        if sustain == 0 and release == 0:
            decay_end = note_duration
        else:
            decay_end = attack_end + decay
        sustain_end = note_duration - release
        
        # Calculate base volume from ADSR envelope
        if frame_offset < attack_end and attack > 0:
            # Attack phase: volume ramps up
            base_volume = int((frame_offset / attack) * 15)
        elif frame_offset < decay_end and decay > 0:
            # Decay phase: volume ramps down to sustain level
            if sustain == 0 and release == 0:
                # For percussion envelopes, decay to zero over note duration
                # Make sure we reach exactly zero at the last frame
                if frame_offset >= note_duration - 1:
                    base_volume = 0
                else:
                    decay_progress = (frame_offset - attack_end) / (note_duration - 1 - attack_end)
                    base_volume = int(15 * (1 - decay_progress))
            else:
                decay_progress = (frame_offset - attack_end) / decay
                base_volume = int(15 - ((15 - sustain) * decay_progress))
        elif frame_offset < sustain_end:
            # Sustain phase: volume stays constant
            base_volume = sustain
        else:
            # Release phase: volume ramps down to zero
            if release == 0 or sustain_end >= note_duration:
                base_volume = 0
            else:
                release_progress = (frame_offset - sustain_end) / release
                base_volume = int(sustain * (1 - release_progress))
        
        # Apply effects if any
        if effects and "tremolo" in effects:
            tremolo = effects["tremolo"]
            tremolo_mod = math.sin(frame_offset / tremolo["speed"] * 2 * math.pi)
            base_volume += int(tremolo_mod * tremolo["depth"])
            
        return max(0, min(15, base_volume))

    def get_duty_cycle(self, frame_offset, sequence_name=None):
        """Get duty cycle value for the current frame."""
        if not sequence_name or sequence_name not in self.effect_definitions["duty_sequences"]:
            return 2  # Default duty cycle
            
        sequence = self.effect_definitions["duty_sequences"][sequence_name]
        total_frames = sum(frames for _, frames in sequence)
        current_frame = frame_offset % total_frames
        
        accumulated = 0
        for duty, frames in sequence:
            accumulated += frames
            if current_frame < accumulated:
                return duty
        return 2

    def get_envelope_control_byte(self, envelope_type, frame_offset, note_duration, duty_cycle=2, effects=None, base_velocity=None):
        """Generate NES control byte for pulse channels."""
        # Get envelope-modified volume
        envelope_volume = self.get_envelope_value(envelope_type, frame_offset, note_duration, effects)
        
        # Apply base velocity if provided (scale from MIDI 0-127 to NES 0-15)
        if base_velocity is not None:
            # Using a 1.5 power curve maps logarithmic human hearing to linear APU steps
            base_velocity = min(127, max(0, base_velocity))
            if base_velocity > 0:
                midi_volume = max(1, int(15 * math.pow(base_velocity / 127.0, 1.5)))
            else:
                midi_volume = 0
            # Round instead of floor division to preserve fidelity during instrument fades
            volume = min(15, round((envelope_volume * midi_volume) / 15.0))
        else:
            volume = envelope_volume
        
        # Get dynamic duty cycle if sequence is specified
        if effects and "duty_sequence" in effects:
            duty_cycle = self.get_duty_cycle(frame_offset, effects["duty_sequence"])
        
        # Duty cycle bits (bits 6-7)
        duty_bits = (duty_cycle & 0x03) << 6
        
        # Envelope bits (constant volume)
        envelope_bits = 0x10  # Set bit 4 for constant volume
        
        return duty_bits | envelope_bits | (volume & 0x0F)
    
    def apply_volume_envelope(self, frames, pattern, channel, start_frame):
        """Apply volume envelope pattern to frames"""
        for i, volume in enumerate(pattern):
            frame_key = str(start_frame + i)
            if frame_key not in frames:
                frames[frame_key] = {}
            if channel not in frames[frame_key]:
                frames[frame_key][channel] = {}
            frames[frame_key][channel]['volume'] = volume
    
    def apply_duty_envelope(self, frames, pattern, channel, start_frame):
        """Apply duty cycle envelope pattern to frames"""
        for i, duty in enumerate(pattern):
            frame_key = str(start_frame + i)
            if frame_key not in frames:
                frames[frame_key] = {}
            if channel not in frames[frame_key]:
                frames[frame_key][channel] = {}
            frames[frame_key][channel]['duty'] = duty * 64  # Convert to NES duty values
    
