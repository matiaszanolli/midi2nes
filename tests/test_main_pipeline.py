"""Tests for main.py run_full_pipeline and compile_rom functions.

These tests focus on the uncovered lines in main.py, particularly:
- run_full_pipeline() (lines 291-459) - the default MIDI-to-ROM conversion
- compile_rom() error paths (lines 187-281)
- Edge cases and error handling
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from argparse import Namespace
import sys

sys.path.append(str(Path(__file__).parent.parent))

from main import run_full_pipeline, compile_rom, main


class TestCompileRomErrorPaths:
    """Test error paths in compile_rom function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_dir = self.temp_dir / "project"
        self.project_dir.mkdir()
        self.rom_output = self.temp_dir / "output.nes"

        # Create required project files for validation
        (self.project_dir / "main.asm").write_text("; main.asm stub")
        (self.project_dir / "music.asm").write_text("; music.asm stub")
        (self.project_dir / "nes.cfg").write_text("; nes.cfg stub")

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_ca65_version_check_fails(self, mock_which, mock_run):
        """Test compile_rom when ca65 version check fails."""
        mock_which.return_value = "/usr/bin/ca65"  # which finds it
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="ca65: error")

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_ld65_version_check_fails(self, mock_which, mock_run):
        """Test compile_rom when ld65 version check fails."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        # First call (ca65) succeeds, second call (ld65) fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="ca65 V2.18", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="ld65: error")
        ]

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_main_asm_compilation_fails(self, mock_which, mock_run):
        """Test compile_rom when main.asm compilation fails."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        # Version checks succeed, main.asm compilation fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="ca65 V2.18", stderr=""),  # ca65 version
            MagicMock(returncode=0, stdout="ld65 V2.18", stderr=""),  # ld65 version
            MagicMock(returncode=1, stdout="", stderr="Error: syntax error")  # main.asm compile
        ]

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_music_asm_compilation_fails(self, mock_which, mock_run):
        """Test compile_rom when music.asm compilation fails."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        # Version checks succeed, main.asm succeeds, music.asm fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="ca65 V2.18", stderr=""),  # ca65 version
            MagicMock(returncode=0, stdout="ld65 V2.18", stderr=""),  # ld65 version
            MagicMock(returncode=0, stdout="", stderr=""),  # main.asm compile
            MagicMock(returncode=1, stdout="", stderr="Error: undefined symbol")  # music.asm compile
        ]

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_linking_fails(self, mock_which, mock_run):
        """Test compile_rom when linking fails."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        # All compiles succeed, linking fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="ca65 V2.18", stderr=""),  # ca65 version
            MagicMock(returncode=0, stdout="ld65 V2.18", stderr=""),  # ld65 version
            MagicMock(returncode=0, stdout="", stderr=""),  # main.asm compile
            MagicMock(returncode=0, stdout="", stderr=""),  # music.asm compile
            MagicMock(returncode=1, stdout="", stderr="Error: unresolved external")  # linking
        ]

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_generated_file_missing(self, mock_which, mock_run):
        """Test compile_rom when generated ROM file doesn't exist."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        # All steps succeed but no ROM file is created
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_generated_file_too_small(self, mock_which, mock_run):
        """Test compile_rom when generated ROM is too small."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        # All steps succeed but ROM is too small
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Create tiny ROM file (smaller than 32KB minimum)
        tiny_rom = self.project_dir / 'game.nes'
        tiny_rom.write_bytes(b'NES\x1a' + b'\x00' * 100)  # Only 104 bytes

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_file_not_found_exception(self, mock_which, mock_run):
        """Test compile_rom when FileNotFoundError is raised."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        mock_run.side_effect = FileNotFoundError("ca65 not found")

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_generic_exception(self, mock_which, mock_run):
        """Test compile_rom when generic exception is raised."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        mock_run.side_effect = Exception("Unexpected error")

        result = compile_rom(self.project_dir, self.rom_output)

        assert result == False


