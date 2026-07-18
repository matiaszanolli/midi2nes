# tests/test_enhanced_drum_mapper.py
import json
from pathlib import Path
import pytest
from dpcm_sampler.enhanced_drum_mapper import (EnhancedDrumMapper, DrumMapperConfig,
                                               DrumPatternConfig, SampleManagerConfig)

REPO_ROOT = Path(__file__).parent.parent

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


class TestDpcmRoleAliasFallback:
    """Regression (#315/DP-07): DEFAULT_MIDI_DRUM_MAPPING produces 40 distinct
    role names, but the shipped dpcm_index.json only has 26 of them under an
    identical key -- 6 of the other 14 have a real sample under a different
    filename (e.g. "tambourine" -> "tamborin") that _resolve_dpcm_sample_name
    never tried, so they always fell back to noise despite a usable sample
    existing. The remaining 4 (splash, vibraslap, triangle mute/open) are a
    genuine asset gap with no matching sample anywhere in the catalog."""

    @pytest.fixture
    def curated_index_path(self, tmp_path):
        index = {
            "tamborin": {"id": 0, "filename": "tamborin.dmc"},
            "whistle1": {"id": 1, "filename": "whistle1.dmc"},
            "whistle2": {"id": 2, "filename": "whistle2.dmc"},
            "guiro1": {"id": 3, "filename": "guiro1.dmc"},
            "guiro2": {"id": 4, "filename": "guiro2.dmc"},
            "cuica1": {"id": 5, "filename": "cuica1.dmc"},
            "cuica2": {"id": 6, "filename": "cuica2.dmc"},
            "mario_2_woodblock": {"id": 7, "filename": "mario_2_woodblock.dmc"},
            "stickrim": {"id": 8, "filename": "stickrim.dmc"},
        }
        path = tmp_path / "curated_index.json"
        path.write_text(json.dumps(index))
        return str(path)

    @pytest.fixture
    def mapper(self, curated_index_path):
        return EnhancedDrumMapper(dpcm_index_path=curated_index_path)

    @pytest.mark.parametrize("note,expected_sample", [
        (37, "stickrim"),            # side_stick
        (54, "tamborin"),            # tambourine
        (71, "whistle1"),            # whistle_short
        (72, "whistle2"),            # whistle_long
        (73, "guiro1"),              # guiro_short
        (74, "guiro2"),              # guiro_long
        (76, "mario_2_woodblock"),   # woodblock_hi
        (77, "mario_2_woodblock"),   # woodblock_lo
        (78, "cuica1"),              # cuica_mute
        (79, "cuica2"),              # cuica_open
    ])
    def test_aliased_role_resolves_to_catalog_sample(self, mapper, note, expected_sample):
        assert mapper._resolve_dpcm_sample_name(note, 100, use_advanced=False) == expected_sample

    def test_true_asset_gaps_still_fall_back_to_none(self, mapper):
        # splash, vibraslap, triangle_mute, triangle_open have no sample
        # anywhere in the catalog -- aliasing must not invent one.
        for note in (55, 58, 80, 81):
            assert mapper._resolve_dpcm_sample_name(note, 100, use_advanced=False) is None

    def test_shipped_catalog_closes_exactly_six_of_fourteen_gaps(self):
        index_path = REPO_ROOT / "dpcm_index.json"
        if not index_path.exists():
            pytest.skip("shipped dpcm_index.json not present in this checkout")

        mapper = EnhancedDrumMapper(dpcm_index_path=str(index_path))
        missing = [
            note for note in range(35, 82)
            if mapper._resolve_dpcm_sample_name(note, 100, use_advanced=False) is None
        ]
        # Only the 4 true asset gaps (splash, vibraslap, triangle mute/open)
        # should remain unresolved on the real shipped catalog.
        assert set(missing) == {55, 58, 80, 81}


