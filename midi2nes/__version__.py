"""Version information for MIDI2NES."""

__version__ = "0.4.0-dev"
__version_info__ = (0, 4, 0, "dev")

# Version history
VERSION_HISTORY = {
    "0.3.5": "Advanced Pattern Detection System with NES-optimized compression",
    "0.4.0-dev": "Performance optimization and user experience improvements"
}

def get_version():
    """Get the current version string."""
    return __version__

def get_version_info():
    """Get version information as tuple."""
    return __version_info__

def get_version_details():
    """Get detailed version information."""
    return {
        "version": __version__,
        "version_info": __version_info__,
        "description": VERSION_HISTORY.get(__version__, "Development version")
    }
