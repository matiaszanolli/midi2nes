# New file: exporter/exporter_nsf.py

import struct
from typing import Dict, Any, List
from exporter.base_exporter import BaseExporter

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
        self.bankswitch_init = [0, 1, 2, 3, 4, 5, 6, 7]  # Bank switching initialization values
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

class NSFExporter(BaseExporter):
    """NSF Binary Format Exporter"""
    
    def __init__(self):
        super().__init__()
        self.header = NSFHeader()
        self.data_segment = bytearray()
        self.current_address = 0x8000

    # NSF export is NOT implemented. The previous draft serialized channel
    # "data" as a UTF-8 JSON string embedded in the NSF binary (not 6502- or
    # APU-loadable) and a hand-assembled play routine whose branch offsets were
    # wrong (BEQ landed past the RTS, BNE landed mid-instruction), so any file it
    # produced was not a playable NSF (#81). Rather than emit garbage, the public
    # API raises; NSF was already removed from the CLI (#79). NSFHeader and the
    # binary NSFMacroPacker (below) are retained as scaffolding for a real
    # implementation. Use the CA65 / ROM export path for working audio output.
    _UNSUPPORTED_MSG = (
        "NSF export is not implemented: a playable NSF needs a real 6502 play "
        "routine and a binary APU data stream (the old path emitted JSON-as-data "
        "and a play routine with wrong branch offsets, #81). Use the CA65/ROM "
        "export path instead."
    )

    def export(self, frames_data: Dict[str, Any], output_path: str,
               song_name: str = "", artist: str = "", copyright: str = ""):
        """NSF export is not implemented - see #81. Raises NotImplementedError."""
        raise NotImplementedError(self._UNSUPPORTED_MSG)

    def export_nsf(self, data: Dict[str, Any], output_path):
        """NSF export is not implemented - see #81. Raises NotImplementedError."""
        raise NotImplementedError(self._UNSUPPORTED_MSG)


class NSFMacroPacker:
    """
    Draft logic for packing MMC3 Macro Bytecode into binary arrays for NSF.
    This will eventually replace the JSON-based serialization in NSFExporter.
    """
    def __init__(self, base_address: int = 0x8000):
        self.base_address = base_address
        self.macro_pool = bytearray()
        self.instrument_table = bytearray()
        self.sequence_data = bytearray()
        self.pointers = {}

    def pack(self, macros: Dict[str, List[int]], instruments: Dict[str, Dict[str, str]], sequences: Dict[str, List[int]]) -> bytes:
        """
        Packs macros, instruments, and channel sequences into a single binary payload.
        
        Args:
            macros: Dict of macro ID to list of integer values (e.g., {'vol_0': [15, 14, 13, 0xFF]})
            instruments: Dict of instrument ID to macro assignments 
                         (e.g., {'inst_0': {'vol': 'vol_0', 'arp': None, 'pitch': None, 'duty': None}})
            sequences: Dict of channel name to list of bytecode integers
                       (e.g., {'pulse1': [0x80, 0x00, 0x64, 0x3C, 0xFF]})
        """
        # 1. Pack Macros (Volume, Arp, Pitch, Duty)
        macro_start_addr = self.base_address
        for macro_id, macro_data in macros.items():
            self.pointers[macro_id] = macro_start_addr + len(self.macro_pool)
            self.macro_pool.extend(macro_data)

        # 2. Pack Instruments
        # Each instrument needs 4 pointers (Vol, Arp, Pitch, Duty) - 8 bytes total
        inst_start_addr = macro_start_addr + len(self.macro_pool)
        for inst_id, inst_macros in instruments.items():
            self.pointers[inst_id] = inst_start_addr + len(self.instrument_table)
            
            for m_type in ['vol', 'arp', 'pitch', 'duty']:
                m_id = inst_macros.get(m_type)
                if m_id and m_id in self.pointers:
                    ptr = self.pointers[m_id]
                else:
                    ptr = 0x0000 # Null pointer (macro_null)
                
                self.instrument_table.extend(struct.pack('<H', ptr))

        # 3. Pack Sequence Bytecode
        seq_start_addr = inst_start_addr + len(self.instrument_table)
        for channel, bytecode in sequences.items():
            self.pointers[f"seq_{channel}"] = seq_start_addr + len(self.sequence_data)
            self.sequence_data.extend(bytecode)
            
        # Combine all parts
        return self.macro_pool + self.instrument_table + self.sequence_data
        
    def get_channel_pointers(self) -> List[int]:
        """Returns the start addresses for the 5 channels to build the song header"""
        channel_order = ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']
        ptrs = []
        for ch in channel_order:
            key = f"seq_{ch}"
            ptrs.append(self.pointers.get(key, 0x0000))
        return ptrs
        
    def build_song_header(self, initial_tempo: int) -> bytes:
        """Builds the 11-byte song header (5 pointers + 1 tempo byte)"""
        header = bytearray()
        for ptr in self.get_channel_pointers():
            header.extend(struct.pack('<H', ptr))
        header.append(initial_tempo & 0xFF)
        return bytes(header)
