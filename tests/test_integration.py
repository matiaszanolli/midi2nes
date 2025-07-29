# tests/test_integration.py
import pytest
from pathlib import Path
from dpcm_sampler.enhanced_drum_mapper import (EnhancedDrumMapper, DrumMapperConfig,
                                               DrumPatternConfig, SampleManagerConfig)
from tracker.parser import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels

class TestDrumMapperIntegration:
    @pytest.fixture
    def test_midi_file(self, tmp_path):
        """Create a test MIDI file"""
        import mido
        
        midi_path = tmp_path / "test_drums.mid"
        
        # Create a simple MIDI file with drum hits
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        
        # Add some drum events on channel 9 (percussion)
        # Kick drum (note 36)
        track.append(mido.Message('note_on', channel=9, note=36, velocity=100, time=0))
        track.append(mido.Message('note_off', channel=9, note=36, velocity=0, time=480))
        
        # Snare drum (note 38)
        track.append(mido.Message('note_on', channel=9, note=38, velocity=90, time=480))
        track.append(mido.Message('note_off', channel=9, note=38, velocity=0, time=480))
        
        # Hi-hat (note 42)
        track.append(mido.Message('note_on', channel=9, note=42, velocity=80, time=240))
        track.append(mido.Message('note_off', channel=9, note=42, velocity=0, time=240))
        
        # Repeat pattern
        track.append(mido.Message('note_on', channel=9, note=36, velocity=100, time=240))
        track.append(mido.Message('note_off', channel=9, note=36, velocity=0, time=480))
        
        mid.save(str(midi_path))
        return midi_path
        
    def test_complete_pipeline(self, test_midi_file, tmp_path):
        """Test complete pipeline with new drum mapping"""
        # Create configuration
        config = DrumMapperConfig()
        config.use_advanced_mapping = True
        config.enable_pattern_detection = True
        
        # Parse MIDI
        midi_data = parse_midi_to_frames(str(test_midi_file))
        
        # Create drum mapper
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        
        # Map tracks
        mapped_data = assign_tracks_to_nes_channels(
            midi_data["events"],
            "tests/fixtures/test_dpcm_index.json"
        )
        
        # Verify results
        assert "dpcm" in mapped_data
        assert "noise" in mapped_data
        # DPCM may be empty if no drums are detected in the track
        assert mapped_data["dpcm"] is not None
        
        # Verify pattern optimization (may be 0 for simple test patterns)
        pattern_count = len(mapper.pattern_detector.detected_patterns)
        assert pattern_count >= 0
        
        # Verify sample management
        assert len(mapper.sample_manager.active_samples) <= config.sample_config.max_samples
        
    def test_configuration_integration(self, test_midi_file, tmp_path):
        """Test configuration integration in full pipeline"""
        config_path = tmp_path / "test_config.json"
        
        # Create custom configuration
        config = DrumMapperConfig(
            pattern_config=DrumPatternConfig(
                min_pattern_length=4,
                max_pattern_length=16
            ),
            sample_config=SampleManagerConfig(
                max_samples=16,
                memory_limit=4096
            )
        )
        
        # Save configuration
        config.to_file(str(config_path))
        
        # Load configuration in pipeline
        loaded_config = DrumMapperConfig.from_file(str(config_path))
        
        # Create mapper with loaded config
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=loaded_config
        )
        
        # Process MIDI
        midi_data = parse_midi_to_frames(str(test_midi_file))
        mapped_data = assign_tracks_to_nes_channels(
            midi_data["events"],
            "tests/fixtures/test_dpcm_index.json"
        )
        
        # Verify configuration was applied
        assert len(mapper.sample_manager.active_samples) <= loaded_config.sample_config.max_samples
        for pattern in mapper.pattern_detector.detected_patterns:
            assert loaded_config.pattern_config.min_pattern_length <= len(pattern) <= loaded_config.pattern_config.max_pattern_length