class TestRunFullPipeline:
    """Test run_full_pipeline function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_midi = self.temp_dir / "test.mid"
        self.output_rom = self.temp_dir / "test.nes"

        # Create a minimal test MIDI file
        import mido
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message('note_on', note=60, velocity=64, time=0))
        track.append(mido.Message('note_off', note=60, velocity=0, time=480))
        mid.save(self.test_midi)

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_full_pipeline_missing_input_file(self):
        """Test full pipeline with missing input file."""
        args = Namespace(
            input="nonexistent.mid",
            output=None,
            verbose=False,
            no_patterns=False
        )

        with pytest.raises(SystemExit):
            run_full_pipeline(args)

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_success_with_patterns(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Test successful full pipeline with pattern detection."""
        # Set up mocks
        mock_parse.return_value = {
            "events": {"0": [{"frame": 0, "note": 60}]},
            "metadata": {}
        }
        mock_assign.return_value = {"pulse1": [{"frame": 0, "note": 60}]}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {
            "pulse1": {"0": {"note": 60, "volume": 15}}
        }
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        # compile_rom needs to create the ROM file
        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=False,
            skip_validation=True  # orchestration test - fake ROM, not validating vectors
        )

        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_detector_class:
            mock_detector = Mock()
            mock_detector.detect_patterns.return_value = {
                'patterns': {'p0': [{'frame': 0, 'note': 60}]},
                'references': {'p0': [0]},
                'stats': {'compression_ratio': 2.5}
            }
            mock_detector_class.return_value = mock_detector

            run_full_pipeline(args)

        # Verify all steps were called
        mock_parse.assert_called_once()
        mock_assign.assert_called_once()
        mock_emulator.process_all_tracks.assert_called_once()
        mock_detector.detect_patterns.assert_called_once()
        mock_exporter.export_tables_with_patterns.assert_called_once()
        mock_builder.prepare_project.assert_called_once()
        mock_compile.assert_called_once()

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_no_patterns_flag(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Test full pipeline with --no-patterns flag."""
        mock_parse.return_value = {
            "events": {"0": [{"frame": 0, "note": 60}]},
            "metadata": {}
        }
        mock_assign.return_value = {"pulse1": [{"frame": 0, "note": 60}]}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {
            "pulse1": {"0": {"note": 60, "volume": 15}}
        }
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        # compile_rom needs to create the ROM file
        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=True,  # Skip pattern detection
            skip_validation=True  # orchestration test - fake ROM, not validating vectors
        )

        run_full_pipeline(args)

        # Pattern detector should NOT be used
        # But other steps should still be called
        mock_parse.assert_called_once()
        mock_emulator.process_all_tracks.assert_called_once()
        mock_exporter.export_tables_with_patterns.assert_called_once()

        # Check that empty patterns were passed
        call_args = mock_exporter.export_tables_with_patterns.call_args[0]
        assert call_args[1] == {}  # Empty patterns
        assert call_args[2] == {}  # Empty references

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_large_file_warning(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Test full pipeline with large MIDI file (>10000 events)."""
        # Create large event list
        large_events = [{"frame": i, "note": 60, "volume": 15} for i in range(15000)]

        mock_parse.return_value = {
            "events": {"0": large_events},
            "metadata": {}
        }
        mock_assign.return_value = {"pulse1": large_events}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {
            "pulse1": {str(i): {"note": 60, "volume": 15} for i in range(15000)}
        }
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        # compile_rom needs to create the ROM file
        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=False,
            skip_validation=True  # orchestration test - fake ROM, not validating vectors
        )

        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_detector_class:
            mock_detector = Mock()
            mock_detector.detect_patterns.return_value = {
                'patterns': {},
                'references': {},
                'stats': {'compression_ratio': 1.0}
            }
            mock_detector_class.return_value = mock_detector

            with patch('builtins.print') as mock_print:
                run_full_pipeline(args)

                # Should print large file warning
                print_calls = [str(call[0][0]) for call in mock_print.call_args_list]
                assert any("Large MIDI file" in s for s in print_calls)

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_parallel_detection_fallback(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Test fallback to non-parallel pattern detection."""
        mock_parse.return_value = {
            "events": {"0": [{"frame": i, "note": 60} for i in range(100)]},
            "metadata": {}
        }
        mock_assign.return_value = {"pulse1": [{"frame": i, "note": 60} for i in range(100)]}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {
            "pulse1": {str(i): {"note": 60, "volume": 15} for i in range(100)}
        }
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        # compile_rom needs to create the ROM file
        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=False,
            skip_validation=True  # orchestration test - fake ROM, not validating vectors
        )

        # Make ParallelPatternDetector fail, forcing fallback
        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_parallel:
            mock_parallel.side_effect = Exception("Parallel detection failed")

            with patch('tracker.pattern_detector.EnhancedPatternDetector') as mock_fallback_class:
                mock_fallback = Mock()
                mock_fallback.detect_patterns.return_value = {
                    'patterns': {},
                    'references': {},
                    'stats': {'compression_ratio': 1.0}
                }
                mock_fallback_class.return_value = mock_fallback

                run_full_pipeline(args)

                # Should have fallen back to EnhancedPatternDetector
                mock_fallback_class.assert_called_once()
                mock_fallback.detect_patterns.assert_called_once()

    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_builder_fails(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class
    ):
        """Test full pipeline when project builder fails."""
        mock_parse.return_value = {"events": {}, "metadata": {}}
        mock_assign.return_value = {"pulse1": []}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {}
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = False  # Fails
        mock_builder_class.return_value = mock_builder

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=True
        )

        with pytest.raises(SystemExit):
            run_full_pipeline(args)

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_compile_fails_no_backup(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Test full pipeline when compilation fails and no backup exists."""
        mock_parse.return_value = {"events": {}, "metadata": {}}
        mock_assign.return_value = {"pulse1": []}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {}
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        mock_compile.return_value = False  # Compilation fails

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=True
        )

        with pytest.raises(SystemExit):
            run_full_pipeline(args)

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_compile_fails_with_backup(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Test full pipeline when compilation fails but backup exists."""
        # Create existing ROM file
        self.output_rom.write_bytes(b'NES\x1a' + b'\x00' * 40000)

        mock_parse.return_value = {"events": {}, "metadata": {}}
        mock_assign.return_value = {"pulse1": []}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {}
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        mock_compile.return_value = False  # Compilation fails

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=True
        )

        with pytest.raises(SystemExit):
            run_full_pipeline(args)

        # Backup should have been created and restored
        backup_path = self.output_rom.with_suffix('.nes.backup')
        assert backup_path.exists()

    @patch('main.NESProjectBuilder')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_exception_verbose(self, mock_parse, mock_builder_class):
        """Test full pipeline exception handling with verbose flag."""
        mock_parse.side_effect = Exception("Parse error")

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=True,
            no_patterns=False
        )

        with pytest.raises(SystemExit):
            run_full_pipeline(args)

    @patch('main.NESProjectBuilder')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_exception_non_verbose(self, mock_parse, mock_builder_class):
        """Test full pipeline exception handling without verbose flag."""
        mock_parse.side_effect = Exception("Parse error")

        args = Namespace(
            input=str(self.test_midi),
            output=str(self.output_rom),
            verbose=False,
            no_patterns=False,
            skip_validation=True  # orchestration test - fake ROM, not validating vectors
        )

        with pytest.raises(SystemExit):
            run_full_pipeline(args)

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_run_full_pipeline_default_output_path(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Test full pipeline with default output path (no output specified)."""
        mock_parse.return_value = {"events": {}, "metadata": {}}
        mock_assign.return_value = {"pulse1": []}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {}
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        # compile_rom needs to create the ROM file at the expected path
        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(
            input=str(self.test_midi),
            output=None,  # No output specified
            verbose=False,
            no_patterns=True,
            skip_validation=True  # orchestration test - fake ROM, not validating vectors
        )

        run_full_pipeline(args)

        # Should create output.nes with same name as input
        expected_output = self.test_midi.with_suffix('.nes')
        assert mock_compile.call_args[0][1] == expected_output


class TestMainDefaultBehavior:
    """Test main() function default MIDI-to-ROM behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_midi = self.temp_dir / "test.mid"

        # Create minimal MIDI file
        import mido
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message('note_on', note=60, velocity=64, time=0))
        track.append(mido.Message('note_off', note=60, velocity=0, time=480))
        mid.save(self.test_midi)

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('main.run_full_pipeline')
    def test_main_default_with_midi_file(self, mock_run_pipeline):
        """Test main() with default MIDI-to-ROM conversion."""
        with patch('sys.argv', ['main.py', str(self.test_midi)]):
            main()

            # Should call run_full_pipeline
            mock_run_pipeline.assert_called_once()
            args = mock_run_pipeline.call_args[0][0]
            assert args.input == str(self.test_midi)
            assert args.output is None
            assert args.no_patterns == False

    @patch('main.run_full_pipeline')
    def test_main_default_with_output_specified(self, mock_run_pipeline):
        """Test main() with MIDI input and output specified."""
        with patch('sys.argv', ['main.py', str(self.test_midi), 'output.nes']):
            main()

            mock_run_pipeline.assert_called_once()
            args = mock_run_pipeline.call_args[0][0]
            assert args.input == str(self.test_midi)
            assert args.output == 'output.nes'

    @patch('main.run_full_pipeline')
    def test_main_default_with_no_patterns_flag(self, mock_run_pipeline):
        """Test main() with --no-patterns flag."""
        with patch('sys.argv', ['main.py', '--no-patterns', str(self.test_midi)]):
            main()

            mock_run_pipeline.assert_called_once()
            args = mock_run_pipeline.call_args[0][0]
            assert args.input == str(self.test_midi)
            assert args.no_patterns == True

    @patch('main.run_full_pipeline')
    def test_main_default_with_verbose_flag(self, mock_run_pipeline):
        """Test main() with --verbose flag."""
        with patch('sys.argv', ['main.py', '--verbose', str(self.test_midi)]):
            main()

            mock_run_pipeline.assert_called_once()
            args = mock_run_pipeline.call_args[0][0]
            assert args.input == str(self.test_midi)
            assert args.verbose == True


class TestCC65WrapperProbes:
    """Regression (#14): --version probes use the resolved path and get_version
    guards its subprocess runs."""

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_version_probe_uses_resolved_path(self, mock_which, mock_run):
        from compiler.cc65_wrapper import CC65Wrapper
        mock_which.side_effect = ["/opt/cc65/bin/ca65", "/opt/cc65/bin/ld65"]
        mock_run.return_value = MagicMock(returncode=0, stdout="V2.18", stderr="")

        CC65Wrapper().check_toolchain()

        probed = [c.args[0][0] for c in mock_run.call_args_list]
        assert probed == ["/opt/cc65/bin/ca65", "/opt/cc65/bin/ld65"], \
            "probes must invoke the shutil.which-resolved paths, not bare names"

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_get_version_guards_filenotfound(self, mock_which, mock_run):
        from compiler.cc65_wrapper import CC65Wrapper
        from core.exceptions import ToolchainError
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        # check_toolchain probes pass, then the get_version run vanishes.
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="ca65 V2.18", stderr=""),
            MagicMock(returncode=0, stdout="ld65 V2.18", stderr=""),
            FileNotFoundError(),  # ca65 disappeared before get_version probe
        ]
        with pytest.raises(ToolchainError):
            CC65Wrapper().get_version()


class TestPipelineSafetyGates:
    """Regression tests for the pipeline safety gates (#6, #10, #11)."""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_midi = self.temp_dir / "test.mid"
        self.output_rom = self.temp_dir / "test.nes"
        import mido
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message('note_on', note=60, velocity=64, time=0))
        track.append(mido.Message('note_off', note=60, velocity=0, time=480))
        mid.save(self.test_midi)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- #11: capacity pre-flight ---
    def test_estimate_music_data_size_counts_bytes(self):
        from main import estimate_music_data_size
        asm = self.temp_dir / "m.asm"
        asm.write_text(".byte 1, 2, 3   ; comment\n.word 1, 2\n.res 99\n")
        # 3 bytes + 2 words*2 = 7; .res is RAM, ignored.
        assert estimate_music_data_size(str(asm)) == 7

    def test_estimate_missing_file_is_zero(self):
        from main import estimate_music_data_size
        assert estimate_music_data_size(str(self.temp_dir / "nope.asm")) == 0

    def test_check_mapper_capacity_raises_on_overflow(self):
        from main import check_mapper_capacity

        class TinyMapper:
            name = "Tiny"
            def can_fit_data(self, n): return n <= 4
            def get_data_capacity(self): return 4

        asm = self.temp_dir / "big.asm"
        asm.write_text(".byte 1, 2, 3, 4, 5, 6\n")
        with pytest.raises(ValueError) as exc:
            check_mapper_capacity(str(asm), TinyMapper())
        assert "exceeds" in str(exc.value)

    def test_check_mapper_capacity_passes_for_mmc3(self):
        from main import check_mapper_capacity
        from mappers.mmc3 import MMC3Mapper
        asm = self.temp_dir / "small.asm"
        asm.write_text(".byte 1, 2, 3\n")
        # Should not raise (3 bytes << 512KB).
        check_mapper_capacity(str(asm), MMC3Mapper())

    # --- #6: validation gate fails on boot-fatal defects ---
    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_validation_gate_fails_on_bad_vectors(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}, "metadata": {}}
        mock_assign.return_value = {"pulse1": [{"frame": 0, "note": 60}]}
        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {"pulse1": {"0": {"note": 60, "volume": 15}}}
        mock_emulator_class.return_value = mock_emulator
        mock_exporter_class.return_value = Mock()
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        # A GOOD-health ROM that nonetheless has invalid reset vectors must still
        # fail the gate (#6) — the bug was that only "ERROR" blocked.
        bad = Mock()
        bad.overall_health = "GOOD"
        bad.reset_vectors_valid = False
        bad.apu_pattern_count = 5
        bad.issues = ["Invalid reset vectors"]
        mock_diag = Mock()
        mock_diag.diagnose_rom.return_value = bad

        args = Namespace(input=str(self.test_midi), output=str(self.output_rom),
                         verbose=False, no_patterns=True, skip_validation=False)
        with patch('debug.rom_diagnostics.ROMDiagnostics', return_value=mock_diag):
            with pytest.raises(SystemExit) as exc:
                run_full_pipeline(args)
            assert exc.value.code == 1

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_validation_gate_fails_on_no_apu_init(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}, "metadata": {}}
        mock_assign.return_value = {"pulse1": [{"frame": 0, "note": 60}]}
        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {"pulse1": {"0": {"note": 60, "volume": 15}}}
        mock_emulator_class.return_value = mock_emulator
        mock_exporter_class.return_value = Mock()
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        bad = Mock()
        bad.overall_health = "GOOD"
        bad.reset_vectors_valid = True
        bad.apu_pattern_count = 0  # no APU init
        bad.issues = ["No APU initialization"]
        mock_diag = Mock()
        mock_diag.diagnose_rom.return_value = bad

        args = Namespace(input=str(self.test_midi), output=str(self.output_rom),
                         verbose=False, no_patterns=True, skip_validation=False)
        with patch('debug.rom_diagnostics.ROMDiagnostics', return_value=mock_diag):
            with pytest.raises(SystemExit) as exc:
                run_full_pipeline(args)
            assert exc.value.code == 1

    # --- #10: fallback truncation surfaces a prominent warning ---
    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_fallback_truncation_warns_incomplete(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        many = {str(i): {"note": 60, "volume": 15} for i in range(3000)}
        mock_parse.return_value = {"events": {"0": [{"frame": i, "note": 60} for i in range(3000)]}, "metadata": {}}
        mock_assign.return_value = {"pulse1": [{"frame": i, "note": 60} for i in range(3000)]}
        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {"pulse1": many}
        mock_emulator_class.return_value = mock_emulator
        mock_exporter_class.return_value = Mock()
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        def create_rom(project_path, rom_path):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(input=str(self.test_midi), output=str(self.output_rom),
                         verbose=False, no_patterns=False, skip_validation=True)

        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_parallel:
            mock_parallel.side_effect = Exception("forced fallback")
            with patch('tracker.pattern_detector.EnhancedPatternDetector') as mock_fb:
                fb = Mock()
                fb.detect_patterns.return_value = {'patterns': {}, 'references': {}, 'stats': {'compression_ratio': 1.0}}
                mock_fb.return_value = fb
                with patch('builtins.print') as mock_print:
                    run_full_pipeline(args)
                    out = " ".join(str(c[0][0]) for c in mock_print.call_args_list if c[0])
                    # 3000 events sampled to 2000 in the fallback -> incomplete warning + banner.
                    assert "INCOMPLETE" in out
                    assert "WARNING" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
