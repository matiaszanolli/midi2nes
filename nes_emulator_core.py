from collections import defaultdict
from typing import List, Dict, Optional
from nes_pitch_table import NES_NOTE_TABLE, CHANNEL_RANGES, get_noise_period

# Accurate NES note table for NTSC
NES_NOTE_TABLE = {
    48: 0x0F9B, 49: 0x0EF9, 50: 0x0E5F, 51: 0x0DDA, 52: 0x0D5A, 53: 0x0CE6, 54: 0x0C77, 55: 0x0C0C,
    56: 0x0BA5, 57: 0x0B42, 58: 0x0AE3, 59: 0x0A87, 60: 0x0A2E, 61: 0x09D9, 62: 0x0986, 63: 0x0936,
    64: 0x08E9, 65: 0x089E, 66: 0x0856, 67: 0x0810, 68: 0x07CC, 69: 0x078A, 70: 0x074A, 71: 0x070C,
    72: 0x06D0, 73: 0x0695, 74: 0x065D, 75: 0x0626, 76: 0x05F1, 77: 0x05BE, 78: 0x058C, 79: 0x055C,
    80: 0x052D, 81: 0x0500, 82: 0x04D4, 83: 0x04A9, 84: 0x0480, 85: 0x0458, 86: 0x0431, 87: 0x040C,
    88: 0x03E7, 89: 0x03C4, 90: 0x03A2, 91: 0x0381, 92: 0x0361, 93: 0x0342, 94: 0x0324, 95: 0x0307,
    96: 0x02EB, 97: 0x02D0, 98: 0x02B5, 99: 0x029B, 100: 0x0282, 101: 0x0269, 102: 0x0251, 103: 0x023A,
    104: 0x0223, 105: 0x020D, 106: 0x01F8, 107: 0x01E3, 108: 0x01CF, 109: 0x01BB, 110: 0x01A8, 111: 0x0195,
    112: 0x0183, 113: 0x0171, 114: 0x0160, 115: 0x014F, 116: 0x013E, 117: 0x012E, 118: 0x011E, 119: 0x010F,
    120: 0x0100, 121: 0x00F1, 122: 0x00E3, 123: 0x00D5, 124: 0x00C7, 125: 0x00BA, 126: 0x00AD, 127: 0x00A0
}

def midi_to_nes_pitch(note, channel_type='pulse'):
    if channel_type == 'pulse' or channel_type == 'triangle':
        return NES_NOTE_TABLE.get(note, 0x000)  # Silent if undefined
    elif channel_type == 'noise':
        # Noise channel uses a different frequency table
        return note  # Placeholder, noise channel uses different handling
    elif channel_type == 'dpcm':
        # DPCM channel uses sample IDs instead of pitches
        return note  # Placeholder, DPCM channel uses different handling
    return 0x000  # Default to silent

def compile_channel_to_frames(events: List[Dict], channel_type='pulse', default_duty=2, sustain_frames=4):
    """
    Extend note-on events to simulate duration across frames with envelope processing.
    """
    frames = defaultdict(dict)
    envelope_processor = EnvelopeProcessor()

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

        pitch = midi_to_nes_pitch(event['note'], channel_type)
        envelope_type = event.get('envelope_type', 'default')
        arpeggio = event.get('arpeggio', False)

        for f in range(start_frame, end_frame):
            frame_offset = f - start_frame
            if channel_type.startswith('pulse'):
                control_byte = envelope_processor.get_envelope_control_byte(
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


def process_all_tracks(nes_tracks: Dict[str, List[Dict]]) -> Dict[str, Dict[int, Dict]]:
    processed = {}

    for channel_name, events in nes_tracks.items():
        if channel_name in ['pulse1', 'pulse2', 'triangle']:
            duty = 2 if 'pulse' in channel_name else None
            processed[channel_name] = compile_channel_to_frames(events, channel_type=channel_name, default_duty=duty)

        elif channel_name == 'noise':
            # Placeholder: use note as noise mode (white vs periodic)
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

if __name__ == "__main__":
    import sys, json

    if len(sys.argv) < 2:
        print("Usage: python nes_emulator_core.py <mapped_tracks.json>")
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        nes_tracks = json.load(f)

    processed = process_all_tracks(nes_tracks)
    print(json.dumps(processed, indent=2))


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
