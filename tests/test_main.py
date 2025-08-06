"""Comprehensive tests for main.py CLI functionality.

Tests cover:
- Argument parsing for all subcommands
- Individual command functions (parse, map, frames, export, etc.)
- Configuration management commands
- Song bank management commands
- Benchmark commands
- Error handling and edge cases
- Version handling and help text
- Integration scenarios
"""

import pytest
import json
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
from argparse import Namespace

# Add the parent directory to the path to import modules
sys.path.append(str(Path(__file__).parent.parent))

import main
from main import (
    run_parse, run_map, run_frames, run_prepare, run_export, 
    run_detect_patterns, run_song_add, run_song_list, run_song_remove,
    load_config, run_config_init, run_config_validate,
    run_benchmark, run_benchmark_memory, main
)


class TestMainArgumentParsing:
    """Test argument parsing functionality."""
    
    def test_version_argument(self):
        """Test --version argument."""
        with patch('sys.argv', ['main.py', '--version']):
            with pytest.raises(SystemExit):
                main()
    
    def test_help_argument(self):
        """Test --help argument."""
        with patch('sys.argv', ['main.py', '--help']):
            with pytest.raises(SystemExit):
                main()
    
    def test_verbose_argument_parsing(self):
        """Test verbose flag parsing."""
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            with patch('argparse.ArgumentParser.print_help') as mock_help:
                mock_args = Namespace(verbose=True, command=None)
                mock_parse.return_value = mock_args
                
                main()
                mock_help.assert_called_once()
    
    def test_no_command_shows_help(self):
        """Test that no command shows help."""
        with patch('sys.argv', ['main.py']):
            with patch('argparse.ArgumentParser.print_help') as mock_help:
                main()
                mock_help.assert_called_once()


class TestRunParse:
    """Test run_parse command."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_input = self.temp_dir / "test.mid"
        self.test_output = self.temp_dir / "test.json"
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.parse_midi_to_frames')
    @patch('builtins.print')
    def test_run_parse_success(self, mock_print, mock_parse):
        """Test successful MIDI parsing."""
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}}
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_parse(args)
        
        mock_parse.assert_called_once_with(str(self.test_input))
        assert self.test_output.exists()
        
        # Verify JSON content
        content = json.loads(self.test_output.read_text())
        assert "events" in content
        
        mock_print.assert_called_once_with(f"[OK] Parsed MIDI -> {args.output}")
    
    @patch('main.parse_midi_to_frames')
    def test_run_parse_error_handling(self, mock_parse):
        """Test parse error handling."""
        mock_parse.side_effect = Exception("Parse error")
        args = Namespace(input="nonexistent.mid", output=str(self.test_output))
        
        with pytest.raises(Exception, match="Parse error"):
            run_parse(args)


class TestRunMap:
    """Test run_map command."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_input = self.temp_dir / "parsed.json"
        self.test_output = self.temp_dir / "mapped.json"
        
        # Create test input file
        test_data = {"events": {"0": [{"frame": 0, "note": 60}]}}
        self.test_input.write_text(json.dumps(test_data))
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.assign_tracks_to_nes_channels')
    @patch('builtins.print')
    def test_run_map_success(self, mock_print, mock_assign):
        """Test successful track mapping."""
        mock_assign.return_value = {"channel_0": [{"frame": 0, "note": 60}]}
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_map(args)
        
        mock_assign.assert_called_once_with({"0": [{"frame": 0, "note": 60}]}, 'dpcm_index.json')
        assert self.test_output.exists()
        
        content = json.loads(self.test_output.read_text())
        assert "channel_0" in content
        
        mock_print.assert_called_once_with(f"[OK] Mapped tracks -> {args.output}")
    
    def test_run_map_invalid_json(self):
        """Test mapping with invalid JSON input."""
        self.test_input.write_text("invalid json")
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        with pytest.raises(json.JSONDecodeError):
            run_map(args)
    
    def test_run_map_missing_file(self):
        """Test mapping with missing input file."""
        args = Namespace(input="nonexistent.json", output=str(self.test_output))
        
        with pytest.raises(FileNotFoundError):
            run_map(args)


