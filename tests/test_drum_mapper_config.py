import pytest
import json
from pathlib import Path
from dpcm_sampler.enhanced_drum_mapper import DrumMapperConfig, DrumPatternConfig, SampleManagerConfig

class TestDrumMapperConfig:
    def test_default_config_creation(self):
        """Test creation of default configuration"""
        config = DrumMapperConfig()
        assert config.pattern_config is not None
        assert config.sample_config is not None
        assert config.frame_rate == 60
        assert config.use_advanced_mapping is True
        
    def test_config_validation(self):
        """Test configuration validation"""
        config = DrumMapperConfig()
        
        # Should not raise
        config.validate()
        
        # Test invalid pattern weights
        config_invalid_weights = DrumMapperConfig()
        config_invalid_weights.pattern_config.timing_weight = 0.5
        config_invalid_weights.pattern_config.velocity_weight = 0.6
        with pytest.raises(ValueError, match="Pattern detection weights must sum to 1"):
            config_invalid_weights.validate()
            
        # Test invalid sample limits
        config_invalid_samples = DrumMapperConfig()
        config_invalid_samples.sample_config.max_samples = 0
        with pytest.raises(ValueError, match="max_samples must be between 1 and 64"):
            config_invalid_samples.validate()
            
    def test_config_file_io(self, tmp_path):
        """Test saving and loading configuration files"""
        config_path = tmp_path / "test_config.json"
        
        # Create config
        original_config = DrumMapperConfig(
            pattern_config=DrumPatternConfig(
                min_pattern_length=4,
                max_pattern_length=32
            ),
            sample_config=SampleManagerConfig(
                max_samples=32,
                memory_limit=8192
            )
        )
        
        # Save config
        original_config.to_file(str(config_path))
        assert config_path.exists()
        
        # Load config
        loaded_config = DrumMapperConfig.from_file(str(config_path))
        assert loaded_config.pattern_config.min_pattern_length == 4
        assert loaded_config.pattern_config.max_pattern_length == 32
        assert loaded_config.sample_config.max_samples == 32
        assert loaded_config.sample_config.memory_limit == 8192
        
    def test_invalid_config_file(self, tmp_path):
        """Test handling of invalid configuration files"""
        config_path = tmp_path / "invalid_config.json"
        
        # Create invalid JSON
        config_path.write_text("invalid json content")
        
        with pytest.raises(ValueError, match="Invalid JSON in configuration file"):
            DrumMapperConfig.from_file(str(config_path))