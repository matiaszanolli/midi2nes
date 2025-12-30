"""
Core module for MIDI2NES.

Contains protocols, data transfer objects, exceptions, and type definitions
used throughout the pipeline.
"""

from .dto import (
    NESChannel,
    MapperType,
    NoteEvent,
    FrameData,
    ChannelFrames,
    ParsedMidiDTO,
    MappedTracksDTO,
    FrameDataDTO,
    PatternInfo,
    CompressionStats,
    PatternResultDTO,
    CompilationResultDTO,
    ValidationResultDTO,
    PipelineResultDTO,
)

from .exceptions import (
    MIDI2NESError,
    ParsingError,
    InvalidMIDIError,
    MappingError,
    ChannelOverflowError,
    PatternError,
    ExportError,
    CompilationError,
    ValidationError,
    MapperError,
    ConfigurationError,
)

from .types import (
    FrameNumber,
    MidiNote,
    Volume,
    Pitch,
    ChannelName,
)

__all__ = [
    # DTOs
    "NESChannel",
    "MapperType",
    "NoteEvent",
    "FrameData",
    "ChannelFrames",
    "ParsedMidiDTO",
    "MappedTracksDTO",
    "FrameDataDTO",
    "PatternInfo",
    "CompressionStats",
    "PatternResultDTO",
    "CompilationResultDTO",
    "ValidationResultDTO",
    "PipelineResultDTO",
    # Exceptions
    "MIDI2NESError",
    "ParsingError",
    "InvalidMIDIError",
    "MappingError",
    "ChannelOverflowError",
    "PatternError",
    "ExportError",
    "CompilationError",
    "ValidationError",
    "MapperError",
    "ConfigurationError",
    # Types
    "FrameNumber",
    "MidiNote",
    "Volume",
    "Pitch",
    "ChannelName",
]