class TestRunFrames:
    """Test run_frames command."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_input = self.temp_dir / "mapped.json"
        self.test_output = self.temp_dir / "frames.json"
        
        # Create test input file
        test_data = {"channel_0": [{"frame": 0, "note": 60}]}
        self.test_input.write_text(json.dumps(test_data))
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.NESEmulatorCore')
    @patch('builtins.print')
    def test_run_frames_success(self, mock_print, mock_emulator_class):
        """Test successful frame generation."""
        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {"0": {"0": {"note": 60, "volume": 15}}}
        mock_emulator_class.return_value = mock_emulator
        
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_frames(args)
        
        mock_emulator_class.assert_called_once()
        mock_emulator.process_all_tracks.assert_called_once_with({"channel_0": [{"frame": 0, "note": 60}]})
        
        assert self.test_output.exists()
        content = json.loads(self.test_output.read_text())
        assert "0" in content
        
        mock_print.assert_called_once_with(f" Generated frames -> {args.output}")


class TestRunPrepare:
    """Test run_prepare command."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_input = self.temp_dir / "music.asm"
        self.test_output = self.temp_dir / "project"
        
        # Create test input file
        self.test_input.write_text("test asm content")
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.NESProjectBuilder')
    @patch('builtins.print')
    def test_run_prepare_success(self, mock_print, mock_builder_class):
        """Test successful project preparation."""
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder
        
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_prepare(args)
        
        mock_builder_class.assert_called_once_with(str(self.test_output))
        mock_builder.prepare_project.assert_called_once_with(str(self.test_input))
        
        # Check all print calls
        assert mock_print.call_count == 5
        mock_print.assert_any_call(f" Prepared NES project -> {args.output}")
        mock_print.assert_any_call(" Ready for CC65 compilation!")
    
    @patch('main.NESProjectBuilder')
    def test_run_prepare_failure(self, mock_builder_class):
        """Test failed project preparation."""
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = False
        mock_builder_class.return_value = mock_builder
        
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_prepare(args)
        
        # Should not print success messages when preparation fails
        mock_builder_class.assert_called_once_with(str(self.test_output))