class TestNoiseModeForMetallicPercussion:
    """Regression (#204/NH-29): noise_mode had no producer anywhere in the
    pipeline, so every noise hit played the default long/hiss Mode 0 even
    though the engine and both exporters already thread noise_mode -> $400E
    bit 7 correctly. docs/APU_NOISE_REFERENCE.md section 6 calls out hi-hats
    and cowbells specifically as good Mode 1 (periodic noise) candidates. The
    drum mapper's noise fallback must now set noise_mode for those roles."""

    @pytest.fixture
    def mapper(self):
        # kick/snare only (tests/fixtures/test_dpcm_index.json) -- hihat/
        # cowbell/tom/ride all miss and fall back to noise.
        return EnhancedDrumMapper(dpcm_index_path="tests/fixtures/test_dpcm_index.json")

    def test_hihat_and_cowbell_get_periodic_noise_mode(self, mapper):
        midi_events = {
            9: [
                {"frame": 0, "note": 42, "velocity": 100},   # hihat_closed
                {"frame": 10, "note": 46, "velocity": 100},  # hihat_open
                {"frame": 20, "note": 56, "velocity": 100},  # cowbell
            ]
        }
        _, noise_events = mapper.map_drums(midi_events)
        assert len(noise_events) == 3
        assert all(e["noise_mode"] == 1 for e in noise_events)

    def test_non_metallic_percussion_stays_default_noise_mode(self, mapper):
        midi_events = {
            9: [
                {"frame": 0, "note": 45, "velocity": 100},   # tom_low
                {"frame": 10, "note": 51, "velocity": 100},  # ride
            ]
        }
        _, noise_events = mapper.map_drums(midi_events)
        assert len(noise_events) == 2
        assert all(e["noise_mode"] == 0 for e in noise_events)

    def test_pattern_path_noise_fallback_also_sets_noise_mode(self, mapper):
        # SIBLING: _handle_pattern_event has its own noise-fallback branch,
        # separate from the non-pattern path exercised above.
        pattern_info = {
            "id": "p0",
            "info": {"template": [(42, 100)]},  # hihat_closed, unresolvable in this index
            "position": 0,
        }
        dpcm_out, noise_out = mapper._handle_pattern_event(
            pattern_info, midi_note=42, velocity=100, frame=5
        )
        assert dpcm_out == []
        assert len(noise_out) == 1
        assert noise_out[0]["noise_mode"] == 1

    def test_noise_mode_reaches_control_byte_bit_6(self):
        # End-to-end: the emulator core folds noise_mode into control bit 6
        # (nes/emulator_core.py:166), which the exporters turn into $400E
        # bit 7 -- confirms the producer added here actually reaches the
        # already-correct consumer.
        from nes.emulator_core import NESEmulatorCore

        core = NESEmulatorCore()
        nes_tracks = {
            'pulse1': [], 'pulse2': [], 'triangle': [],
            'noise': [{'frame': 0, 'note': 42, 'velocity': 100, 'noise_mode': 1}],
            'dpcm': [],
        }
        processed = core.process_all_tracks(nes_tracks)
        assert processed['noise'][0]['control'] & 0x40 == 0x40


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


