"""Comprehensive tests for drum_engine.py.

Tests cover:
- MIDI drum mappings (default and advanced)
- Edge cases and error handling
- Integration with enhanced drum mapper

(optimize_dpcm_samples and DrumPatternAnalyzer coverage was removed along
with the dead code itself, #368/DP-DPCM-06 -- neither had a production
caller, and DrumPatternAnalyzer's methods were unimplemented stubs.)
"""

import pytest
import json
import tempfile
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

# Add the parent directory to the path to import modules
sys.path.append(str(Path(__file__).parent.parent))

from dpcm_sampler.drum_engine import (
    DEFAULT_MIDI_DRUM_MAPPING,
    ADVANCED_MIDI_DRUM_MAPPING,
    map_drums_to_dpcm,
)


class TestDrumMappingConstants:
    """Test drum mapping constant definitions."""
    
    def test_default_midi_drum_mapping(self):
        """Test that default MIDI drum mapping is properly defined."""
        assert isinstance(DEFAULT_MIDI_DRUM_MAPPING, dict)
        assert len(DEFAULT_MIDI_DRUM_MAPPING) > 0
        
        # Check some common drum mappings
        assert DEFAULT_MIDI_DRUM_MAPPING[36] == "kick"
        assert DEFAULT_MIDI_DRUM_MAPPING[38] == "snare"
        assert DEFAULT_MIDI_DRUM_MAPPING[42] == "hihat_closed"
        assert DEFAULT_MIDI_DRUM_MAPPING[46] == "hihat_open"
        
        # All values should be strings
        for note, drum_name in DEFAULT_MIDI_DRUM_MAPPING.items():
            assert isinstance(note, int)
            assert isinstance(drum_name, str)
            assert len(drum_name) > 0

    def test_default_mapping_covers_full_gm_percussion_range(self):
        """Regression (#73/D-10): the default mapping used to define only 7
        notes (kick/snare/hihats/crash/ride), so toms, most cymbals, and
        percussion (35-81 minus those 7) had no fallback at all and always
        fell through to noise. It must now cover the full GM range."""
        for note in range(35, 82):
            assert note in DEFAULT_MIDI_DRUM_MAPPING, f"GM percussion note {note} has no default mapping"


    def test_advanced_midi_drum_mapping(self):
        """Test that advanced MIDI drum mapping is properly structured."""
        assert isinstance(ADVANCED_MIDI_DRUM_MAPPING, dict)
        assert len(ADVANCED_MIDI_DRUM_MAPPING) > 0
        
        # Check kick drum configuration
        kick_config = ADVANCED_MIDI_DRUM_MAPPING[36]
        assert kick_config["primary"] == "kick"
        assert "velocity_ranges" in kick_config
        # No "layers" key (#300/DP-05): the DMC is single-voice and can't
        # play two samples at once, so a "layers" list could only ever
        # duplicate the primary on the same frame or reference a
        # nonexistent sample name -- both removed.
        assert "layers" not in kick_config

        # Check velocity ranges structure
        velocity_ranges = kick_config["velocity_ranges"]
        assert isinstance(velocity_ranges, dict)
        for vel_range, sample_name in velocity_ranges.items():
            assert isinstance(vel_range, tuple)
            assert len(vel_range) == 2
            assert isinstance(sample_name, str)
            assert vel_range[0] <= vel_range[1]
    
    def test_velocity_range_coverage(self):
        """Test that velocity ranges cover full MIDI velocity range."""
        for note, config in ADVANCED_MIDI_DRUM_MAPPING.items():
            velocity_ranges = config["velocity_ranges"]
            
            # Sort ranges by start velocity
            sorted_ranges = sorted(velocity_ranges.keys(), key=lambda x: x[0])
            
            # Check that ranges start at 0 and end at 127
            assert sorted_ranges[0][0] == 0
            assert sorted_ranges[-1][1] == 127
            
            # Check for gaps or overlaps
            for i in range(len(sorted_ranges) - 1):
                current_end = sorted_ranges[i][1]
                next_start = sorted_ranges[i + 1][0]
                assert current_end + 1 == next_start, f"Gap or overlap in velocity ranges for note {note}"