class TestRunExport:
    """Test run_export command."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_input = self.temp_dir / "frames.json"
        self.test_patterns = self.temp_dir / "patterns.json"
        self.test_output = self.temp_dir / "output.asm"
        
        # Create test input files
        frames_data = {"channel_0": {"0": {"note": 60, "volume": 15}}}
        self.test_input.write_text(json.dumps(frames_data))
        
        patterns_data = {
            "patterns": {"pattern_0": [{"frame": 0, "note": 60}]},
            "references": {"channel_0": ["pattern_0"]}
        }
        self.test_patterns.write_text(json.dumps(patterns_data))
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.CA65Exporter')
    @patch('builtins.print')
    def test_run_export_ca65_with_patterns(self, mock_print, mock_exporter_class):
        """Test CA65 export with patterns."""
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter
        
        args = Namespace(
            input=str(self.test_input),
            output=str(self.test_output),
            format="ca65",
            patterns=str(self.test_patterns)
        )
        
        run_export(args)
        
        mock_exporter_class.assert_called_once()
        mock_exporter.export_tables_with_patterns.assert_called_once()
        
        # Check arguments passed to exporter
        call_args = mock_exporter.export_tables_with_patterns.call_args
        assert call_args[0][2] == {"channel_0": ["pattern_0"]}  # references
        assert call_args[0][3] == str(self.test_output)  # output path
        
        mock_print.assert_called_once_with(f" Exported CA65 ASM -> {args.output}")
    
    @patch('main.CA65Exporter')
    @patch('builtins.print')
    def test_run_export_ca65_without_patterns(self, mock_print, mock_exporter_class):
        """Test CA65 export without patterns."""
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter
        
        args = Namespace(
            input=str(self.test_input),
            output=str(self.test_output),
            format="ca65",
            patterns=None
        )
        
        run_export(args)
        
        mock_exporter_class.assert_called_once()
        mock_exporter.export_tables_with_patterns.assert_called_once()
        
        # Check that empty patterns are passed
        call_args = mock_exporter.export_tables_with_patterns.call_args
        assert call_args[0][1] == {}  # empty patterns
        assert call_args[0][2] == {}  # empty references
    
    @patch('main.NSFExporter')
    @patch('builtins.print')
    def test_run_export_nsf_format(self, mock_print, mock_exporter_class):
        """Test NSF export format."""
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter
        
        args = Namespace(
            input=str(self.test_input),
            output=str(self.test_output),
            format="nsftxt",  # This should trigger NSF export
            patterns=None
        )
        
        run_export(args)
        
        mock_exporter_class.assert_called_once()
        mock_exporter.export.assert_called_once()
        
        # Check arguments passed to NSF exporter
        call_args = mock_exporter.export.call_args
        assert call_args[1]['output_path'] == str(self.test_output)
        assert call_args[1]['song_name'] == "MIDI2NES Export"
        
        mock_print.assert_called_once_with(f" Exported NSF -> {args.output}")


class TestRunDetectPatterns:
    """Test run_detect_patterns command."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_input = self.temp_dir / "frames.json"
        self.test_output = self.temp_dir / "patterns.json"
        
        # Create test input file
        frames_data = {
            "channel_0": {
                "0": {"note": 60, "volume": 15},
                "4": {"note": 62, "volume": 14},
                "8": {"note": 64, "volume": 13}
            }
        }
        self.test_input.write_text(json.dumps(frames_data))
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.EnhancedPatternDetector')
    @patch('main.EnhancedTempoMap')
    @patch('builtins.print')
    def test_run_detect_patterns_success(self, mock_print, mock_tempo_class, mock_detector_class):
        """Test successful pattern detection."""
        # Set up mocks
        mock_tempo = Mock()
        mock_tempo_class.return_value = mock_tempo
        
        mock_detector = Mock()
        mock_detector.detect_patterns.return_value = {
            'patterns': {'pattern_0': [{'frame': 0, 'note': 60}]},
            'references': {'channel_0': ['pattern_0']},
            'stats': {'compression_ratio': 2.5}
        }
        mock_detector_class.return_value = mock_detector
        
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_detect_patterns(args)
        
        # Verify mocks were called correctly
        mock_tempo_class.assert_called_once_with(initial_tempo=500000)
        mock_detector_class.assert_called_once_with(mock_tempo, min_pattern_length=3)
        mock_detector.detect_patterns.assert_called_once()
        
        # Verify output file was created
        assert self.test_output.exists()
        content = json.loads(self.test_output.read_text())
        assert 'patterns' in content
        assert 'references' in content
        assert 'stats' in content
        assert content['stats']['compression_ratio'] == 2.5
        
        # Verify print calls
        assert mock_print.call_count == 2
        mock_print.assert_any_call(f" Detected patterns -> {args.output}")
        mock_print.assert_any_call(" Compression ratio: 2.50")
    
    def test_run_detect_patterns_empty_frames(self):
        """Test pattern detection with empty frames."""
        # Create empty frames file
        self.test_input.write_text(json.dumps({}))
        
        with patch('main.EnhancedPatternDetector') as mock_detector_class:
            with patch('main.EnhancedTempoMap'):
                mock_detector = Mock()
                mock_detector.detect_patterns.return_value = {
                    'patterns': {},
                    'references': {},
                    'stats': {'compression_ratio': 1.0}
                }
                mock_detector_class.return_value = mock_detector
                
                args = Namespace(input=str(self.test_input), output=str(self.test_output))
                run_detect_patterns(args)
                
                # Should handle empty input gracefully
                mock_detector.detect_patterns.assert_called_once_with([])