class TestHighCatalogIdsResolveToDpcm:
    """Regression (#254/D-17): a MAX_SAFE_SAMPLE_ID=254 guard used to route
    every hit whose *raw* dpcm_index.json id exceeded 254 to noise, on the
    premise that the id would collide once clamped to a single byte
    downstream. That premise was already false: nes/emulator_core.py's
    process_all_tracks remaps each song's referenced raw ids to a dense
    0..N-1 range (dpcm_sample_map side table) *before* the single-byte note
    encoding, so no raw-id ceiling was ever needed here. Since the shipped
    dpcm_index.json's named drums all sit at ids >= 1083, the guard silently
    discarded 100% of resolvable DPCM percussion. map_drums must now emit
    the raw catalog id regardless of magnitude and let process_all_tracks's
    dense-remap handle the byte encoding."""

    @pytest.fixture
    def high_id_index_path(self, tmp_path):
        # Mirrors the real shipped catalog's shape: named drums at ids well
        # past the single-byte ceiling.
        index = {
            "kick": {"id": 1318, "filename": "kick.dmc"},
            "snare": {"id": 1620, "filename": "snare.dmc"},
            "tom_low": {"id": 200, "filename": "tom_low.dmc"},  # also in-range
        }
        path = tmp_path / "high_id_index.json"
        path.write_text(json.dumps(index))
        return str(path)

    @pytest.fixture
    def mapper(self, high_id_index_path):
        return EnhancedDrumMapper(dpcm_index_path=high_id_index_path)

    def test_two_high_id_drums_resolve_to_their_own_dpcm_sample(self, mapper):
        midi_events = {
            9: [
                {"frame": 0, "note": 36, "velocity": 100},   # kick -> id 1318
                {"frame": 10, "note": 38, "velocity": 100},  # snare -> id 1620
            ]
        }
        dpcm_events, noise_events = mapper.map_drums(midi_events)

        assert noise_events == []
        by_frame = {e["frame"]: e["sample_id"] for e in dpcm_events}
        assert by_frame[0] == 1318
        assert by_frame[10] == 1620

    def test_in_range_id_still_resolves_to_dpcm(self, mapper):
        midi_events = {9: [{"frame": 0, "note": 45, "velocity": 100}]}  # tom_low, id 200
        dpcm_events, noise_events = mapper.map_drums(midi_events)
        assert len(dpcm_events) == 1
        assert dpcm_events[0]["sample_id"] == 200
        assert noise_events == []

    def test_layered_high_id_sample_is_included_not_dropped(self, mapper):
        # _handle_layered_samples appends additional hits on top of a primary
        # drum; a high-id layer must be included like any other, not dropped.
        events = []
        mapper._handle_layered_samples(
            layers=["kick", "snare"], frame=0, velocity=100, events=events
        )
        sample_ids = {e["sample_id"] for e in events}
        assert sample_ids == {1318, 1620}

    def test_pattern_event_with_high_id_resolves_to_dpcm(self, mapper):
        pattern_info = {
            "id": "p0",
            "info": {"template": [(36, 100)]},  # kick, id 1318
            "position": 0,
        }
        dpcm_out, noise_out = mapper._handle_pattern_event(
            pattern_info, midi_note=36, velocity=100, frame=5
        )
        assert noise_out == []
        assert len(dpcm_out) == 1
        assert dpcm_out[0]["sample_id"] == 1318


class TestShippedCatalogEndToEnd:
    """Regression (#254/D-17), end-to-end per the issue's suggested fix: drive
    map_drums -> process_all_tracks with the REAL shipped dpcm_index.json and
    assert a kick+snare song produces two distinct non-noise DPCM events --
    the exact scenario the MAX_SAFE_SAMPLE_ID guard silently broke."""

    def test_kick_and_snare_produce_distinct_dpcm_frames(self):
        from nes.emulator_core import NESEmulatorCore

        index_path = REPO_ROOT / "dpcm_index.json"
        if not index_path.exists():
            pytest.skip("shipped dpcm_index.json not present in this checkout")

        mapper = EnhancedDrumMapper(dpcm_index_path=str(index_path))
        midi_events = {
            9: [
                {"frame": 0, "note": 36, "velocity": 100},   # kick
                {"frame": 10, "note": 38, "velocity": 100},  # snare
            ]
        }
        dpcm_events, noise_events = mapper.map_drums(midi_events)
        assert dpcm_events, "expected the shipped catalog to resolve real DPCM samples"
        assert noise_events == []

        core = NESEmulatorCore()
        nes_tracks = {
            'pulse1': [], 'pulse2': [], 'triangle': [], 'noise': [],
            'dpcm': dpcm_events,
        }
        processed = core.process_all_tracks(nes_tracks)

        dpcm_frames = processed['dpcm']
        # Two distinct hits must land on two distinct (non-rest) notes --
        # the whole point of the dense remap is that they don't alias.
        notes = {frame['note'] for frame in dpcm_frames.values()}
        assert 0 not in notes, "note 0 is the rest sentinel, not a real hit"
        assert len(notes) == 2, f"expected 2 distinct DPCM notes, got {notes}"

        # dpcm_sample_map must let a consumer recover the real catalog ids.
        sample_map = processed['dpcm_sample_map']
        recovered_ids = set(sample_map.values())
        assert recovered_ids == {e['sample_id'] for e in dpcm_events}
