"""Configuration management for MIDI2NES."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field


@dataclass
class ProcessingConfig:
    """Processing-related configuration."""
    pattern_detection: Dict[str, Any] = field(default_factory=lambda: {
        "min_length": 3,
        "max_variations": 5,
        "similarity_threshold": 0.8,
        "enable_transposition": True,
        "enable_volume_variations": True
    })
    channel_mapping: Dict[str, Any] = field(default_factory=lambda: {
        "priority_order": ["pulse1", "pulse2", "triangle", "noise", "dpcm"],
        "allow_channel_sharing": False,
        "prefer_melody_on_pulse1": True
    })
    tempo: Dict[str, Any] = field(default_factory=lambda: {
        "frame_alignment": True,
        "max_tempo_change_ratio": 2.0,
        "enable_tempo_smoothing": True
    })


@dataclass 
class ExportConfig:
    """Export format configuration."""
    ca65: Dict[str, Any] = field(default_factory=lambda: {
        "standalone_mode": True,
        "include_debug_info": False,
        "optimize_size": True,
        "generate_linker_config": True
    })
    nsf: Dict[str, Any] = field(default_factory=lambda: {
        "ntsc_mode": True,
        "load_address": 0x8000,
        "init_address": 0x8000,
        "enable_bankswitching": True
    })
    famistudio: Dict[str, Any] = field(default_factory=lambda: {
        "include_tempo_track": True,
        "include_volume_track": True,
        "optimize_patterns": True
    })


@dataclass
class PerformanceConfig:
    """Performance and resource configuration."""
    max_memory_mb: int = 512
    enable_caching: bool = True
    parallel_processing: bool = False
    progress_reporting: bool = True


@dataclass
class QualityConfig:
    """Quality and compression configuration."""
    envelope_resolution: int = 16
    pitch_bend_resolution: int = 64
    volume_curve: str = "linear"
    pattern_compression_level: str = "balanced"
    enable_delta_compression: bool = True
    enable_rle_compression: bool = True


@dataclass
class ValidationConfig:
    """Validation and compliance configuration."""
    strict_nes_compliance: bool = True
    warn_on_channel_overflow: bool = True
    validate_timing: bool = True
    check_memory_limits: bool = True


@dataclass
class DevelopmentConfig:
    """Development and debugging configuration."""
    debug_mode: bool = False
    save_intermediate_files: bool = False
    enable_profiling: bool = False
    log_level: str = "info"


class ConfigManager:
    """Manages MIDI2NES configuration files."""
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file. If None, uses default config.
        """
        self.config_path = Path(config_path) if config_path else None
        self._config = None
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file or use defaults."""
        if self.config_path and self.config_path.exists():
            self._load_from_file(self.config_path)
        else:
            self._load_defaults()
    
    def _load_from_file(self, path: Path):
        """Load configuration from YAML file."""
        try:
            with open(path, 'r') as f:
                self._config = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to load configuration from {path}: {e}")
    
    def _load_defaults(self):
        """Load default configuration."""
        # Load from default config file
        default_config_path = Path(__file__).parent / "default_config.yaml"
        if default_config_path.exists():
            self._load_from_file(default_config_path)
        else:
            # Fallback to hardcoded defaults
            self._config = self._get_hardcoded_defaults()
    
    def _get_hardcoded_defaults(self) -> Dict[str, Any]:
        """Get hardcoded default configuration."""
        return {
            "processing": {
                "pattern_detection": {
                    "min_length": 3,
                    "max_variations": 5,
                    "similarity_threshold": 0.8,
                    "enable_transposition": True,
                    "enable_volume_variations": True
                },
                "channel_mapping": {
                    "priority_order": ["pulse1", "pulse2", "triangle", "noise", "dpcm"],
                    "allow_channel_sharing": False,
                    "prefer_melody_on_pulse1": True
                },
                "tempo": {
                    "frame_alignment": True,
                    "max_tempo_change_ratio": 2.0,
                    "enable_tempo_smoothing": True
                }
            },
            "export": {
                "ca65": {
                    "standalone_mode": True,
                    "include_debug_info": False,
                    "optimize_size": True,
                    "generate_linker_config": True
                },
                "nsf": {
                    "ntsc_mode": True,
                    "load_address": 0x8000,
                    "init_address": 0x8000,
                    "enable_bankswitching": True
                }
            },
            "performance": {
                "max_memory_mb": 512,
                "enable_caching": True,
                "parallel_processing": False,
                "progress_reporting": True
            },
            "quality": {
                "envelope_resolution": 16,
                "pitch_bend_resolution": 64,
                "volume_curve": "linear",
                "pattern_compression_level": "balanced",
                "enable_delta_compression": True,
                "enable_rle_compression": True
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "processing.pattern_detection.min_length")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        Set configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "processing.pattern_detection.min_length")
            value: Value to set
        """
        keys = key.split('.')
        config = self._config
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
    
    def save(self, path: Optional[Union[str, Path]] = None):
        """
        Save configuration to file.
        
        Args:
            path: Path to save configuration. If None, saves to original path.
        """
        save_path = Path(path) if path else self.config_path
        if not save_path:
            raise ValueError("No path specified for saving configuration")
        
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(save_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False, indent=2)
    
    def validate(self) -> bool:
        """
        Validate configuration values.
        
        Returns:
            True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        errors = []
        
        # Validate pattern detection settings
        min_length = self.get("processing.pattern_detection.min_length", 3)
        if not isinstance(min_length, int) or min_length < 1:
            errors.append("processing.pattern_detection.min_length must be a positive integer")
        
        similarity_threshold = self.get("processing.pattern_detection.similarity_threshold", 0.8)
        if not isinstance(similarity_threshold, (int, float)) or not 0.0 <= similarity_threshold <= 1.0:
            errors.append("processing.pattern_detection.similarity_threshold must be between 0.0 and 1.0")
        
        # Validate performance settings
        max_memory = self.get("performance.max_memory_mb", 512)
        if not isinstance(max_memory, int) or max_memory < 64:
            errors.append("performance.max_memory_mb must be at least 64 MB")
        
        # Validate NSF settings
        load_address = self.get("export.nsf.load_address", 0x8000)
        if not isinstance(load_address, int) or not 0x8000 <= load_address <= 0xFFFF:
            errors.append("export.nsf.load_address must be between 0x8000 and 0xFFFF")
        
        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors))
        
        return True
    
    def get_processing_config(self) -> ProcessingConfig:
        """Get processing configuration as dataclass."""
        config_dict = self.get("processing", {})
        return ProcessingConfig(
            pattern_detection=config_dict.get("pattern_detection", {}),
            channel_mapping=config_dict.get("channel_mapping", {}),
            tempo=config_dict.get("tempo", {})
        )
    
    def get_export_config(self) -> ExportConfig:
        """Get export configuration as dataclass."""
        config_dict = self.get("export", {})
        return ExportConfig(
            ca65=config_dict.get("ca65", {}),
            nsf=config_dict.get("nsf", {}),
            famistudio=config_dict.get("famistudio", {})
        )
    
    def get_performance_config(self) -> PerformanceConfig:
        """Get performance configuration as dataclass."""
        config_dict = self.get("performance", {})
        return PerformanceConfig(
            max_memory_mb=config_dict.get("max_memory_mb", 512),
            enable_caching=config_dict.get("enable_caching", True),
            parallel_processing=config_dict.get("parallel_processing", False),
            progress_reporting=config_dict.get("progress_reporting", True)
        )
    
    @classmethod
    def create_default_config(cls, output_path: Union[str, Path]):
        """
        Create a default configuration file.
        
        Args:
            output_path: Path where to create the configuration file
        """
        config_manager = cls()
        config_manager.save(output_path)
        
    def copy_default_config_to(self, output_path: Union[str, Path]):
        """
        Copy the default configuration to a new location.
        
        Args:
            output_path: Destination path for configuration file
        """
        default_config_path = Path(__file__).parent / "default_config.yaml"
        output_path = Path(output_path)
        
        if default_config_path.exists():
            import shutil
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(default_config_path, output_path)
        else:
            # Create from hardcoded defaults
            self.save(output_path)