class TestSongBankCommands:
    """Test song bank management commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_bank = self.temp_dir / "songs.json"
        self.test_midi = self.temp_dir / "test.mid"
        
        # Create test MIDI file (dummy)
        self.test_midi.write_bytes(b"fake midi data")
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.SongBank')
    @patch('builtins.print')
    def test_run_song_add_new_bank(self, mock_print, mock_bank_class):
        """Test adding song to new bank."""
        mock_bank = Mock()
        mock_bank_class.return_value = mock_bank
        
        args = Namespace(
            input=str(self.test_midi),
            bank=str(self.test_bank),
            name="Test Song",
            composer="Test Composer",
            loop_point=1000,
            tags="rock,8bit",
            tempo=140
        )
        
        run_song_add(args)
        
        mock_bank_class.assert_called_once()
        # Bank file doesn't exist, so import_bank should not be called
        mock_bank.import_bank.assert_not_called()
        
        # Check metadata passed to add_song_from_midi
        expected_metadata = {
            'composer': 'Test Composer',
            'loop_point': 1000,
            'tags': ['rock', '8bit'],
            'tempo_base': 140
        }
        mock_bank.add_song_from_midi.assert_called_once_with(
            str(self.test_midi), "Test Song", expected_metadata
        )
        mock_bank.export_bank.assert_called_once_with(str(self.test_bank))
        
        mock_print.assert_called_once_with(f"Song added to bank: {args.bank}")
    
    @patch('main.SongBank')
    @patch('builtins.print')
    def test_run_song_add_existing_bank(self, mock_print, mock_bank_class):
        """Test adding song to existing bank."""
        # Create existing bank file
        self.test_bank.write_text('{"songs": {}}')
        
        mock_bank = Mock()
        mock_bank_class.return_value = mock_bank
        
        args = Namespace(
            input=str(self.test_midi),
            bank=str(self.test_bank),
            name="Test Song",
            composer=None,
            loop_point=None,
            tags=None,
            tempo=120
        )
        
        run_song_add(args)
        
        # Should import existing bank
        mock_bank.import_bank.assert_called_once_with(str(self.test_bank))
        
        # Check metadata with None values
        expected_metadata = {
            'composer': None,
            'loop_point': None,
            'tags': [],
            'tempo_base': 120
        }
        mock_bank.add_song_from_midi.assert_called_once_with(
            str(self.test_midi), "Test Song", expected_metadata
        )
    
    @patch('main.SongBank')
    @patch('builtins.print')
    def test_run_song_list_success(self, mock_print, mock_bank_class):
        """Test listing songs in bank."""
        # Create bank file
        self.test_bank.write_text('{"songs": {}}')
        
        mock_bank = Mock()
        mock_bank.songs = {
            "Song 1": {
                "metadata": {
                    "composer": "Composer 1",
                    "tags": ["rock", "8bit"],
                    "loop_point": 500
                },
                "bank": "bank_0"
            },
            "Song 2": {
                "metadata": {
                    "composer": None,
                    "tags": [],
                    "loop_point": None
                },
                "bank": "bank_1"
            }
        }
        mock_bank_class.return_value = mock_bank
        
        args = Namespace(bank=str(self.test_bank))
        
        run_song_list(args)
        
        mock_bank.import_bank.assert_called_once_with(str(self.test_bank))
        
        # Check print calls for song listing
        print_calls = mock_print.call_args_list
        assert len(print_calls) >= 6  # Header + songs + separators
        
        # Verify song information is printed
        printed_text = " ".join([str(call[0][0]) for call in print_calls])
        assert "Song 1" in printed_text
        assert "Song 2" in printed_text
        assert "Composer 1" in printed_text
        assert "rock, 8bit" in printed_text
    
    @patch('builtins.print')
    def test_run_song_list_missing_bank(self, mock_print):
        """Test listing songs with missing bank file."""
        args = Namespace(bank="nonexistent.json")
        
        run_song_list(args)
        
        mock_print.assert_called_once_with("Error: Song bank file not found: nonexistent.json")
    
    @patch('main.SongBank')
    @patch('builtins.print')
    def test_run_song_remove_success(self, mock_print, mock_bank_class):
        """Test removing song from bank."""
        # Create bank file
        self.test_bank.write_text('{"songs": {}}')
        
        mock_bank = Mock()
        mock_bank.songs = {"Test Song": {"metadata": {}, "bank": "bank_0"}}
        mock_bank_class.return_value = mock_bank
        
        args = Namespace(bank=str(self.test_bank), name="Test Song")
        
        run_song_remove(args)
        
        mock_bank.import_bank.assert_called_once_with(str(self.test_bank))
        mock_bank.export_bank.assert_called_once_with(str(self.test_bank))
        
        # Verify song was removed
        assert "Test Song" not in mock_bank.songs
        
        mock_print.assert_called_once_with("Song 'Test Song' removed from bank")
    
    @patch('main.SongBank')
    @patch('builtins.print')
    def test_run_song_remove_not_found(self, mock_print, mock_bank_class):
        """Test removing non-existent song."""
        # Create bank file
        self.test_bank.write_text('{"songs": {}}')
        
        mock_bank = Mock()
        mock_bank.songs = {}
        mock_bank_class.return_value = mock_bank
        
        args = Namespace(bank=str(self.test_bank), name="Nonexistent Song")
        
        run_song_remove(args)
        
        mock_print.assert_called_once_with("Error: Song 'Nonexistent Song' not found in bank")


class TestConfigCommands:
    """Test configuration management commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_config = self.temp_dir / "config.json"
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.ConfigManager')
    @patch('builtins.print')
    def test_run_config_init_success(self, mock_print, mock_config_class):
        """Test successful config initialization."""
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        
        args = Namespace(output=str(self.test_config))
        
        run_config_init(args)
        
        mock_config.copy_default_config_to.assert_called_once_with(str(self.test_config))
        
        assert mock_print.call_count == 2
        mock_print.assert_any_call(f"[OK] Generated default configuration -> {args.output}")
        mock_print.assert_any_call("     Edit this file to customize MIDI2NES behavior")
    
    @patch('main.ConfigManager')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_run_config_init_error(self, mock_exit, mock_print, mock_config_class):
        """Test config initialization error."""
        mock_config_class.side_effect = Exception("Config error")
        
        args = Namespace(output=str(self.test_config))
        
        run_config_init(args)
        
        mock_print.assert_called_once_with("[ERROR] Failed to generate configuration: Config error")
        mock_exit.assert_called_once_with(1)
    
    @patch('main.ConfigManager')
    @patch('builtins.print')
    def test_run_config_validate_success(self, mock_print, mock_config_class):
        """Test successful config validation."""
        mock_config = Mock()
        mock_config.get.side_effect = lambda key: {
            'processing.pattern_detection.min_length': 3,
            'performance.max_memory_mb': 512,
            'export.nsf.load_address': 0x8000
        }.get(key)
        mock_config_class.return_value = mock_config
        
        args = Namespace(config=str(self.test_config), verbose=True)
        
        run_config_validate(args)
        
        mock_config_class.assert_called_once_with(str(self.test_config))
        mock_config.validate.assert_called_once()
        
        # Check print calls
        print_calls = mock_print.call_args_list
        assert len(print_calls) >= 4
        mock_print.assert_any_call(f"[OK] Configuration file is valid: {args.config}")
    
    @patch('main.ConfigManager')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_run_config_validate_error(self, mock_exit, mock_print, mock_config_class):
        """Test config validation error."""
        mock_config = Mock()
        mock_config.validate.side_effect = Exception("Validation error")
        mock_config_class.return_value = mock_config
        
        args = Namespace(config=str(self.test_config))
        
        run_config_validate(args)
        
        mock_print.assert_called_once_with("[ERROR] Configuration validation failed: Validation error")
        mock_exit.assert_called_once_with(1)


