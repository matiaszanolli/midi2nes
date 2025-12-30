"""
Type aliases for MIDI2NES.

Provides semantic type hints that make code more readable
and enable better static analysis.
"""

from typing import Dict, List, Tuple, Union, Literal

# Basic numeric types with semantic meaning
FrameNumber = int  # Frame number (0-65535 typically)
MidiNote = int  # MIDI note number (0-127)
Volume = int  # Volume/velocity (0-127 for MIDI, 0-15 for NES)
Pitch = int  # NES APU timer value (0-2047)
ControlByte = int  # APU control byte (0-255)

# Channel identifiers
ChannelName = Literal["pulse1", "pulse2", "triangle", "noise", "dpcm"]

# Frame data types (what's stored at each frame)
FrameDict = Dict[str, int]  # {'pitch': int, 'volume': int, ...}

# Channel frame collections
ChannelFrameDict = Dict[int, FrameDict]  # {frame_num: frame_data}
AllChannelsDict = Dict[ChannelName, ChannelFrameDict]

# Event types
EventDict = Dict[str, Union[int, str, bool]]

# Pattern types
PatternId = str  # e.g., "pattern_0", "pattern_1"
PositionList = List[int]  # List of position indices
PatternReferences = Dict[PatternId, PositionList]

# Mapper types
MapperNumber = int  # iNES mapper number (0, 1, 4, etc.)
BankNumber = int  # PRG bank number

# Assembly code
AssemblyCode = str  # CA65 assembly code string
LinkerConfig = str  # CC65 linker configuration
