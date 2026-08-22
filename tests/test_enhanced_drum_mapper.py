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
        
    def test_map_drums_reads_volume_key_not_just_velocity(self, config):
        """Real parsed MIDI events (tracker/parser_fast.py) carry 'volume',
        never 'velocity' -- map_drums used to guard exclusively on
        e.get('velocity', 0), which is always 0 for real input, so every
        event was skipped before ever reaching sample resolution
        (#DP-DPCM-12: legacy-mode drum detection was dead code on real
        input). Confirm 'volume'-keyed events now actually produce output.
        """
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        real_parser_shaped_events = {
            9: [
                {"note": 36, "volume": 100, "frame": 0},  # Bass drum
                {"note": 38, "volume": 90, "frame": 30},  # Snare
            ]
        }

        dpcm_events, noise_events = mapper.map_drums(real_parser_shaped_events)

        # Both hits resolve to DPCM (kick_hard id=2 at velocity 100,
        # snare_hard id=6 at velocity 90 in the test catalog), none fall
        # through to noise -- pin the routing and sample identity, not
        # just the combined count (#471/REG-30).
        assert noise_events == []
        assert [e['sample_id'] for e in dpcm_events] == [2, 6]
        assert [e['frame'] for e in dpcm_events] == [0, 30]

    def test_map_drums_still_skips_genuine_zero_velocity_events(self, config):
        """A real note-off (volume=0) must still be skipped -- the fix must
        not turn every event into a hit regardless of velocity."""
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        events = {
            9: [
                {"note": 36, "volume": 100, "frame": 0},
                {"note": 36, "volume": 0, "frame": 5},  # note-off, must be skipped
            ]
        }

        dpcm_events, noise_events = mapper.map_drums(events)

        assert len(dpcm_events) + len(noise_events) == 1

    def test_map_drums_skips_melodic_notes_on_real_input(self, config):
        """A drumless melodic track parsed by tracker/parser_fast.py carries
        'channel' != 9 on every event. Before the channel filter, map_drums's
        only guard was volume > 0, so every melodic note-on (most sit in
        GM's 35-81 percussion range) was resolved as a phantom drum hit
        (#425)."""
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        melodic_track_events = {
            "Piano": [
                {"note": 60, "volume": 100, "frame": 0, "channel": 0},
                {"note": 64, "volume": 90, "frame": 30, "channel": 0},
                {"note": 67, "volume": 80, "frame": 60, "channel": 0},
            ]
        }

        dpcm_events, noise_events = mapper.map_drums(melodic_track_events)

        assert dpcm_events == []
        assert noise_events == []

    def test_map_drums_separates_channel_9_from_melodic_within_one_track(self, config):
        """A Type-0 MIDI (or any multi-channel track) puts every channel's
        events in one track's event list -- per-event 'channel' must decide
        drum vs. melodic, not the outer track-name key (#425)."""
        mapper = EnhancedDrumMapper(
            dpcm_index_path="tests/fixtures/test_dpcm_index.json",
            config=config
        )
        mixed_track_events = {
            "Track 0": [
                {"note": 36, "volume": 100, "frame": 0, "channel": 9},   # kick
                {"note": 60, "volume": 100, "frame": 30, "channel": 0},  # melodic, ignore
                {"note": 38, "volume": 90, "frame": 60, "channel": 9},   # snare
            ]
        }

        dpcm_events, noise_events = mapper.map_drums(mixed_track_events)

        assert len(dpcm_events) + len(noise_events) == 2

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

    def test_pattern_event_honors_use_advanced_false(self, curated_index_path):
        """Regression (#202/D-16): _handle_pattern_event called
        _resolve_dpcm_sample_name with no third argument, so it always used
        the default use_advanced=True regardless of what map_drums's caller
        passed -- a caller explicitly asking for use_advanced=False still
        got advanced velocity-split resolution for any pattern-matched hit."""
        # This index has both the plain role name and the advanced
        # velocity-split name, so the two modes resolve to different ids.
        index = json.loads(open(curated_index_path).read())
        index["kick_soft"] = {"id": 10, "filename": "kick_soft.dmc"}
        path = curated_index_path.replace("curated_index.json", "curated_index2.json")
        with open(path, "w") as f:
            json.dump(index, f)
        mapper = EnhancedDrumMapper(dpcm_index_path=path)

        pattern_info = {
            "id": "p0",
            "info": {"template": [(36, 30)]},  # kick, soft velocity
            "position": 0,
        }

        # use_advanced=True (default): resolves via ADVANCED_MIDI_DRUM_MAPPING's
        # velocity split -> "kick_soft" (id 10).
        dpcm_out, _ = mapper._handle_pattern_event(
            pattern_info, midi_note=36, velocity=30, frame=5, use_advanced=True
        )
        assert dpcm_out[0]["sample_id"] == 10

        # use_advanced=False must skip the velocity split entirely and
        # resolve via DEFAULT_MIDI_DRUM_MAPPING's plain "kick" (id 0).
        dpcm_out, _ = mapper._handle_pattern_event(
            pattern_info, midi_note=36, velocity=30, frame=5, use_advanced=False
        )
        assert dpcm_out[0]["sample_id"] == 0

    def test_map_drums_use_advanced_false_reaches_pattern_path(self, curated_index_path):
        """End-to-end (#202/D-16): map_drums(..., use_advanced=False) must
        keep that setting for hits that land inside a detected drum
        pattern, not just the non-pattern path."""
        index = json.loads(open(curated_index_path).read())
        index["kick_soft"] = {"id": 10, "filename": "kick_soft.dmc"}
        path = curated_index_path.replace("curated_index.json", "curated_index3.json")
        with open(path, "w") as f:
            json.dump(index, f)
        mapper = EnhancedDrumMapper(dpcm_index_path=path)

        # A repeating kick+snare pattern so DrumPatternDetector flags later
        # occurrences as pattern-matched (exercising _handle_pattern_event).
        midi_events = {
            9: [
                {"frame": i * 4 + off, "note": note, "velocity": 30}
                for i in range(6)
                for off, note in ((0, 36), (2, 38))
            ]
        }
        dpcm_events, _ = mapper.map_drums(midi_events, use_advanced=False)
        kick_ids = {e["sample_id"] for e in dpcm_events
                    if e["frame"] % 4 == 0}
        # Every kick hit (pattern-matched or not) must resolve to "kick"
        # (id 0), never the advanced "kick_soft" (id 10) split.
        assert 10 not in kick_ids
        assert kick_ids == {0}