class TestBenchmarkCommands:
    """Test benchmark commands."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_output = self.temp_dir / "benchmark_output"
        self.test_midi = self.temp_dir / "test.mid"
        
        # Create test MIDI file
        self.test_midi.write_bytes(b"fake midi data")
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.PerformanceBenchmark')
    @patch('builtins.print')
    def test_run_benchmark_with_files(self, mock_print, mock_benchmark_class):
        """Test running benchmarks with specific files."""
        # Set up mock benchmark
        mock_benchmark = Mock()
        mock_result = Mock()
        mock_result.file_path = str(self.test_midi)
        mock_result.file_size_kb = 10.5
        mock_result.total_duration_ms = 1500
        mock_result.total_memory_mb = 25.3
        mock_result.stages = [
            Mock(stage="parse", duration_ms=500, success=True),
            Mock(stage="map", duration_ms=1000, success=True)
        ]
        mock_result.midi_info = {"total_events": 100}
        mock_benchmark.run_full_pipeline.return_value = mock_result
        mock_benchmark_class.return_value = mock_benchmark
        
        args = Namespace(
            files=[str(self.test_midi)],
            output=str(self.test_output),
            memory=True
        )
        
        run_benchmark(args)
        
        # Verify benchmark was created and run
        mock_benchmark_class.assert_called_once()
        mock_benchmark.run_full_pipeline.assert_called_once_with(str(self.test_midi))
        
        # Check output directory was created
        assert self.test_output.exists()
        
        # Check results file was created
        results_file = self.test_output / "benchmark_results.json"
        assert results_file.exists()
        
        # Verify results content
        results = json.loads(results_file.read_text())
        assert "test.mid" in results
        assert results["test.mid"]["execution_time"] == 1.5
        assert results["test.mid"]["memory_peak"] == 25.3
        assert "throughput" in results["test.mid"]
        
        # Check print output
        print_calls = mock_print.call_args_list
        printed_text = " ".join([str(call[0][0]) for call in print_calls])
        assert "Memory profiling enabled" in printed_text
        assert "Benchmark completed" in printed_text
    
    @patch('main.PerformanceBenchmark')
    @patch('builtins.print')
    def test_run_benchmark_no_files(self, mock_print, mock_benchmark_class):
        """Test running benchmarks with no specific files."""
        mock_benchmark = Mock()
        mock_benchmark_class.return_value = mock_benchmark
        
        args = Namespace(
            files=[],
            output=str(self.test_output),
            memory=False
        )
        
        run_benchmark(args)
        
        # Should create synthetic test results
        results_file = self.test_output / "benchmark_results.json"
        assert results_file.exists()
        
        results = json.loads(results_file.read_text())
        assert "synthetic_test" in results
        
        # Verify print output
        print_calls = mock_print.call_args_list
        printed_text = " ".join([str(call[0][0]) for call in print_calls])
        assert "No test files specified" in printed_text
        # Check that synthetic test results are mentioned
        assert "synthetic" in printed_text.lower()
    
    @patch('main.PerformanceBenchmark')
    @patch('builtins.print')
    def test_run_benchmark_directory_input(self, mock_print, mock_benchmark_class):
        """Test running benchmarks with directory input."""
        # Create directory with MIDI files
        midi_dir = self.temp_dir / "midi_files"
        midi_dir.mkdir()
        (midi_dir / "song1.mid").write_bytes(b"fake midi 1")
        (midi_dir / "song2.midi").write_bytes(b"fake midi 2")
        
        mock_benchmark = Mock()
        mock_result = Mock()
        mock_result.file_path = "test.mid"
        mock_result.file_size_kb = 5.0
        mock_result.total_duration_ms = 800
        mock_result.total_memory_mb = 15.0
        mock_result.stages = []
        mock_result.midi_info = {"total_events": 50}
        mock_benchmark.run_full_pipeline.return_value = mock_result
        mock_benchmark_class.return_value = mock_benchmark
        
        args = Namespace(
            files=[str(midi_dir)],
            output=str(self.test_output),
            memory=False
        )
        
        run_benchmark(args)
        
        # Should find and process both MIDI files
        assert mock_benchmark.run_full_pipeline.call_count == 2
    
    @patch('main.PerformanceBenchmark')
    def test_run_benchmark_initialization_error(self, mock_benchmark_class):
        """Test benchmark initialization error."""
        mock_benchmark_class.side_effect = Exception("Benchmark initialization error")
        
        args = Namespace(
            files=[],
            output=str(self.test_output),
            memory=False
        )
        
        # The function doesn't handle initialization errors, so it should raise
        with pytest.raises(Exception, match="Benchmark initialization error"):
            run_benchmark(args)
    
    @patch('main.get_memory_usage')
    @patch('main.log_memory_usage')
    @patch('builtins.print')
    def test_run_benchmark_memory_success(self, mock_print, mock_log_memory, mock_get_memory):
        """Test memory usage reporting."""
        mock_get_memory.return_value = {
            "rss_mb": 125.5,
            "vms_mb": 256.3,
            "peak_memory_mb": 150.2,
            "available_mb": 2048.0
        }
        
        args = Namespace()
        
        run_benchmark_memory(args)
        
        mock_get_memory.assert_called_once()
        mock_log_memory.assert_called_once_with("Current Memory Usage")
        
        # Check print output
        print_calls = mock_print.call_args_list
        printed_text = " ".join([str(call[0][0]) for call in print_calls])
        assert "Memory Usage Report" in printed_text
        assert "125.5" in printed_text
        assert "256.3" in printed_text
    
    @patch('main.get_memory_usage')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_run_benchmark_memory_error(self, mock_exit, mock_print, mock_get_memory):
        """Test memory usage error handling."""
        mock_get_memory.side_effect = Exception("Memory error")
        
        args = Namespace()
        
        run_benchmark_memory(args)
        
        mock_print.assert_called_once_with("[ERROR] Memory profiling failed: Memory error")
        mock_exit.assert_called_once_with(1)


class TestLoadConfig:
    """Test load_config function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_config = self.temp_dir / "config.json"
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('main.DrumMapperConfig')
    def test_load_config_with_file(self, mock_config_class):
        """Test loading config from existing file."""
        # Create config file
        self.test_config.write_text('{"test": "config"}')
        
        mock_config = Mock()
        mock_config_class.from_file.return_value = mock_config
        
        result = load_config(str(self.test_config))
        
        mock_config_class.from_file.assert_called_once_with(str(self.test_config))
        assert result == mock_config
    
    @patch('main.DrumMapperConfig')
    def test_load_config_no_file(self, mock_config_class):
        """Test loading config with no file specified."""
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        
        result = load_config(None)
        
        mock_config_class.assert_called_once_with()
        assert result == mock_config
    
    @patch('main.DrumMapperConfig')
    def test_load_config_missing_file(self, mock_config_class):
        """Test loading config from non-existent file."""
        mock_config = Mock()
        mock_config_class.return_value = mock_config
        
        result = load_config("nonexistent.json")
        
        # Should fall back to default config
        mock_config_class.assert_called_once_with()
        mock_config_class.from_file.assert_not_called()
        assert result == mock_config