class TestMapDrumsToDpcm:
    """Test map_drums_to_dpcm function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sample_midi_events = {
            9: [  # Drum channel
                {"frame": 0, "note": 36, "velocity": 100},   # Kick
                {"frame": 4, "note": 38, "velocity": 80},    # Snare
                {"frame": 8, "note": 42, "velocity": 60},    # Hi-hat closed
                {"frame": 12, "note": 46, "velocity": 90}    # Hi-hat open
            ]
        }
        
        # Create a temporary DPCM index file
        self.temp_dpcm_index = {
            "samples": {
                "kick": 0,
                "snare": 1,
                "hihat_closed": 2,
                "hihat_open": 3,
                "kick_soft": 4,
                "kick_hard": 5,
                "snare_soft": 6,
                "snare_hard": 7
            },
            "mappings": {
                0: {"name": "kick", "size": 256},
                1: {"name": "snare", "size": 512},
                2: {"name": "hihat_closed", "size": 128},
                3: {"name": "hihat_open", "size": 256}
            }
        }
    
    def create_temp_dpcm_index(self, index_data=None):
        """Create a temporary DPCM index file."""
        if index_data is None:
            index_data = self.temp_dpcm_index
            
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(index_data, temp_file)
        temp_file.close()
        return temp_file.name
    
    @patch('dpcm_sampler.enhanced_drum_mapper.map_drums_to_dpcm')
    def test_map_drums_to_dpcm_calls_enhanced_mapper(self, mock_enhanced_map):
        """Test that map_drums_to_dpcm delegates to enhanced mapper."""
        mock_enhanced_map.return_value = ([], [])
        temp_index_path = self.create_temp_dpcm_index()
        
        try:
            result = map_drums_to_dpcm(self.sample_midi_events, temp_index_path, use_advanced=True)
            
            # Should call enhanced mapper with correct parameters
            mock_enhanced_map.assert_called_once_with(
                self.sample_midi_events, 
                temp_index_path, 
                True
            )
            assert result == ([], [])
        finally:
            os.unlink(temp_index_path)
    
    @patch('dpcm_sampler.enhanced_drum_mapper.map_drums_to_dpcm')
    def test_map_drums_to_dpcm_basic_mode(self, mock_enhanced_map):
        """Test map_drums_to_dpcm with basic mode."""
        mock_enhanced_map.return_value = ([], [])
        temp_index_path = self.create_temp_dpcm_index()
        
        try:
            map_drums_to_dpcm(self.sample_midi_events, temp_index_path, use_advanced=False)
            
            # Should call with use_advanced=False
            mock_enhanced_map.assert_called_once_with(
                self.sample_midi_events, 
                temp_index_path, 
                False
            )
        finally:
            os.unlink(temp_index_path)
    
    @patch('dpcm_sampler.enhanced_drum_mapper.map_drums_to_dpcm')
    def test_map_drums_to_dpcm_error_handling(self, mock_enhanced_map):
        """Test error handling in map_drums_to_dpcm."""
        mock_enhanced_map.side_effect = FileNotFoundError("DPCM index not found")
        
        with pytest.raises(FileNotFoundError):
            map_drums_to_dpcm(self.sample_midi_events, "nonexistent.json")
    
    def test_map_drums_to_dpcm_import_error_handling(self):
        """Test handling of import errors."""
        # Temporarily modify sys.modules to simulate import error
        original_module = sys.modules.get('dpcm_sampler.enhanced_drum_mapper')
        sys.modules['dpcm_sampler.enhanced_drum_mapper'] = None
        
        try:
            with pytest.raises(ImportError):
                map_drums_to_dpcm(self.sample_midi_events, "dummy.json")
        finally:
            # Restore original module
            if original_module:
                sys.modules['dpcm_sampler.enhanced_drum_mapper'] = original_module
            else:
                sys.modules.pop('dpcm_sampler.enhanced_drum_mapper', None)


class TestDrumEngineMainExecution:
    """Test main execution functionality.

    Regression (#395/REG-25): both tests here used to reimplement the
    `__main__` block's logic inline (with `builtins.open`/`json.load` mocked
    so the literal 'test_midi.json' path was never touched) instead of
    invoking the module, and wrapped the success case in a blanket
    `try: ... except Exception: pass` that passed even if the reimplemented
    logic diverged from the real block entirely. Both now execute
    `dpcm_sampler/drum_engine.py` for real via `runpy.run_module`, so a
    broken `sys.argv` handling, a wrong `map_drums_to_dpcm` call signature,
    or a crash on real file I/O would actually fail the test.
    """

    # run_module (not run_path) so drum_engine.py's `from .enhanced_drum_mapper
    # import ...` relative import resolves through the real dpcm_sampler
    # package instead of raising ImportError as a detached top-level script.
    DRUM_ENGINE_MODULE = "dpcm_sampler.drum_engine"

    def _run_main(self):
        # The module is already imported at this file's top (`from
        # dpcm_sampler.drum_engine import ...`), so it's already in
        # sys.modules; drop it first so run_module executes a genuinely
        # fresh module body instead of just warning about the stale entry.
        sys.modules.pop(self.DRUM_ENGINE_MODULE, None)
        runpy.run_module(self.DRUM_ENGINE_MODULE, run_name="__main__")

    def test_main_execution_insufficient_args(self, capsys, monkeypatch):
        """Too few argv entries must print the usage line and exit(1)."""
        monkeypatch.setattr(sys, "argv", ["drum_engine.py"])
        with pytest.raises(SystemExit) as exc:
            self._run_main()
        assert exc.value.code == 1
        assert ("Usage: python drum_engine.py <parsed_midi.json> "
                "<dpcm_index.json>") in capsys.readouterr().out

    def test_main_execution_success(self, tmp_path, capsys, monkeypatch):
        """A real parsed-MIDI JSON + a real dpcm_index.json must run the
        actual `__main__` block end-to-end and print valid JSON output."""
        midi_json = tmp_path / "test_midi.json"
        midi_json.write_text(json.dumps({
            "9": [  # Drum channel
                {"frame": 0, "note": 36, "velocity": 100},   # Kick
                {"frame": 4, "note": 38, "velocity": 80},    # Snare
            ]
        }))
        dpcm_index = tmp_path / "test_dpcm.json"
        dpcm_index.write_text(json.dumps({
            "kick": {"id": 0, "filename": "kick.dmc"},
            "snare": {"id": 1, "filename": "snare.dmc"},
        }))

        monkeypatch.setattr(
            sys, "argv",
            ["drum_engine.py", str(midi_json), str(dpcm_index)])
        self._run_main()

        output = capsys.readouterr().out
        events = json.loads(output)  # must be valid JSON, not garbage
        # map_drums_to_dpcm returns (dpcm_events, noise_events).
        assert isinstance(events, list)
        assert len(events) == 2
        dpcm_events, noise_events = events
        assert isinstance(dpcm_events, list)
        assert isinstance(noise_events, list)


class TestDrumEngineIntegration:
    """Integration tests for drum engine functionality."""
    
    def setup_method(self):
        """Set up integration test fixtures."""
        self.complex_midi_events = {
            9: [  # Drum channel
                # Bar 1: Basic rock pattern
                {"frame": 0, "note": 36, "velocity": 127},    # Kick hard
                {"frame": 2, "note": 42, "velocity": 60},     # Hi-hat soft
                {"frame": 4, "note": 38, "velocity": 100},    # Snare medium
                {"frame": 6, "note": 42, "velocity": 60},     # Hi-hat soft
                
                # Bar 2: Variation with fills
                {"frame": 8, "note": 36, "velocity": 100},    # Kick medium
                {"frame": 10, "note": 42, "velocity": 80},    # Hi-hat medium
                {"frame": 12, "note": 38, "velocity": 127},   # Snare hard
                {"frame": 13, "note": 40, "velocity": 90},    # Snare rim
                {"frame": 14, "note": 46, "velocity": 100},   # Hi-hat open
                
                # Bar 3: Complex pattern
                {"frame": 16, "note": 36, "velocity": 110},   # Kick
                {"frame": 18, "note": 36, "velocity": 80},    # Kick ghost
                {"frame": 20, "note": 38, "velocity": 120},   # Snare
                {"frame": 22, "note": 49, "velocity": 90},    # Crash
                {"frame": 24, "note": 51, "velocity": 70},    # Ride
            ]
        }
    
    @patch('dpcm_sampler.enhanced_drum_mapper.map_drums_to_dpcm')
    def test_integration_complex_drum_pattern(self, mock_enhanced_map):
        """Test integration with complex drum patterns."""
        # Mock enhanced mapper to return realistic results
        mock_enhanced_map.return_value = (
            [  # DPCM events
                {"frame": 0, "sample_id": 0, "velocity": 127},   # Kick hard
                {"frame": 4, "sample_id": 1, "velocity": 100},   # Snare medium
                {"frame": 8, "sample_id": 2, "velocity": 100},   # Kick medium  
                {"frame": 12, "sample_id": 3, "velocity": 127},  # Snare hard
            ],
            [  # Noise fallback events
                {"frame": 2, "velocity": 60},    # Hi-hat soft
                {"frame": 6, "velocity": 60},    # Hi-hat soft
                {"frame": 10, "velocity": 80},   # Hi-hat medium
                {"frame": 14, "velocity": 100},  # Hi-hat open
                {"frame": 22, "velocity": 90},   # Crash
                {"frame": 24, "velocity": 70},   # Ride
            ]
        )
        
        temp_index_path = "dummy_index.json"
        dpcm_events, noise_events = map_drums_to_dpcm(
            self.complex_midi_events, 
            temp_index_path, 
            use_advanced=True
        )
        
        # Verify enhanced mapper was called correctly
        mock_enhanced_map.assert_called_once_with(
            self.complex_midi_events, 
            temp_index_path, 
            True
        )
        
        # Verify returned data structure
        assert len(dpcm_events) == 4
        assert len(noise_events) == 6
        
        # Verify DPCM events have required fields
        for event in dpcm_events:
            assert "frame" in event
            assert "sample_id" in event
            assert "velocity" in event
        
        # Verify noise events have required fields
        for event in noise_events:
            assert "frame" in event
            assert "velocity" in event
            assert "sample_id" not in event


if __name__ == "__main__":
    pytest.main([__file__])
