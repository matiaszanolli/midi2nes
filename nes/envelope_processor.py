import math
from collections import defaultdict
from nes.pitch_table import PitchProcessor

class EnvelopeProcessor:
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
        decay_end = attack_end + decay
        sustain_end = note_duration - release
        
        # Calculate base volume from ADSR envelope
        if frame_offset < attack_end and attack > 0:
            # Attack phase: volume ramps up
            base_volume = int((frame_offset / attack) * 15)
        elif frame_offset < decay_end and decay > 0:
            # Decay phase: volume ramps down to sustain level
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

    def get_envelope_control_byte(self, envelope_type, frame_offset, note_duration, duty_cycle=2, effects=None):
        """Generate NES control byte for pulse channels."""
        volume = self.get_envelope_value(envelope_type, frame_offset, note_duration, effects)
        
        # Get dynamic duty cycle if sequence is specified
        if effects and "duty_sequence" in effects:
            duty_cycle = self.get_duty_cycle(frame_offset, effects["duty_sequence"])
        
        # Duty cycle bits (bits 6-7)
        duty_bits = (duty_cycle & 0x03) << 6
        
        # Envelope bits (constant)
        envelope_bits = 0x30
        
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


class NESEmulatorCore:
    def __init__(self):
        self.pitch_processor = PitchProcessor()
        self.envelope_processor = EnvelopeProcessor()

    def compile_channel_to_frames(self, events, channel_type='pulse', default_duty=2, sustain_frames=4):
        frames = defaultdict(dict)
        events = sorted(events, key=lambda e: e['frame'])
        num_events = len(events)

        for i, event in enumerate(events):
            if event.get('velocity', 0) == 0:
                continue

            start_frame = event['frame']
            end_frame = start_frame + sustain_frames

            # Look ahead for next note
            for j in range(i + 1, num_events):
                next_event = events[j]
                if next_event.get('velocity', 0) > 0 and next_event['frame'] > start_frame:
                    end_frame = min(end_frame, next_event['frame'])
                    break

            pitch = self.midi_to_nes_pitch(event['note'], channel_type)
            envelope_type = event.get('envelope_type', 'default')
            
            # Extract effect parameters
            effects = {}
            if 'effects' in event:
                effects = event['effects']
                
            for f in range(start_frame, end_frame):
                frame_offset = f - start_frame
                
                # Apply pitch modifications
                modified_pitch = pitch
                if effects:
                    pitch_mod = self.envelope_processor.get_pitch_modification(frame_offset, effects)
                    modified_pitch += pitch_mod

                if channel_type.startswith('pulse'):
                    control_byte = self.envelope_processor.get_envelope_control_byte(
                        envelope_type, 
                        frame_offset, 
                        end_frame - start_frame,
                        default_duty,
                        effects
                    )
                    frames[f] = {
                        "pitch": modified_pitch,
                        "control": control_byte,
                        "effects": effects,
                        "note": event['note']
                    }
                else:
                    volume = min(15, event.get('velocity', 0) // 8)
                    frames[f] = {
                        "pitch": modified_pitch,
                        "volume": volume,
                        "effects": effects,
                        "note": event['note']
                    }

        return dict(sorted(frames.items()))