class TestMainIntegration:
    """Integration tests for main function."""
    
    @patch('sys.argv')
    @patch('main.run_parse')
    def test_main_parse_command(self, mock_run_parse, mock_argv):
        """Test main function with parse command."""
        mock_argv.__getitem__.side_effect = ['main.py', 'parse', 'input.mid', 'output.json']
        
        with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
            mock_args = Namespace(
                command='parse',
                input='input.mid',
                output='output.json',
                func=run_parse
            )
            mock_parse_args.return_value = mock_args
            
            main()
            
            mock_run_parse.assert_called_once_with(mock_args)
    
    @patch('sys.argv')
    @patch('main.run_export')
    def test_main_export_command(self, mock_run_export, mock_argv):
        """Test main function with export command."""
        mock_argv.__getitem__.side_effect = ['main.py', 'export', 'frames.json', 'output.asm', '--format', 'ca65']
        
        with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
            mock_args = Namespace(
                command='export',
                input='frames.json',
                output='output.asm',
                format='ca65',
                patterns=None,
                func=run_export
            )
            mock_parse_args.return_value = mock_args
            
            main()
            
            mock_run_export.assert_called_once_with(mock_args)
    
    @patch('sys.argv', ['main.py', 'invalid'])
    def test_main_invalid_command(self):
        """Test main function with invalid command."""
        with patch('argparse.ArgumentParser.print_help') as mock_help:
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_args = Namespace(command='invalid')
                mock_parse_args.return_value = mock_args
                
                main()
                
                mock_help.assert_called_once()
    
    def test_version_import_fallback(self):
        """Test version import fallback behavior."""
        # Test that version fallback works correctly
        with patch.dict('sys.modules', {'midi2nes': None}):
            import importlib
            # Force reimport of main module to trigger fallback
            if 'main' in sys.modules:
                del sys.modules['main']
            
            # Import should work with fallback version
            import main as main_module
            # The fallback version should be used
            assert hasattr(main_module, '__version__')


