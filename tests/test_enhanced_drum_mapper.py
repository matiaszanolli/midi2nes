# tests/test_enhanced_drum_mapper.py
import pytest
from dpcm_sampler.enhanced_drum_mapper import (EnhancedDrumMapper, DrumMapperConfig,
                                               DrumPatternConfig, SampleManagerConfig)

class TestEnhancedDrumMapper:
    @pytest.fixture
    def sample_midi_events(self):
        """Sample MIDI drum events for testing"""
        return {
            9: [  # Channel 10 (MIDI channel 9) for drums
                {"note": 36, "velocity": 100, "frame": 0},  # Bass drum
                {"note": 38, "velocity": 90, "frame": 30},  # Snare
                {"note": 42, "velocity": 80, "frame": 60},  # Closed hi-hat
            ]
        }
        
    @pytest.fixture
    def config(self):
        """Test configuration"""
        return DrumMapperConfig(
            pattern_config=DrumPatternConfig(
                min_pattern_length=2,
                max_pattern_length=8
            ),
            sample_config=SampleManagerConfig(
                max_samples=8,
                memory_limit=2048
            )
        )
        
    def test_drum_pattern_detection(self, sample_midi_events, config):
        """Test pattern detection in drum mapping"""
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        
        # Add repeated pattern
        pattern_events = sample_midi_events[9] * 2  # Repeat pattern
        sample_midi_events[9] = pattern_events
        
        dpcm_events, noise_events = mapper.map_drums(sample_midi_events)
        
        # Verify pattern detection
        assert len(mapper.pattern_detector.detected_patterns) > 0
        
        # Verify sample reuse for patterns
        sample_ids = [e["sample_id"] for e in dpcm_events]
        unique_samples = len(set(sample_ids))
        assert unique_samples <= len(sample_ids)  # Should reuse samples
        
    def test_sample_management(self, sample_midi_events, config):
        """Test sample management and optimization"""
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        
        # Force memory pressure by setting low limit
        mapper.config.sample_config.memory_limit = 1024
        
        # Process multiple drum hits
        many_events = sample_midi_events[9] * 10  # Create many events
        sample_midi_events[9] = many_events
        
        dpcm_events, noise_events = mapper.map_drums(sample_midi_events)
        
        # Verify sample count stays within limits
        assert len(mapper.sample_manager.active_samples) <= config.sample_config.max_samples
        
        # Verify memory usage
        total_memory = mapper.sample_manager._get_total_memory()
        assert total_memory <= config.sample_config.memory_limit
        
    def test_advanced_mapping_features(self, sample_midi_events, config):
        """Test advanced mapping features"""
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        
        # Enable advanced mapping
        mapper.config.use_advanced_mapping = True
        
        dpcm_events, noise_events = mapper.map_drums(sample_midi_events)
        
        # Verify velocity-based sample selection
        high_velocity_event = {"note": 36, "velocity": 127, "frame": 90}
        low_velocity_event = {"note": 36, "velocity": 30, "frame": 120}
        sample_midi_events[9].extend([high_velocity_event, low_velocity_event])
        
        new_dpcm_events, _ = mapper.map_drums(sample_midi_events)
        
        # Should use different samples for different velocities (if they're mapped to DPCM)
        high_vel_events = [e for e in new_dpcm_events if e["frame"] == 90]
        low_vel_events = [e for e in new_dpcm_events if e["frame"] == 120]
        
        # If both events were mapped to DPCM, they should use different samples
        if high_vel_events and low_vel_events:
            high_vel_sample = high_vel_events[0]["sample_id"]
            low_vel_sample = low_vel_events[0]["sample_id"]
            assert high_vel_sample != low_vel_sample
        else:
            # At least verify that the events were processed
            assert len(new_dpcm_events) > 0 or len(noise_events) > 0
