"""
Data Transfer Objects for MIDI2NES.

Provides typed, immutable data structures for passing data between
pipeline stages. Using frozen dataclasses ensures data integrity
and enables better static analysis.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Tuple


class NESChannel(Enum):
    """NES APU channel identifiers."""
    PULSE1 = "pulse1"
    PULSE2 = "pulse2"
    TRIANGLE = "triangle"
    NOISE = "noise"
    DPCM = "dpcm"


class MapperType(Enum):
    """Supported NES mapper types with their specifications."""
    NROM = 0      # 32KB PRG-ROM, no banking
    MMC1 = 1      # 128KB PRG-ROM, 8 banks
    MMC3 = 4      # 512KB PRG-ROM, 32 banks

    @property
    def prg_size(self) -> int:
        """Return PRG-ROM size in bytes."""
        sizes = {
            MapperType.NROM: 32 * 1024,
            MapperType.MMC1: 128 * 1024,
            MapperType.MMC3: 512 * 1024,
        }
        return sizes[self]

    @property
    def bank_count(self) -> int:
        """Return number of 16KB PRG banks."""
        counts = {
            MapperType.NROM: 2,
            MapperType.MMC1: 8,
            MapperType.MMC3: 32,
        }
        return counts[self]


@dataclass(frozen=True)
class NoteEvent:
    """A single note event from MIDI parsing."""
    note: int           # MIDI note number (0-127)
    velocity: int       # Note velocity (0-127)
    start_frame: int    # Frame when note starts
    end_frame: int      # Frame when note ends
    channel: int = 0    # MIDI channel (0-15)

    @property
    def duration_frames(self) -> int:
        """Duration of the note in frames."""
        return self.end_frame - self.start_frame


@dataclass(frozen=True)
class FrameData:
    """
    Audio data for a single frame on a single channel.

    All values are NES APU register-ready:
    - pitch: Timer value for frequency (0-2047)
    - volume: Volume level (0-15)
    - control: APU control byte (duty cycle, envelope, etc.)
    - note: Original MIDI note for reference (0-127)
    """
    pitch: int = 0
    volume: int = 0
    control: int = 0
    note: int = 0

    def is_silent(self) -> bool:
        """Check if this frame represents silence."""
        return self.volume == 0


@dataclass
class ChannelFrames:
    """
    Frame data for a single NES channel across all frames.

    Uses integer keys for consistency (fixes the int/str key mismatch bug).
    """
    frames: Dict[int, FrameData] = field(default_factory=dict)

    def get_frame(self, frame_num: int) -> Optional[FrameData]:
        """Get frame data, returning None if not present."""
        return self.frames.get(frame_num)

    def get_max_frame(self) -> int:
        """Get the highest frame number in this channel."""
        return max(self.frames.keys()) if self.frames else 0

    def __len__(self) -> int:
        return len(self.frames)


@dataclass
class ParsedMidiDTO:
    """
    Result of MIDI parsing stage.

    Contains raw note events organized by track, plus tempo information.
    """
    tracks: Dict[int, List[NoteEvent]]  # track_num -> note events
    tempo_bpm: float = 120.0
    ticks_per_beat: int = 480
    total_frames: int = 0
    track_names: Dict[int, str] = field(default_factory=dict)

    @property
    def track_count(self) -> int:
        """Number of tracks in the parsed MIDI."""
        return len(self.tracks)


@dataclass
class MappedTracksDTO:
    """
    Result of track mapping stage.

    Maps MIDI tracks to NES channels with priority assignments.
    """
    channel_assignments: Dict[NESChannel, List[int]]  # channel -> track indices
    unmapped_tracks: List[int] = field(default_factory=list)
    mapping_notes: List[str] = field(default_factory=list)  # Warnings/info


@dataclass
class FrameDataDTO:
    """
    Complete frame data for all NES channels.

    This is the main data structure passed to the exporter.
    Frame keys are always integers for consistency.
    """
    pulse1: ChannelFrames = field(default_factory=ChannelFrames)
    pulse2: ChannelFrames = field(default_factory=ChannelFrames)
    triangle: ChannelFrames = field(default_factory=ChannelFrames)
    noise: ChannelFrames = field(default_factory=ChannelFrames)
    dpcm: ChannelFrames = field(default_factory=ChannelFrames)
    total_frames: int = 0

    def get_channel(self, channel: NESChannel) -> ChannelFrames:
        """Get frame data for a specific channel."""
        return getattr(self, channel.value)

    def get_max_frame(self) -> int:
        """Get the highest frame number across all channels."""
        return max(
            self.pulse1.get_max_frame(),
            self.pulse2.get_max_frame(),
            self.triangle.get_max_frame(),
            self.noise.get_max_frame(),
            self.dpcm.get_max_frame(),
        )


@dataclass(frozen=True)
class PatternInfo:
    """Information about a detected pattern."""
    pattern_id: str
    length: int
    occurrences: int
    channel: str

    @property
    def savings(self) -> int:
        """Bytes saved by using this pattern."""
        # Each occurrence saves (length - 2) bytes (2 bytes for reference)
        return (self.occurrences - 1) * (self.length - 2)


@dataclass
class CompressionStats:
    """Statistics about pattern compression."""
    original_size: int = 0
    compressed_size: int = 0
    pattern_count: int = 0
    total_references: int = 0

    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.compressed_size == 0:
            return 0.0
        return self.original_size / self.compressed_size

    @property
    def savings_percent(self) -> float:
        """Calculate percentage of bytes saved."""
        if self.original_size == 0:
            return 0.0
        return (1 - self.compressed_size / self.original_size) * 100


@dataclass
class PatternResultDTO:
    """
    Result of pattern detection stage.
    """
    patterns: Dict[str, List[Any]]  # pattern_id -> frame data
    references: Dict[str, List[int]]  # pattern_id -> positions
    stats: CompressionStats = field(default_factory=CompressionStats)
    variations: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompilationResultDTO:
    """
    Result of ROM compilation stage.
    """
    rom_path: str
    rom_size: int
    mapper_type: MapperType = MapperType.MMC1
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ValidationResultDTO:
    """
    Result of ROM validation stage.
    """
    is_valid: bool = True
    rom_size: int = 0
    header_valid: bool = True
    vectors_valid: bool = True
    has_music_data: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineResultDTO:
    """
    Complete result of the full MIDI2NES pipeline.
    """
    success: bool = True
    rom_path: Optional[str] = None

    # Stage results
    parsed: Optional[ParsedMidiDTO] = None
    mapped: Optional[MappedTracksDTO] = None
    frames: Optional[FrameDataDTO] = None
    patterns: Optional[PatternResultDTO] = None
    compilation: Optional[CompilationResultDTO] = None
    validation: Optional[ValidationResultDTO] = None

    # Timing and diagnostics
    total_time_seconds: float = 0.0
    stage_times: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