class TestErrorHandling:
    """Test error handling across main functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_run_parse_file_not_found(self):
        """Test parse with missing input file."""
        args = Namespace(input="nonexistent.mid", output="output.json")
        
        with pytest.raises(Exception):  # Should raise some kind of exception
            run_parse(args)
    
    def test_run_map_invalid_json(self):
        """Test map with invalid JSON input."""
        invalid_json_file = self.temp_dir / "invalid.json"
        invalid_json_file.write_text("invalid json content")
        
        args = Namespace(input=str(invalid_json_file), output="output.json")
        
        with pytest.raises(json.JSONDecodeError):
            run_map(args)
    
    @patch('main.EnhancedPatternDetector')
    def test_run_detect_patterns_detector_error(self, mock_detector_class):
        """Test pattern detection with detector error."""
        mock_detector = Mock()
        mock_detector.detect_patterns.side_effect = Exception("Detector error")
        mock_detector_class.return_value = mock_detector
        
        frames_file = self.temp_dir / "frames.json"
        frames_file.write_text('{"channel_0": {"0": {"note": 60}}}')
        
        args = Namespace(input=str(frames_file), output="patterns.json")
        
        with patch('main.EnhancedTempoMap'):
            with pytest.raises(Exception, match="Detector error"):
                run_detect_patterns(args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
