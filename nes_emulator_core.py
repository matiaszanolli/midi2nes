from collections import defaultdict
from nes_pitch_table import PitchProcessor
from collections import defaultdict


class NESEmulatorCore:
    def __init__(self):
        self.pitch_processor = PitchProcessor()
        self.envelope_processor = EnvelopeProcessor()

    def midi_to_nes_pitch(self, note, channel_type='pulse'):
        return self.pitch_processor.get_channel_pitch(note, channel_type)

    def compile_channel_to_frames(self, events, channel_type='pulse', default_duty=2, sustain_frames=4):
        """
        Extend note-on events to simulate duration across frames with envelope processing.
        """
        frames = defaultdict(dict)

        # Sort events by frame
        events = sorted(events, key=lambda e: e['frame'])
        num_events = len(events)

        for i, event in enumerate(events):
            if event.get('velocity', 0) == 0:
                continue  # We simulate note-off via time

            start_frame = event['frame']
            end_frame = start_frame + sustain_frames

            # Stop early if another note starts before sustain ends
            for j in range(i + 1, num_events):
                next_event = events[j]
                if next_event.get('velocity', 0) > 0 and next_event['frame'] > start_frame:
                    end_frame = min(end_frame, next_event['frame'])
                    break

            # Use the pitch_processor instance instead of static function
            pitch = self.midi_to_nes_pitch(event['note'], channel_type)
            envelope_type = event.get('envelope_type', 'default')
            arpeggio = event.get('arpeggio', False)

            for f in range(start_frame, end_frame):
                frame_offset = f - start_frame
                if channel_type.startswith('pulse'):
                    control_byte = self.envelope_processor.get_envelope_control_byte(
                        envelope_type, frame_offset, end_frame - start_frame, default_duty
                    )
                    frames[f] = {
                        "pitch": pitch,
                        "control": control_byte,
                        "arpeggio": arpeggio,
                        "note": event['note']
                    }
                else:
                    # For non-pulse channels, use simple volume calculation
                    volume = min(15, event.get('velocity', 0) // 8)
                    frames[f] = {
                        "pitch": pitch,
                        "volume": volume,
                        "arpeggio": arpeggio,
                        "note": event['note']
                    }

        return dict(sorted(frames.items()))

    def process_all_tracks(self, nes_tracks):
        processed = {}
        
        for channel_name, events in nes_tracks.items():
            if channel_name in ['pulse1', 'pulse2', 'triangle']:
                duty = 2 if 'pulse' in channel_name else None
                processed[channel_name] = self.compile_channel_to_frames(
                    events, 
                    channel_type=channel_name, 
                    default_duty=duty
                )
            elif channel_name == 'noise':
                noise_frames = {
                    e['frame']: {
                        "noise_mode": 0,  # white noise
                        "volume": 15 if e.get('velocity', 0) > 0 else 0
                    } for e in events
                }
                processed[channel_name] = noise_frames
            elif channel_name == 'dpcm':
                dpcm_frames = {
                    e['frame']: {
                        "sample_id": e.get('sample_id', 0),
                        "volume": 15 if e.get('velocity', 0) > 0 else 0
                    } for e in events
                }
                processed[channel_name] = dpcm_frames

        return processed


class EnvelopeProcessor:
    """
    Handles ADSR envelope processing for NES audio channels.
    """
    def __init__(self):
        self.envelope_definitions = {
            # Format: (attack, decay, sustain, release)
            "default": (0, 0, 15, 0),  # Default: no attack/decay, full sustain, no release
            "piano": (1, 3, 10, 2),    # Piano-like: quick attack, some decay, medium sustain
            "pad": (5, 10, 8, 5),      # Pad-like: slow attack, long decay, medium sustain
            "pluck": (0, 8, 0, 0),     # Pluck: no attack, quick decay, no sustain
            "percussion": (0, 15, 0, 0) # Percussion: no attack, immediate decay
        }
        
    def get_envelope_value(self, envelope_type, frame_offset, note_duration):
        """
        Calculate envelope value for a specific frame offset within a note.
        
        Args:
            envelope_type: String identifier for envelope type
            frame_offset: Number of frames since note start
            note_duration: Total duration of note in frames
            
        Returns:
            Volume value (0-15) for the current frame
        """
        if envelope_type not in self.envelope_definitions:
            envelope_type = "default"
            
        attack, decay, sustain, release = self.envelope_definitions[envelope_type]
        
        # Calculate envelope phases in frames
        attack_end = attack
        decay_end = attack_end + decay
        sustain_end = note_duration - release
        
        # Determine current envelope phase
        if frame_offset < attack_end and attack > 0:
            # Attack phase: volume ramps up
            return int((frame_offset / attack) * 15)
        elif frame_offset < decay_end and decay > 0:
            # Decay phase: volume ramps down to sustain level
            decay_progress = (frame_offset - attack_end) / decay
            return int(15 - ((15 - sustain) * decay_progress))
        elif frame_offset < sustain_end:
            # Sustain phase: volume stays constant
            return sustain
        else:
            # Release phase: volume ramps down to zero
            if release == 0 or sustain_end >= note_duration:
                return 0
            release_progress = (frame_offset - sustain_end) / release
            return int(sustain * (1 - release_progress))

    def get_envelope_control_byte(self, envelope_type, frame_offset, note_duration, duty_cycle=2):
        """
        Generate NES control byte for pulse channels with envelope and duty cycle.
        
        Args:
            envelope_type: String identifier for envelope type
            frame_offset: Number of frames since note start
            note_duration: Total duration of note in frames
            duty_cycle: Duty cycle value (0-3)
            
        Returns:
            Control byte for NES pulse channel
        """
        volume = self.get_envelope_value(envelope_type, frame_offset, note_duration)
        
        # Duty cycle bits (bits 6-7)
        duty_bits = (duty_cycle & 0x03) << 6
        
        # Envelope bits
        # Bit 4: Envelope loop flag (0 for now)
        # Bit 5: Length counter halt (1 to disable length counter)
        envelope_bits = 0x30  # 0011 0000
        
        # Combine with volume (bits 0-3)
        return duty_bits | envelope_bits | (volume & 0x0F)