class TestDpcmRoleAliasFallback:
    """Regression (#315/DP-07, extended by #340/DP-DPCM-01): DEFAULT_MIDI_
    DRUM_MAPPING produces 40 distinct role names, but the shipped
    dpcm_index.json only has 26 of them under an identical key -- 9 of the
    other 14 have a real (#315) or reasonably-close (#340: splash -> crash,
    triangle_mute/open -> "DPCM triangle") sample under a different filename
    that _resolve_dpcm_sample_name never tried, so they always fell back to
    noise despite a usable sample existing. The remaining 1 (vibraslap) is a
    genuine asset gap with no matching or close sample anywhere in the
    catalog."""

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
            "crash": {"id": 9, "filename": "crash.dmc"},
            "DPCM triangle": {"id": 10, "filename": "DPCM triangle.dmc"},
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
        (55, "crash"),               # splash (#340)
        (71, "whistle1"),            # whistle_short
        (72, "whistle2"),            # whistle_long
        (73, "guiro1"),              # guiro_short
        (74, "guiro2"),              # guiro_long
        (76, "mario_2_woodblock"),   # woodblock_hi
        (77, "mario_2_woodblock"),   # woodblock_lo
        (78, "cuica1"),              # cuica_mute
        (79, "cuica2"),              # cuica_open
        (80, "DPCM triangle"),       # triangle_mute (#340)
        (81, "DPCM triangle"),       # triangle_open (#340)
    ])
    def test_aliased_role_resolves_to_catalog_sample(self, mapper, note, expected_sample):
        assert mapper._resolve_dpcm_sample_name(note, 100, use_advanced=False) == expected_sample

    def test_true_asset_gap_still_falls_back_to_none(self, mapper):
        # vibraslap has no sample (or reasonably-close alias target) anywhere
        # in the catalog -- aliasing must not invent one.
        assert mapper._resolve_dpcm_sample_name(58, 100, use_advanced=False) is None

    def test_alias_does_not_invent_a_sample_when_its_target_is_also_missing(self, tmp_path):
        # A catalog that has NEITHER the identical name NOR the alias target
        # (e.g. no "crash", no "DPCM triangle") must still fall back to None
        # for splash/triangle -- aliasing only helps when the target sample
        # genuinely exists.
        index = {"unrelated": {"id": 0, "filename": "unrelated.dmc"}}
        path = tmp_path / "sparse_index.json"
        path.write_text(json.dumps(index))
        mapper = EnhancedDrumMapper(dpcm_index_path=str(path))
        for note in (55, 58, 80, 81):
            assert mapper._resolve_dpcm_sample_name(note, 100, use_advanced=False) is None

    def test_shipped_catalog_closes_exactly_nine_of_fourteen_gaps(self):
        index_path = REPO_ROOT / "dpcm_index.json"
        if not index_path.exists():
            pytest.skip("shipped dpcm_index.json not present in this checkout")

        mapper = EnhancedDrumMapper(dpcm_index_path=str(index_path))
        missing = [
            note for note in range(35, 82)
            if mapper._resolve_dpcm_sample_name(note, 100, use_advanced=False) is None
        ]
        # Only the 1 true asset gap (vibraslap) should remain unresolved on
        # the real shipped catalog.
        assert set(missing) == {58}


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

    def test_single_kick_and_snare_hit_each_yield_exactly_one_dpcm_event(self, mapper):
        """Regression (#300/DP-05): _handle_layered_samples used to append a
        duplicate of the primary sample on the same frame for kick/snare
        (the DMC is single-voice and can't actually layer -- see
        docs/APU_DMC_REFERENCE.md §1), which the same-frame collapse then
        silently discarded with a misleading "note dropped" warning. A
        single kick or snare hit must now yield exactly one DPCM event."""
        midi_events = {
            9: [
                {"frame": 0, "note": 36, "velocity": 100},   # kick -> id 1318
                {"frame": 10, "note": 38, "velocity": 100},  # snare -> id 1620
            ]
        }
        dpcm_events, noise_events = mapper.map_drums(midi_events)

        assert noise_events == []
        assert len(dpcm_events) == 2  # one per hit, no layered duplicate
        by_frame = {e["frame"]: e["sample_id"] for e in dpcm_events}
        assert by_frame[0] == 1318
        assert by_frame[10] == 1620

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


