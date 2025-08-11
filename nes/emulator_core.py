from collections import defaultdict
from .pitch_table import PitchProcessor
from collections import defaultdict
from .envelope_processor import EnvelopeProcessor


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
            # Handle both 'velocity' and 'volume' fields for compatibility
            velocity = event.get('velocity', event.get('volume', 0))
            if velocity == 0:
                continue  # We simulate note-off via time

            start_frame = event['frame']
            end_frame = start_frame + sustain_frames

            # Stop early if another note starts before sustain ends
            for j in range(i + 1, num_events):
                next_event = events[j]
                next_velocity = next_event.get('velocity', next_event.get('volume', 0))
                if next_velocity > 0 and next_event['frame'] > start_frame:
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
                        envelope_type, frame_offset, end_frame - start_frame, default_duty, None, velocity
                    )
                    frames[f] = {
                        "pitch": pitch,
                        "control": control_byte,
                        "arpeggio": arpeggio,
                        "note": event['note'],
                        "volume": min(15, velocity // 8)  # Also store raw volume for debugging
                    }
                else:
                    # For non-pulse channels, use simple volume calculation
                    volume = min(15, velocity // 8)
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
                        "volume": 15 if e.get('velocity', e.get('volume', 0)) > 0 else 0
                    } for e in events
                }
                processed[channel_name] = noise_frames
            elif channel_name == 'dpcm':
                dpcm_frames = {
                    e['frame']: {
                        "sample_id": e.get('sample_id', 0),
                        "volume": 15 if e.get('velocity', e.get('volume', 0)) > 0 else 0
                    } for e in events
                }
                processed[channel_name] = dpcm_frames

        return processed

