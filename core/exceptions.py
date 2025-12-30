"""
Exception hierarchy for MIDI2NES.

Provides a structured set of exceptions that indicate specific
failure modes in the pipeline, enabling better error handling
and user feedback.
"""


class MIDI2NESError(Exception):
    """
    Base exception for all MIDI2NES errors.

    All custom exceptions inherit from this, allowing callers to catch
    all MIDI2NES-specific errors with a single except clause.
    """

    def __init__(self, message: str, details: str = ""):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


# =============================================================================
# Parsing Errors
# =============================================================================

class ParsingError(MIDI2NESError):
    """Error during MIDI file parsing."""
    pass


class InvalidMIDIError(ParsingError):
    """The input file is not a valid MIDI file."""

    def __init__(self, filepath: str, reason: str = ""):
        self.filepath = filepath
        message = f"Invalid MIDI file: {filepath}"
        super().__init__(message, reason)


# =============================================================================
# Mapping Errors
# =============================================================================

class MappingError(MIDI2NESError):
    """Error during track-to-channel mapping."""
    pass


class ChannelOverflowError(MappingError):
    """Too many tracks for available NES channels."""

    def __init__(self, track_count: int, available_channels: int = 4):
        self.track_count = track_count
        self.available_channels = available_channels
        message = f"Cannot map {track_count} tracks to {available_channels} channels"
        super().__init__(message)


# =============================================================================
# Pattern Detection Errors
# =============================================================================

class PatternError(MIDI2NESError):
    """Error during pattern detection or compression."""
    pass


# =============================================================================
# Export Errors
# =============================================================================

class ExportError(MIDI2NESError):
    """Error during assembly/data export."""
    pass


# =============================================================================
# Compilation Errors
# =============================================================================

class CompilationError(MIDI2NESError):
    """Error during ROM compilation with CC65 toolchain."""

    def __init__(self, message: str, tool: str = "", exit_code: int = -1):
        self.tool = tool
        self.exit_code = exit_code
        details = ""
        if tool:
            details = f"Tool: {tool}"
            if exit_code >= 0:
                details += f", Exit code: {exit_code}"
        super().__init__(message, details)


# =============================================================================
# Validation Errors
# =============================================================================

class ValidationError(MIDI2NESError):
    """ROM validation failed."""

    def __init__(self, message: str, checks_failed: list = None):
        self.checks_failed = checks_failed or []
        details = ", ".join(self.checks_failed) if self.checks_failed else ""
        super().__init__(message, details)


# =============================================================================
# Mapper Errors
# =============================================================================

class MapperError(MIDI2NESError):
    """Error related to NES mapper configuration."""
    pass


class MapperNotFoundError(MapperError):
    """Requested mapper type is not available."""

    def __init__(self, mapper_name: str):
        self.mapper_name = mapper_name
        message = f"Unknown mapper: {mapper_name}"
        details = "Available mappers: nrom, mmc1, mmc3"
        super().__init__(message, details)


class DataTooLargeError(MapperError):
    """Data exceeds capacity of the selected mapper."""

    def __init__(self, data_size: int, mapper_capacity: int, mapper_name: str):
        self.data_size = data_size
        self.mapper_capacity = mapper_capacity
        self.mapper_name = mapper_name
        message = f"Data size ({data_size} bytes) exceeds {mapper_name} capacity ({mapper_capacity} bytes)"
        super().__init__(message)


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigurationError(MIDI2NESError):
    """Error in configuration file or settings."""
    pass


# =============================================================================
# Toolchain Errors
# =============================================================================

class ToolchainError(MIDI2NESError):
    """CC65 toolchain not found or not working."""

    def __init__(self, tool: str = "cc65"):
        self.tool = tool
        message = f"CC65 toolchain not found"
        details = (
            f"Required tool '{tool}' is not available. "
            "Install with: brew install cc65 (macOS) or apt install cc65 (Linux)"
        )
        super().__init__(message, details)