class TestSampleManagerBackfillsRealSize:
    """Regression (#341/DP-DPCM-02): real dpcm_index.json entries carry only
    'id' + 'filename', so DPCMSampleManager.allocate_sample always fell back
    to its placeholder default (1024 bytes) for every sample -- the
    memory-limit/eviction machinery operated on identical fictional sizes
    regardless of what was actually packed. EnhancedDrumMapper now resolves
    each sample's real on-disk size before allocating."""

    @pytest.fixture
    def dpcm_index_path(self, tmp_path):
        dmc_dir = tmp_path / "dmc"
        dmc_dir.mkdir()
        # Two very differently-sized samples so a 1024-byte placeholder
        # couldn't coincidentally match either.
        (dmc_dir / "kick.dmc").write_bytes(b"\x00" * 200)
        (dmc_dir / "snare.dmc").write_bytes(b"\x00" * 3000)
        index = {
            "kick": {"id": 0, "filename": "kick.dmc"},
            "snare": {"id": 1, "filename": "snare.dmc"},
        }
        path = tmp_path / "dpcm_index.json"
        path.write_text(json.dumps(index))
        return str(path)

    def test_allocated_sample_reflects_real_file_size(self, dpcm_index_path):
        mapper = EnhancedDrumMapper(dpcm_index_path=dpcm_index_path)
        midi_events = {
            9: [
                {"frame": 0, "note": 36, "velocity": 100},   # kick -> 200 bytes
                {"frame": 10, "note": 38, "velocity": 100},  # snare -> 3000 bytes
            ]
        }
        mapper.map_drums(midi_events)

        kick_info = mapper.sample_manager.active_samples["kick"]
        snare_info = mapper.sample_manager.active_samples["snare"]
        assert kick_info['metadata']['size'] == 200
        assert snare_info['metadata']['size'] == 3000
        # The two real sizes must differ from each other and from the old
        # 1024 placeholder -- otherwise this would pass even if the backfill
        # were a no-op that happened to still read 1024 for both.
        assert kick_info['metadata']['size'] != snare_info['metadata']['size']
        assert kick_info['metadata']['size'] != 1024
        assert snare_info['metadata']['size'] != 1024

    def test_unresolvable_sample_falls_back_to_placeholder(self, tmp_path):
        # A catalog entry whose file doesn't exist on disk must not raise --
        # allocate_sample still gets its safe placeholder default.
        index = {"ghost": {"id": 0, "filename": "missing.dmc"}}
        path = tmp_path / "dpcm_index.json"
        path.write_text(json.dumps(index))
        mapper = EnhancedDrumMapper(dpcm_index_path=str(path))
        mapper._allocate("ghost", mapper.sample_index["ghost"])
        assert mapper.sample_manager.active_samples["ghost"]['metadata']['size'] == 1024

    def test_repeated_allocation_reuses_cached_size(self, dpcm_index_path):
        """The size cache must avoid re-stat'ing the same file on every hit
        in a song that reuses one drum many times."""
        mapper = EnhancedDrumMapper(dpcm_index_path=dpcm_index_path)
        sample_data = mapper.sample_index["kick"]
        for _ in range(5):
            mapper._allocate("kick", sample_data)
        assert mapper._sample_size_cache["kick"] == 200

    def test_repeated_unresolvable_sample_only_probes_once(self, dpcm_index_path):
        """Regression (#413/DP-DPCM-07): an unresolvable sample (missing
        'filename', or a 'filename' that doesn't resolve to an existing file)
        used to skip the cache write on both early-return paths, so a drum
        that never resolves re-ran the full resolve_dpcm_sample_path
        candidate-path probe on every single occurrence in the song instead
        of just the first."""
        import dpcm_sampler.enhanced_drum_mapper as edm
        from unittest.mock import patch

        mapper = EnhancedDrumMapper(dpcm_index_path=dpcm_index_path)
        sample_data = {"id": 99, "filename": "missing.dmc"}

        with patch.object(edm, "resolve_dpcm_sample_path",
                           wraps=edm.resolve_dpcm_sample_path) as mock_resolve:
            for _ in range(5):
                assert mapper._real_sample_size("ghost", sample_data) is None
            assert mock_resolve.call_count == 1, \
                "resolve_dpcm_sample_path must only run once for a repeated unresolvable sample"
        assert mapper._sample_size_cache["ghost"] is None

    def test_repeated_no_filename_sample_never_probes(self, dpcm_index_path):
        """Sibling of the above for the other early-return path: a catalog
        entry with no 'filename' key at all must also be cached as a miss,
        not just the 'filename' -> resolution-failure path."""
        mapper = EnhancedDrumMapper(dpcm_index_path=dpcm_index_path)
        sample_data = {"id": 99}  # no 'filename' key

        assert mapper._real_sample_size("no_filename", sample_data) is None
        assert "no_filename" in mapper._sample_size_cache
        assert mapper._sample_size_cache["no_filename"] is None
        # Second call must hit the cache fast-path, not re-derive anything.
        assert mapper._real_sample_size("no_filename", sample_data) is None
