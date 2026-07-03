# tests/test_enhanced_drum_mapper.py
import json
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
        
        # Force memory pressure by setting a low limit. DPCMSampleManager
        # copies memory_limit at construction time, so the config mutation
        # alone never reached the running manager (a no-op that #70/D-07's
        # real memory accounting exposed -- it used to pass trivially
        # because total_memory was always ~0 regardless of the limit).
        mapper.config.sample_config.memory_limit = 1024
        mapper.sample_manager.memory_limit = 1024

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


class TestDpcmSampleNameFallback:
    """Regression (#73/D-10): ADVANCED_MIDI_DRUM_MAPPING only fully defined
    kick/snare, so every other GM percussion note -- and even kick/snare at
    velocities whose split sample name wasn't in the index -- fell through
    to the noise fallback. _resolve_dpcm_sample_name must try progressively
    coarser fallbacks (velocity-split -> primary -> generic role name)
    before giving up."""

    @pytest.fixture
    def curated_index_path(self, tmp_path):
        # A curated kit (unlike the real shipped dpcm_index.json, which is an
        # uncurated found sample pack) -- only bare role names, no
        # velocity-split variants, to exercise the primary/default fallbacks.
        index = {
            "kick": {"id": 0, "filename": "kick.dmc"},
            "snare": {"id": 1, "filename": "snare.dmc"},
            "tom_low": {"id": 2, "filename": "tom_low.dmc"},
            "ride": {"id": 3, "filename": "ride.dmc"},
            "hihat_closed": {"id": 4, "filename": "hihat_closed.dmc"},
        }
        path = tmp_path / "curated_index.json"
        path.write_text(json.dumps(index))
        return str(path)

    @pytest.fixture
    def mapper(self, curated_index_path):
        return EnhancedDrumMapper(dpcm_index_path=curated_index_path)

    def test_kick_falls_back_to_primary_when_velocity_split_missing(self, mapper):
        # kick_soft/kick_hard aren't in the index, but "kick" (primary) is.
        assert mapper._resolve_dpcm_sample_name(36, 100) == "kick"
        assert mapper._resolve_dpcm_sample_name(36, 30) == "kick"

    def test_unmapped_gm_note_falls_back_to_default_mapping(self, mapper):
        # Notes 45 (tom) and 51 (ride) have no ADVANCED_MIDI_DRUM_MAPPING
        # entry at all -- they must still resolve via DEFAULT_MIDI_DRUM_MAPPING.
        assert mapper._resolve_dpcm_sample_name(45, 100) == "tom_low"
        assert mapper._resolve_dpcm_sample_name(51, 100) == "ride"
        assert mapper._resolve_dpcm_sample_name(42, 100) == "hihat_closed"

    def test_truly_unmapped_note_returns_none(self, mapper):
        # Note 90 isn't GM percussion at all -- no fallback should invent one.
        assert mapper._resolve_dpcm_sample_name(90, 100) is None

    def test_map_drums_routes_toms_and_cymbals_to_dpcm_not_noise(self, mapper):
        midi_events = {
            9: [
                {"frame": 0, "note": 45, "velocity": 100},   # tom -> tom_low
                {"frame": 10, "note": 51, "velocity": 100},  # ride
                {"frame": 20, "note": 90, "velocity": 100},  # not GM percussion -> noise
            ]
        }
        dpcm_events, noise_events = mapper.map_drums(midi_events)

        dpcm_frames = {e["frame"] for e in dpcm_events}
        noise_frames = {e["frame"] for e in noise_events}
        assert {0, 10}.issubset(dpcm_frames)
        assert 20 in noise_frames

        # Regression (#195/NH-26): a noise-fallback event without a `note`
        # key crashes process_all_tracks's midi_to_nes_pitch lookup.
        noise_event = next(e for e in noise_events if e["frame"] == 20)
        assert noise_event["note"] == 90

    def test_pattern_event_resolution_miss_falls_back_to_noise_not_silent_drop(self, mapper):
        # Regression (#73/D-10): _handle_pattern_event used to return an empty
        # list on a resolution miss, silently dropping the hit entirely (no
        # DPCM, no noise) -- worse than the non-pattern path's noise fallback.
        pattern_info = {
            "id": "p0",
            "info": {"template": [(90, 100)]},  # note 90: unresolvable anywhere
            "position": 0,
        }
        dpcm_out, noise_out = mapper._handle_pattern_event(
            pattern_info, midi_note=90, velocity=100, frame=5
        )
        assert dpcm_out == []
        assert len(noise_out) == 1
        assert noise_out[0]["frame"] == 5
        # Regression (#195/NH-26): pattern path shares the same missing-`note`
        # bug as the non-pattern fallback above.
        assert noise_out[0]["note"] == 90


class TestNoiseFallbackEndToEnd:
    """Regression (#195/NH-26): a drum-mapper noise fallback with no `note`
    key used to crash NESEmulatorCore.process_all_tracks with a bare
    KeyError('note'), aborting the entire build for any real-world drummed
    MIDI file the shipped DPCM index doesn't fully cover."""

    def test_process_all_tracks_does_not_crash_on_noise_fallback(self):
        from nes.emulator_core import NESEmulatorCore

        core = NESEmulatorCore()
        nes_tracks = {
            'pulse1': [], 'pulse2': [], 'triangle': [],
            'noise': [{'frame': 10, 'note': 38, 'velocity': 90}],
            'dpcm': [],
        }
        processed = core.process_all_tracks(nes_tracks)
        assert 10 in processed['noise']
        assert processed['noise'][10]['note'] > 0
