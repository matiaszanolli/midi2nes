# New file: exporter/exporter_nsf.py

import struct
from pathlib import Path
from typing import Dict, Any, List

class NSFHeader:
    """NSF File Format Header"""
    def __init__(self):
        self.magic = b'NESM\x1a'  # NSF Magic number
        self.version = 1
        self.total_songs = 1
        self.starting_song = 1
        self.load_address = 0x8000    # Default load address
        self.init_address = 0x8000    # Address of init routine
        self.play_address = 0x8003    # Address of play routine
        self.song_name = "MIDI2NES"   # Default song name
        self.artist_name = ""         # Artist name
        self.copyright = ""           # Copyright info
        self.ntsc_speed = 16639      # ~60Hz for NTSC
        self.bankswitch_init = [0] * 8  # Bank switching initialization values
        self.pal_speed = 19997       # ~50Hz for PAL
        self.pal_ntsc_bits = 0       # 0 = NTSC, 1 = PAL, 2 = Dual
        self.extra_sound_chips = 0   # No extra sound chips
        self.reserved = bytes([0] * 4)  # Reserved bytes

    def pack(self) -> bytes:
        """Pack header into bytes"""
        header = (
            self.magic +
            bytes([self.version]) +
            bytes([self.total_songs]) +
            bytes([self.starting_song]) +
            struct.pack('<H', self.load_address) +
            struct.pack('<H', self.init_address) +
            struct.pack('<H', self.play_address) +
            self.song_name.ljust(32, '\0').encode('ascii') +
            self.artist_name.ljust(32, '\0').encode('ascii') +
            self.copyright.ljust(32, '\0').encode('ascii') +
            struct.pack('<H', self.ntsc_speed) +
            bytes(self.bankswitch_init) +
            struct.pack('<H', self.pal_speed) +
            bytes([self.pal_ntsc_bits]) +
            bytes([self.extra_sound_chips]) +
            self.reserved
        )
        return header

class NSFExporter:
    """NSF Binary Format Exporter"""
    
    def __init__(self):
        self.header = NSFHeader()
        self.data_segment = bytearray()
        self.current_address = 0x8000

    def add_init_routine(self):
        """Add initialization routine"""
        # Basic init routine
        init_routine = bytes([
            0xA9, 0x00,     # LDA #$00   ; Initialize APU
            0x8D, 0x15, 0x40,  # STA $4015
            0xA9, 0x0F,     # LDA #$0F   ; Enable channels
            0x8D, 0x15, 0x40,  # STA $4015
            0x60            # RTS
        ])
        self.data_segment.extend(init_routine)
        self.current_address += len(init_routine)

    def add_play_routine(self, frames_data: Dict[str, Any]):
        """
        Add play routine and frame data
        
        Args:
            frames_data: Dictionary containing frame data for each channel
        """
        # Convert frames to binary data
        frame_data = self._convert_frames_to_binary(frames_data)
        
        # Add frame data pointer table
        pointer_table_start = self.current_address
        for channel_data in frame_data:
            self.data_segment.extend(struct.pack('<H', self.current_address + len(frame_data) * 2))
        
        # Add frame data
        for channel_data in frame_data:
            self.data_segment.extend(channel_data)
        
        # Add play routine
        play_routine = self._generate_play_routine(pointer_table_start)
        self.data_segment.extend(play_routine)

    def _convert_frames_to_binary(self, frames_data: Dict[str, Any]) -> List[bytes]:
        """Convert frame data to binary format"""
        binary_data = []
        
        # Process each channel
        for channel in ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']:
            if channel not in frames_data:
                binary_data.append(bytes([0xFF]))  # End marker
                continue
                
            channel_data = bytearray()
            events = frames_data[channel]
            
            current_frame = 0
            for frame_str, event in sorted(events.items(), key=lambda x: int(x[0])):
                frame = int(frame_str)
                
                # Add wait frames if needed
                while current_frame < frame:
                    channel_data.append(0x00)  # Wait command
                    current_frame += 1
                
                # Add event data
                if channel in ['pulse1', 'pulse2', 'triangle']:
                    note = event['note']
                    volume = min(15, event['volume'])
                    channel_data.append((volume << 4) | (note & 0x0F))
                    channel_data.append(note >> 4)
                elif channel == 'noise':
                    volume = min(15, event['volume'])
                    channel_data.append(volume)
                elif channel == 'dpcm':
                    sample_id = event['sample_id']
                    channel_data.append(sample_id)
                
                current_frame += 1
            
            channel_data.append(0xFF)  # End marker
            binary_data.append(bytes(channel_data))
        
        return binary_data

    def _generate_play_routine(self, pointer_table_start: int) -> bytes:
        """Generate play routine assembly code"""
        # Simple play routine that reads through frame data
        play_routine = bytes([
            0xA2, 0x00,     # LDX #$00   ; Channel counter
            0xBD, pointer_table_start & 0xFF, pointer_table_start >> 8,  # LDA pointer_table,X
            0x85, 0x00,     # STA $00    ; Store pointer low byte
            0xBD, (pointer_table_start + 1) & 0xFF, (pointer_table_start + 1) >> 8,  # LDA pointer_table+1,X
            0x85, 0x01,     # STA $01    ; Store pointer high byte
            0xA0, 0x00,     # LDY #$00   ; Frame counter
            0xB1, 0x00,     # LDA ($00),Y ; Load frame data
            0xC9, 0xFF,     # CMP #$FF   ; Check for end marker
            0xF0, 0x0A,     # BEQ done   ; Branch if end marker
            0x9D, 0x00, 0x40,  # STA $4000,X ; Write to APU
            0xE8,           # INX        ; Next channel
            0xE0, 0x0F,     # CPX #$0F   ; Check if done
            0xD0, 0xE7,     # BNE loop   ; Branch if not done
            0x60            # RTS
        ])
        return play_routine

    def export(self, frames_data: Dict[str, Any], output_path: str, 
               song_name: str = "", artist: str = "", copyright: str = ""):
        """
        Export frames data to NSF format
        
        Args:
            frames_data: Dictionary containing frame data for each channel
            output_path: Path to output NSF file
            song_name: Name of the song
            artist: Artist name
            copyright: Copyright information
        """
        # Update header information
        self.header.song_name = song_name
        self.header.artist_name = artist
        self.header.copyright = copyright
        
        # Add initialization routine
        self.add_init_routine()
        
        # Update header addresses
        self.header.init_address = 0x8000
        self.header.play_address = self.current_address
        
        # Add play routine and frame data
        self.add_play_routine(frames_data)
        
        # Write NSF file
        with open(output_path, 'wb') as f:
            f.write(self.header.pack())
            f.write(self.data_segment)
