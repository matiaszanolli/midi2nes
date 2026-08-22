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

from main import run_full_pipeline, compile_rom, main, DpcmPackResult


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
    def test_compile_rom_truncated_mmc3_image_rejected_with_mapper(self, mock_which, mock_run):
        """Regression (#28/M-8): a flat 32768-byte floor silently passes a
        truncated MMC3 image (declared 512KB PRG) as long as it clears the
        floor. Passing the mapper must reject anything short of the exact
        declared size."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Well above the old flat floor, but far short of MMC3's 512KB + 16.
        truncated_rom = self.project_dir / 'game.nes'
        truncated_rom.write_bytes(b'NES\x1a' + b'\x00' * 65536)

        from mappers.mmc3 import MMC3Mapper
        result = compile_rom(self.project_dir, self.rom_output, mapper=MMC3Mapper())

        assert result == False

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_exact_mmc3_size_accepted_with_mapper(self, mock_which, mock_run):
        """The exact declared MMC3 PRG size (+ 16-byte header) must still pass."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from mappers.mmc3 import MMC3Mapper
        mapper = MMC3Mapper()
        exact_rom = self.project_dir / 'game.nes'
        exact_rom.write_bytes(b'\x00' * (mapper.prg_rom_size + 16))

        result = compile_rom(self.project_dir, self.rom_output, mapper=mapper)

        assert result == True

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_runs_mapper_post_process_commands(
            self, mock_which, mock_run):
        """Regression (#214/MAP-3): ROMCompiler.compile() previously never
        called mapper.generate_post_process_commands() at all -- build.sh
        (via BaseMapper.generate_build_script) runs a mapper's post-link
        fixup but this compiler path silently skipped it. Must now run the
        returned shell snippet from the project directory.

        Note: compiler/compiler.py and compiler/cc65_wrapper.py both do
        `import subprocess`, the same real module -- patching that attribute
        via two different dotted paths would collide (only the last-entered
        patch stays live), so this mocks subprocess.run ONCE and tells the
        cc65 assemble/link calls (argv list) apart from the post-process
        call (a shell string) by argument shape."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        mock_run.side_effect = lambda cmd, **kwargs: MagicMock(returncode=0, stdout="", stderr="")

        from mappers.mmc3 import MMC3Mapper

        class _MapperWithPostProcess(MMC3Mapper):
            def generate_post_process_commands(self, is_windows=False):
                return "echo fixup\n"

        mapper = _MapperWithPostProcess()
        exact_rom = self.project_dir / 'game.nes'
        exact_rom.write_bytes(b'\x00' * (mapper.prg_rom_size + 16))

        result = compile_rom(self.project_dir, self.rom_output, mapper=mapper)

        assert result == True
        shell_calls = [c for c in mock_run.call_args_list if isinstance(c.args[0], str)]
        assert len(shell_calls) == 1
        assert shell_calls[0].args[0] == "echo fixup\n"
        assert shell_calls[0].kwargs['shell'] is True
        assert shell_calls[0].kwargs['cwd'] == self.project_dir

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_skips_post_process_when_mapper_has_none(
            self, mock_which, mock_run):
        """A mapper whose generate_post_process_commands() returns "" (every
        mapper today, since #213 removed MMC1's broken fixup) must not spawn
        a post-process subprocess at all."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from mappers.mmc3 import MMC3Mapper
        mapper = MMC3Mapper()
        exact_rom = self.project_dir / 'game.nes'
        exact_rom.write_bytes(b'\x00' * (mapper.prg_rom_size + 16))

        result = compile_rom(self.project_dir, self.rom_output, mapper=mapper)

        assert result == True
        shell_calls = [c for c in mock_run.call_args_list if isinstance(c.args[0], str)]
        assert len(shell_calls) == 0

    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_post_process_failure_surfaces_stderr(
            self, mock_which, mock_run, capsys):
        """A failing post-process command must fail the whole compile with a
        nonzero-equivalent (result False) and surface its stderr, matching
        the CC65 assemble/link error-surfacing contract."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]

        def run_side_effect(cmd, **kwargs):
            if isinstance(cmd, str):
                return MagicMock(returncode=1, stdout="", stderr="fixup exploded")
            return MagicMock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = run_side_effect

        from mappers.mmc3 import MMC3Mapper

        class _MapperWithPostProcess(MMC3Mapper):
            def generate_post_process_commands(self, is_windows=False):
                return "false\n"

        mapper = _MapperWithPostProcess()
        exact_rom = self.project_dir / 'game.nes'
        exact_rom.write_bytes(b'\x00' * (mapper.prg_rom_size + 16))

        result = compile_rom(self.project_dir, self.rom_output, mapper=mapper)

        assert result == False
        out = capsys.readouterr().out
        assert "fixup exploded" in out

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

    @patch('compiler.compiler.traceback.print_exc')
    @patch('compiler.cc65_wrapper.subprocess.run')
    @patch('compiler.cc65_wrapper.shutil.which')
    def test_compile_rom_generic_exception_prints_traceback_when_verbose(
            self, mock_which, mock_run, mock_print_exc):
        """Regression (#32/M-9): the catch-all except in compile_rom used to
        print only the exception message with no way to see where an
        unexpected failure actually originated. Under verbose=True it must
        also print the traceback; under verbose=False (the default,
        exercised by test_compile_rom_generic_exception above) it must not."""
        mock_which.side_effect = ["/usr/bin/ca65", "/usr/bin/ld65"]
        mock_run.side_effect = Exception("Unexpected error")

        result = compile_rom(self.project_dir, self.rom_output, verbose=True)

        assert result == False
        mock_print_exc.assert_called_once()


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
        def create_rom(project_path, rom_path, **kwargs):
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
                'stats': {'compression_ratio': 2.5, 'total_events': 10, 'coverage_ratio': 60.0}
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
    def test_run_full_pipeline_calls_shared_dpcm_pack_helper(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Regression (#380/TD-28): run_full_pipeline must route DPCM
        packing through the shared pack_dpcm_into_asm helper (not a
        re-inlined copy) so a fix to the packing logic can't silently
        miss this path -- the SIBLING half of the same check on run_export."""
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}, "metadata": {}}
        mock_assign.return_value = {"pulse1": [{"frame": 0, "note": 60}]}
        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {"pulse1": {"0": {"note": 60, "volume": 15}}}
        mock_emulator_class.return_value = mock_emulator
        mock_exporter_class.return_value = Mock()
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        def create_rom(project_path, rom_path, **kwargs):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(
            input=str(self.test_midi), output=str(self.output_rom),
            verbose=False, no_patterns=True, skip_validation=True
        )

        from main import DpcmPackResult
        with patch('main.pack_dpcm_into_asm') as mock_pack:
            mock_pack.return_value = DpcmPackResult(index_found=False)
            run_full_pipeline(args)
            mock_pack.assert_called_once()
            assert mock_pack.call_args.kwargs.get('verbose') == args.verbose

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
        def create_rom(project_path, rom_path, **kwargs):
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
        """Test full pipeline with large MIDI file (exceeds the advisory
        large-file threshold, which defaults to MAX_PATTERN_EVENTS=15000 per
        #334/PERF-14 -- use a count comfortably past that, not equal to it)."""
        # Create large event list
        large_events = [{"frame": i, "note": 60, "volume": 15} for i in range(20000)]

        mock_parse.return_value = {
            "events": {"0": large_events},
            "metadata": {}
        }
        mock_assign.return_value = {"pulse1": large_events}

        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {
            "pulse1": {str(i): {"note": 60, "volume": 15} for i in range(20000)}
        }
        mock_emulator_class.return_value = mock_emulator

        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        # compile_rom needs to create the ROM file
        def create_rom(project_path, rom_path, **kwargs):
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
                'stats': {'compression_ratio': 1.0, 'total_events': 0, 'coverage_ratio': 0}
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
        def create_rom(project_path, rom_path, **kwargs):
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
                    'stats': {'compression_ratio': 1.0, 'total_events': 0, 'coverage_ratio': 0}
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
        def create_rom(project_path, rom_path, **kwargs):
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


class TestRunFullPipelineMemoryOverhead:
    """Regression (#371/PERF-A-01): run_full_pipeline used to hold three
    successive full copies of the same musical data simultaneously (parsed
    midi_data, mapped, and frames) with no stage releasing its input once
    its successor was built -- the frames stage's peak held both its input
    and output at once. Each stage's input dict must now be `del`d right
    after its successor is built, in both the legacy and --arranger
    branches."""

    def test_legacy_branch_dels_midi_data_and_mapped(self):
        import inspect
        import main
        src = inspect.getsource(main.run_full_pipeline)
        # Isolate the legacy (non-arranger) branch's source between the two
        # step markers so this doesn't false-positive on the arranger
        # branch's own `del midi_data`. Steps 4-8 were extracted into stage
        # helpers (#406/TD-11-FOLLOWUP); steps 1-3 deliberately stay inline
        # in run_full_pipeline itself (see that extraction's own comment) so
        # this del-ordering contract keeps being checked against the actual
        # code that implements it.
        legacy_start = src.index('# Step 2: Map tracks to NES channels')
        legacy_end = src.index('# Steps 4-8 are extracted into stage helpers')
        legacy_branch = src[legacy_start:legacy_end]

        assign_idx = legacy_branch.index('assign_tracks_to_nes_channels(')
        del_midi_idx = legacy_branch.index('del midi_data')
        process_idx = legacy_branch.index('process_all_tracks(')
        del_mapped_idx = legacy_branch.index('del mapped')

        assert assign_idx < del_midi_idx < process_idx < del_mapped_idx, (
            "expected: assign mapped -> del midi_data -> build frames -> del mapped"
        )

    def test_arranger_branch_dels_midi_data(self):
        import inspect
        import main
        src = inspect.getsource(main.run_full_pipeline)
        arranger_start = src.index('if use_arranger:')
        arranger_end = src.index('else:', arranger_start)
        arranger_branch = src[arranger_start:arranger_end]

        arrange_idx = arranger_branch.index('arrange_for_nes(')
        del_idx = arranger_branch.index('del midi_data')
        assert arrange_idx < del_idx, "expected: build frames -> del midi_data"


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
            def validate_segment_sizes(self, segment_sizes):
                total = sum(segment_sizes.values())
                if total > self.get_data_capacity():
                    return [f"music data ({total} bytes) exceeds {self.name} "
                            f"capacity ({self.get_data_capacity()} bytes)"]
                return []

        asm = self.temp_dir / "big.asm"
        asm.write_text(".byte 1, 2, 3, 4, 5, 6\n")
        with pytest.raises(ValueError) as exc:
            check_mapper_capacity(str(asm), TinyMapper())
        assert "exceeds" in str(exc.value)

    def test_check_mapper_capacity_error_is_also_a_midi2neserror(self):
        """Regression (#457/SAFE-2026-08-21-3, PIPE-2026-08-21-8): this
        expected, actionable failure must be catchable through
        `except MIDI2NESError` (run_full_pipeline's "expected failure"
        clause), not just `except ValueError` -- MapperError is now both."""
        from main import check_mapper_capacity
        from core.exceptions import MIDI2NESError, MapperError

        class TinyMapper:
            name = "Tiny"
            def can_fit_data(self, n): return n <= 4
            def get_data_capacity(self): return 4
            def validate_segment_sizes(self, segment_sizes):
                return ["music data exceeds Tiny capacity"]

        asm = self.temp_dir / "big2.asm"
        asm.write_text(".byte 1, 2, 3, 4, 5, 6\n")
        with pytest.raises(MIDI2NESError):
            check_mapper_capacity(str(asm), TinyMapper())
        with pytest.raises(MapperError):
            check_mapper_capacity(str(asm), TinyMapper())

    def test_check_mapper_capacity_passes_for_mmc3(self):
        from main import check_mapper_capacity
        from mappers.mmc3 import MMC3Mapper
        asm = self.temp_dir / "small.asm"
        asm.write_text(".byte 1, 2, 3\n")
        # Should not raise (3 bytes << 512KB).
        check_mapper_capacity(str(asm), MMC3Mapper())

    def test_capacity_gate_rejects_oversized_direct_export(self):
        """#126: direct-export tables land in the 8 KB PRG_FIX bank, not the full
        510 KB PRG. A multi-KB RODATA must fail the pre-flight (naming PRG_FIX)
        instead of being waved through to a raw ld65 region overflow."""
        from main import check_mapper_capacity
        from mappers.mmc3 import MMC3Mapper
        asm = self.temp_dir / "big_direct.asm"
        row = "    .byte " + ", ".join(["$00"] * 64) + "\n"
        asm.write_text('.segment "RODATA"\n' + row * 200)  # ~12.8 KB of RODATA
        with pytest.raises(ValueError) as exc:
            check_mapper_capacity(str(asm), MMC3Mapper())
        assert "PRG_FIX" in str(exc.value)

    def test_capacity_gate_rejects_bank_overflow(self):
        """#127: a BANK_60 segment has no MEMORY region in the MMC3 cfg (only
        BANK_00..59). The gate must reject it pre-link with a bank-budget message."""
        from main import check_mapper_capacity
        from mappers.mmc3 import MMC3Mapper
        asm = self.temp_dir / "overbank.asm"
        asm.write_text('.segment "BANK_60"\n    .byte $01, $02\n')
        with pytest.raises(ValueError) as exc:
            check_mapper_capacity(str(asm), MMC3Mapper())
        assert "bank 60" in str(exc.value)

    def test_estimate_segment_sizes_buckets_and_honors_bounded_incbin(self):
        """estimate_segment_sizes keys bytes by .segment and counts a bounded
        `.incbin "f", 0, N` as N (the truncated DPCM length, #68), not the file."""
        from main import estimate_segment_sizes
        asm = self.temp_dir / "seg.asm"
        asm.write_text(
            '.segment "RODATA"\n    .byte 1, 2, 3\n'
            '.segment "BANK_00"\n    .word 1, 2\n'        # 2 words = 4 bytes
            '    .incbin "anything.dmc", 0, 4081\n'        # bounded -> 4081, file need not exist
        )
        sizes = estimate_segment_sizes(str(asm))
        assert sizes["RODATA"] == 3
        assert sizes["BANK_00"] == 4 + 4081

    def test_estimate_segment_sizes_counts_string_literal_length(self):
        """Regression (#390/MAP-2026-08-05-3): a quoted `.byte "string"` token
        must count its real character length, not "1 token = 1 byte" like a
        numeric literal -- the old naive comma-split undercounted every
        string line (e.g. the iNES header's `.byte "NES", $1A"` was counted
        as 2 bytes instead of the real 4)."""
        from main import estimate_segment_sizes
        asm = self.temp_dir / "strings.asm"
        asm.write_text(
            '.segment "HEADER"\n'
            '    .byte "NES", $1A\n'          # "NES" (3) + $1A (1) = 4
            '.segment "RODATA"\n'
            '    .byte "MIDI2NES DEBUG v1.0", $00\n'  # 19-char string + $00 = 20
        )
        sizes = estimate_segment_sizes(str(asm))
        assert sizes["HEADER"] == 4
        assert sizes["RODATA"] == 20

    def test_estimate_segment_sizes_ignores_comma_inside_string(self):
        """A comma inside a quoted string literal is not a token separator
        (#390/MAP-2026-08-05-3) -- the naive split would previously treat
        `.byte "some, string", $00` as 3 tokens (overcounting) instead of the
        real 13 bytes (12-char string + 1 terminator byte)."""
        from main import estimate_segment_sizes
        asm = self.temp_dir / "embedded_comma.asm"
        asm.write_text('.segment "RODATA"\n    .byte "some, string", $00\n')
        sizes = estimate_segment_sizes(str(asm))
        assert sizes["RODATA"] == 13

    def test_estimate_segment_sizes_accounts_for_align_padding(self):
        """Regression (#301/MAP-2026-07-06-2): `.align N` must round the
        running per-segment offset up to the next multiple of N, matching
        ld65, instead of being silently ignored. `DpcmPacker` emits
        `.align 64` before every packed sample -- an unaligned two-sample
        segment previously undercounted the real ROM footprint by the
        padding gap."""
        from main import estimate_segment_sizes
        asm = self.temp_dir / "aligned.asm"
        asm.write_text(
            '.segment "DPCM_00"\n'
            '    .align 64\n'
            '    dpcm_sample_0:\n'
            '    .incbin "s0.dmc", 0, 10\n'   # offset 0 -> 10 (no padding needed)
            '    .align 64\n'                  # 10 -> pad up to 64
            '    dpcm_sample_1:\n'
            '    .incbin "s1.dmc", 0, 20\n'   # 64 -> 84
        )
        sizes = estimate_segment_sizes(str(asm))
        assert sizes["DPCM_00"] == 84  # not 10 + 20 = 30 (the pre-fix undercount)

    def test_estimate_segment_sizes_matches_dpcm_packer_real_layout(self):
        """The pre-flight estimate for a bank of packed DPCM samples must
        match the real, tightly-packed layout `DpcmPacker.generate_assembly`
        emits (#301): `.align 64` before each sample pads the running offset
        up to the next boundary, then the raw sample bytes follow with no
        further padding -- this is strictly tighter than (<=) the sum of each
        sample's independently-rounded `aligned_size`, which is only a
        conservative bin-fit budget `_pack_samples` uses to choose which bank
        a sample goes in, not the final byte count."""
        from main import estimate_segment_sizes

        sample_sizes = [10, 20, 4081]  # arbitrary, unaligned raw sizes

        # Simulate the same running-offset layout generate_assembly produces:
        # align-before-each, no post-padding.
        offset = 0
        for size in sample_sizes:
            offset = -(-offset // 64) * 64  # round up to next 64-byte boundary
            offset += size
        expected_total = offset

        asm_lines = ['.segment "DPCM_00"']
        for i, size in enumerate(sample_sizes):
            asm_lines.append('    .align 64')
            asm_lines.append(f'    dpcm_sample_{i}:')
            asm_lines.append(f'    .incbin "s{i}.dmc", 0, {size}')
        asm = self.temp_dir / "packed.asm"
        asm.write_text('\n'.join(asm_lines) + '\n')

        sizes = estimate_segment_sizes(str(asm))
        assert sizes["DPCM_00"] == expected_total
        # And that real layout is never larger than the packer's conservative
        # per-sample bin-fit budget, confirming #301's "packer-guarded" claim:
        # aligned_size-sum <= BANK_SIZE always implies real bytes <= BANK_SIZE.
        conservative_budget = sum(-(-s // 64) * 64 for s in sample_sizes)
        assert expected_total <= conservative_budget

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

        def create_rom(project_path, rom_path, **kwargs):
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

        def create_rom(project_path, rom_path, **kwargs):
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

    # --- #178/PL-05: a validation-failed ROM must never be left at the output path ---
    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_validation_gate_failure_removes_bad_rom_on_first_build(
        self, mock_parse, mock_assign, mock_emulator_class,
        mock_exporter_class, mock_builder_class, mock_compile
    ):
        """Regression (#178/PL-05): previously the finally-restore was a no-op
        when no backup existed (first-time build), leaving the freshly written
        unbootable ROM sitting at the output path despite the nonzero exit."""
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}, "metadata": {}}
        mock_assign.return_value = {"pulse1": [{"frame": 0, "note": 60}]}
        mock_emulator = Mock()
        mock_emulator.process_all_tracks.return_value = {"pulse1": {"0": {"note": 60, "volume": 15}}}
        mock_emulator_class.return_value = mock_emulator
        mock_exporter_class.return_value = Mock()
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        def create_rom(project_path, rom_path, **kwargs):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        assert not self.output_rom.exists()

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

        assert not self.output_rom.exists(), "unbootable ROM must not be left at the output path"
        assert Path(str(self.output_rom) + '.failed').exists()

    # --- #176/PL-03: fallback truncation surfaces an accurate, non-scary note ---
    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_fallback_truncation_warns_but_rom_is_not_incomplete(
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

        def create_rom(project_path, rom_path, **kwargs):
            rom_path.write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(input=str(self.test_midi), output=str(self.output_rom),
                         verbose=False, no_patterns=False, skip_validation=True)

        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_parallel:
            mock_parallel.side_effect = Exception("forced fallback")
            with patch('tracker.pattern_detector.EnhancedPatternDetector') as mock_fb:
                fb = Mock()
                fb.detect_patterns.return_value = {'patterns': {}, 'references': {}, 'stats': {'compression_ratio': 1.0, 'total_events': 0, 'coverage_ratio': 0}}
                mock_fb.return_value = fb
                with patch('builtins.print') as mock_print:
                    run_full_pipeline(args)
                    out = " ".join(str(c[0][0]) for c in mock_print.call_args_list if c[0])
                    # 3000 events sampled to 2000 in the fallback -> a note that
                    # compression stats are approximate, NOT a false claim that
                    # the ROM itself is incomplete (#176/PL-03) or advice to use
                    # --no-patterns (which would make the ROM bigger for no gain).
                    assert "approximate" in out
                    assert "unaffected" in out
                    assert "INCOMPLETE" not in out
                    assert "--no-patterns" not in out


class TestPreparePath(object):
    """Regression tests for run_prepare error handling and the compile
    subcommand (#15)."""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('main.NESProjectBuilder')
    def test_run_prepare_exits_on_falsy_return(self, mock_builder_class):
        from main import run_prepare
        asm = self.temp_dir / "music.asm"
        asm.write_text(".byte 1, 2, 3\n")
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = False
        mock_builder_class.return_value = mock_builder
        args = Namespace(input=str(asm), output=str(self.temp_dir / "proj"))
        with pytest.raises(SystemExit) as exc:
            run_prepare(args)
        assert exc.value.code == 1

    @patch('main.NESProjectBuilder')
    def test_run_prepare_exits_on_exception(self, mock_builder_class):
        from main import run_prepare
        asm = self.temp_dir / "music.asm"
        asm.write_text(".byte 1, 2, 3\n")
        mock_builder = Mock()
        mock_builder.prepare_project.side_effect = PermissionError("denied")
        mock_builder_class.return_value = mock_builder
        args = Namespace(input=str(asm), output=str(self.temp_dir / "proj"))
        with pytest.raises(SystemExit) as exc:
            run_prepare(args)
        assert exc.value.code == 1

    def test_run_compile_missing_project_exits(self):
        from main import run_compile
        args = Namespace(input=str(self.temp_dir / "nope"),
                         output=str(self.temp_dir / "out.nes"))
        with pytest.raises(SystemExit) as exc:
            run_compile(args)
        assert exc.value.code == 1

    @patch('main.compile_rom')
    def test_run_compile_validates_and_fails_on_bad_vectors(self, mock_compile):
        from main import run_compile
        proj = self.temp_dir / "proj"
        proj.mkdir()
        out = self.temp_dir / "out.nes"

        def create_rom(p, r, **kwargs):
            Path(r).write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        bad = Mock()
        bad.reset_vectors_valid = False
        bad.apu_pattern_count = 5
        bad.overall_health = "GOOD"
        bad.issues = []
        mock_diag = Mock()
        mock_diag.diagnose_rom.return_value = bad

        args = Namespace(input=str(proj), output=str(out), skip_validation=False, verbose=False)
        with patch('debug.rom_diagnostics.ROMDiagnostics', return_value=mock_diag):
            with pytest.raises(SystemExit) as exc:
                run_compile(args)
            assert exc.value.code == 1

    @patch('main.compile_rom')
    def test_run_compile_validation_failure_removes_bad_rom_first_build(self, mock_compile):
        """Regression (#178/PL-05): a first-time build (no pre-existing output
        ROM) that fails validation must not leave the unbootable ROM at the
        output path -- it gets moved aside to <name>.nes.failed instead."""
        from main import run_compile
        proj = self.temp_dir / "proj"
        proj.mkdir()
        out = self.temp_dir / "out.nes"
        assert not out.exists()

        def create_rom(p, r, **kwargs):
            Path(r).write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        bad = Mock()
        bad.reset_vectors_valid = False
        bad.apu_pattern_count = 5
        bad.overall_health = "GOOD"
        bad.issues = []
        mock_diag = Mock()
        mock_diag.diagnose_rom.return_value = bad

        args = Namespace(input=str(proj), output=str(out), skip_validation=False, verbose=False)
        with patch('debug.rom_diagnostics.ROMDiagnostics', return_value=mock_diag):
            with pytest.raises(SystemExit) as exc:
                run_compile(args)
            assert exc.value.code == 1

        assert not out.exists(), "unbootable ROM must not be left at the output path"
        assert Path(str(out) + '.failed').exists()

    @patch('main.compile_rom')
    def test_run_compile_validation_failure_restores_pre_existing_rom(self, mock_compile):
        """Regression (#178/PL-05): run_compile previously had no backup
        contract at all -- a validation failure overwrote a pre-existing good
        ROM with no way back. It must now back up first and restore on failure,
        matching the default pipeline path's contract."""
        from main import run_compile
        proj = self.temp_dir / "proj"
        proj.mkdir()
        out = self.temp_dir / "out.nes"
        original_bytes = b'GOODROM' + b'\x00' * 100
        out.write_bytes(original_bytes)

        def create_rom(p, r, **kwargs):
            Path(r).write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        bad = Mock()
        bad.reset_vectors_valid = False
        bad.apu_pattern_count = 5
        bad.overall_health = "GOOD"
        bad.issues = []
        mock_diag = Mock()
        mock_diag.diagnose_rom.return_value = bad

        args = Namespace(input=str(proj), output=str(out), skip_validation=False, verbose=False)
        with patch('debug.rom_diagnostics.ROMDiagnostics', return_value=mock_diag):
            with pytest.raises(SystemExit) as exc:
                run_compile(args)
            assert exc.value.code == 1

        assert out.read_bytes() == original_bytes, "pre-existing good ROM must be restored"
        assert not Path(str(out) + '.failed').exists()

    @patch('main.compile_rom')
    def test_run_compile_skip_validation_succeeds(self, mock_compile):
        from main import run_compile
        proj = self.temp_dir / "proj"
        proj.mkdir()
        out = self.temp_dir / "out.nes"

        def create_rom(p, r, **kwargs):
            Path(r).write_bytes(b'NES\x1a' + b'\x00' * 131000)
            return True
        mock_compile.side_effect = create_rom

        args = Namespace(input=str(proj), output=str(out), skip_validation=True, verbose=False)
        run_compile(args)  # should not raise
        assert out.exists()

    @patch('main.compile_rom')
    def test_run_compile_recovers_prepare_auto_mapper_from_nes_cfg(self, mock_compile):
        """Regression (#269/PL-08): a project prepared with --mapper auto has
        no matching --mapper choice for `compile` (only nrom/mmc1/mmc3, no
        'auto'). `_prepared_mapper_name_from_cfg` already recovers the mapper
        `prepare` actually resolved from the nes.cfg marker it stamps, so
        `compile` must use THAT mapper even when the user passes (or
        defaults to) an unrelated --mapper value -- pinning the parity the
        #297 cfg-recovery fix already provides at the code level."""
        from main import run_compile, NES_CFG_MAPPER_MARKER
        from mappers.nrom import NROMMapper

        proj = self.temp_dir / "proj"
        proj.mkdir()
        # Mirror what `prepare --mapper auto` stamps for a small song that
        # auto-selects NROM: a marker line at the top of nes.cfg.
        (proj / "nes.cfg").write_text(f"{NES_CFG_MAPPER_MARKER}nrom\n# rest of cfg\n")
        (proj / "music.asm").write_text(".byte 1, 2, 3\n")
        out = self.temp_dir / "out.nes"

        def create_rom(p, r, **kwargs):
            Path(r).write_bytes(b'NES\x1a' + b'\x00' * 32768)
            return True
        mock_compile.side_effect = create_rom

        # args.mapper defaults to 'mmc3' -- the CLI's own default -- and is
        # NOT nrom, proving the nes.cfg marker wins over it.
        args = Namespace(input=str(proj), output=str(out), skip_validation=True,
                          verbose=False, mapper='mmc3')
        run_compile(args)

        used_mapper = mock_compile.call_args.kwargs['mapper']
        assert isinstance(used_mapper, NROMMapper), (
            "compile must build with the mapper prepare(auto) actually chose "
            "(nrom, recovered from nes.cfg), not the --mapper default (mmc3)"
        )

    def test_validate_rom_passes_for_bootable(self):
        from main import validate_rom
        good = Mock()
        good.reset_vectors_valid = True
        good.apu_pattern_count = 22
        good.overall_health = "GOOD"
        good.assembly_code_score = 180
        mock_diag = Mock()
        mock_diag.diagnose_rom.return_value = good
        with patch('debug.rom_diagnostics.ROMDiagnostics', return_value=mock_diag):
            assert validate_rom(self.temp_dir / "x.nes") is True

    def test_validate_rom_fails_closed_when_diagnostics_engine_breaks(self):
        """Regression (#177/PL-04): a broken diagnostics engine (import error,
        internal bug) must fail validation, not silently pass the ROM -- the
        caller only reaches validate_rom when the user did NOT ask to skip
        validation, so accepting on a broken engine defeats the boot-fatal gate."""
        from main import validate_rom
        with patch('debug.rom_diagnostics.ROMDiagnostics', side_effect=ImportError("boom")):
            assert validate_rom(self.temp_dir / "x.nes") is False

    def test_validate_rom_prints_engine_failure_without_verbose(self, capsys):
        """Regression (#177/PL-04): the "ROM NOT validated" warning must print
        unconditionally -- previously it was gated behind --verbose, so a
        default (non-verbose) run gave zero indication validation was skipped."""
        from main import validate_rom
        with patch('debug.rom_diagnostics.ROMDiagnostics', side_effect=RuntimeError("boom")):
            validate_rom(self.temp_dir / "x.nes")
        out = capsys.readouterr().out
        assert "ROM NOT validated" in out
        assert "boom" in out

    def test_compile_subcommand_is_registered(self):
        from main import main as main_entry
        # `compile` with a missing project dir should exit 1 (recognized command).
        with patch('sys.argv', ['main.py', 'compile', str(self.temp_dir / 'nope'), 'o.nes']):
            with pytest.raises(SystemExit) as exc:
                main_entry()
            assert exc.value.code == 1


class TestDetectPatternsOrDirectExport:
    """Coverage for the #406/TD-11-FOLLOWUP extraction of run_full_pipeline's
    Step 4 into its own testable function."""

    def test_direct_export_returns_matching_schema_stub(self):
        from main import detect_patterns_or_direct_export
        # Real per-channel shape ({frame_num: {...}}, as process_all_tracks
        # produces) -- the stub now goes through the shared frames_to_events
        # extractor (#435/PAT-2026-08-21-1), which requires real channel
        # dicts rather than the bare length-count placeholders this fixture
        # used to hold.
        frames = {
            "pulse1": {"0": {"note": 60, "volume": 100}, "4": {"note": 62, "volume": 90}, "8": {"note": 64, "volume": 80}},
            "triangle": {"0": {"note": 40, "volume": 100}, "4": {"note": 42, "volume": 90}},
        }
        args = Namespace(verbose=False, config=None)

        result, loss_warning, lossy_note = detect_patterns_or_direct_export(
            frames, use_patterns=False, args=args)

        # Same schema every real detector emits (#104), zero compression
        # and zero coverage since direct export applies none (#17, #169).
        assert result['patterns'] == {}
        assert result['references'] == {}
        assert result['variations'] == {}
        assert result['stats']['original_size'] == 5
        assert result['stats']['compression_ratio'] == 0
        assert result['stats']['coverage_ratio'] == 0
        assert loss_warning is None
        assert lossy_note == ""

    @patch('main.get_pattern_detection_caps')
    def test_patterns_path_returns_detector_result(self, mock_caps):
        from main import detect_patterns_or_direct_export
        mock_caps.return_value = (1000, 15000, 15000)
        frames = {"pulse1": {"0": {"note": 60, "volume": 100}}}
        args = Namespace(verbose=False, config=None)

        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_cls:
            mock_detector = Mock()
            mock_detector.was_sampled = False
            mock_detector.detect_patterns.return_value = {
                'patterns': {'p0': []}, 'references': {},
                'stats': {'compression_ratio': 3.0, 'total_events': 5, 'coverage_ratio': 80.0},
            }
            mock_cls.return_value = mock_detector

            result, loss_warning, lossy_note = detect_patterns_or_direct_export(
                frames, use_patterns=True, args=args)

        assert result['patterns'] == {'p0': []}
        assert loss_warning is None
        assert lossy_note == ""

    @patch('main.get_pattern_detection_caps')
    def test_fallback_path_sets_lossy_note_when_sampled(self, mock_caps):
        from main import detect_patterns_or_direct_export
        mock_caps.return_value = (1000, 15000, 15000)
        frames = {"pulse1": {"0": {"note": 60, "volume": 100}}}
        args = Namespace(verbose=False, config=None)

        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_parallel:
            mock_parallel.side_effect = Exception("parallel unavailable")
            with patch('tracker.pattern_detector.EnhancedPatternDetector') as mock_fallback_cls:
                mock_fallback = Mock()
                mock_fallback.was_sampled = True  # collapses coverage_ratio (#312/PAT-11)
                mock_fallback.detect_patterns.return_value = {
                    'patterns': {}, 'references': {},
                    'stats': {'compression_ratio': 0, 'total_events': 1, 'coverage_ratio': 10.0},
                }
                mock_fallback_cls.return_value = mock_fallback

                result, loss_warning, lossy_note = detect_patterns_or_direct_export(
                    frames, use_patterns=True, args=args)

        assert "lossy" in lossy_note

    @patch('main.get_pattern_detection_caps')
    def test_fallback_path_sets_lossy_note_when_only_externally_sampled(self, mock_caps):
        """Regression (#378/PIPE-2026-07-19-2): the fallback branch pre-samples
        events down to max_events (main.py) *before* calling
        detector.detect_patterns, so the detector's own internal re-sample
        (tracker/pattern_detector.py) is a no-op and detector.was_sampled stays
        False even though the events genuinely were sampled. The coverage
        suffix must still key off the fallback's own local was_sampled flag,
        not only detector.was_sampled."""
        from main import detect_patterns_or_direct_export
        mock_caps.return_value = (2, 15000, 15000)  # max_events=2 -> forces external sampling
        frames = {"pulse1": {str(i): {"note": 60, "volume": 100} for i in range(5)}}
        args = Namespace(verbose=False, config=None)

        with patch('tracker.pattern_detector_parallel.ParallelPatternDetector') as mock_parallel:
            mock_parallel.side_effect = Exception("parallel unavailable")
            with patch('tracker.pattern_detector.EnhancedPatternDetector') as mock_fallback_cls:
                mock_fallback = Mock()
                # The detector's own internal sampling is a no-op here (events
                # already at the cap by the time detect_patterns receives them).
                mock_fallback.was_sampled = False
                mock_fallback.detect_patterns.return_value = {
                    'patterns': {}, 'references': {},
                    'stats': {'compression_ratio': 0, 'total_events': 2, 'coverage_ratio': 100.0},
                }
                mock_fallback_cls.return_value = mock_fallback

                result, loss_warning, lossy_note = detect_patterns_or_direct_export(
                    frames, use_patterns=True, args=args)

        assert loss_warning is not None
        assert "lossy" in lossy_note


class TestExportFramesAndResolveMapper:
    """Coverage for the #406/TD-11-FOLLOWUP extraction of run_full_pipeline's
    Steps 5-5.5. Pins the mapper-resolution timing that differs by path
    (#255/MAP-2026-07-05-1): direct-export resolves before exporting,
    patterned/bytecode resolves after, from the written music.asm."""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('main.CA65Exporter')
    def test_patterns_path_resolves_mapper_after_export(self, mock_exporter_cls):
        from main import export_frames_and_resolve_mapper
        mock_exporter = Mock()
        mock_exporter_cls.return_value = mock_exporter
        music_asm = self.temp_dir / "music.asm"
        args = Namespace(verbose=False, mapper=None)
        pattern_result = {'patterns': {}, 'references': {}}
        frames = {"pulse1": []}

        call_order = []
        mock_exporter.export_tables_with_patterns.side_effect = (
            lambda *a, **kw: call_order.append('export'))

        with patch('main.resolve_mapper') as mock_resolve, \
             patch('main.pack_dpcm_into_asm') as mock_pack:
            mock_resolve.side_effect = lambda *a, **kw: (call_order.append('resolve'), Mock(name='mmc3'))[1]
            mock_pack.return_value = DpcmPackResult(index_found=False)

            mapper, pack_result = export_frames_and_resolve_mapper(
                frames, pattern_result, music_asm, use_patterns=True, args=args)

        assert call_order == ['export', 'resolve']
        # Exported with mapper=None -- resolution genuinely happens after,
        # not just called-after with a value already known.
        assert mock_exporter.export_tables_with_patterns.call_args.kwargs['mapper'] is None

    @patch('main.CA65Exporter')
    def test_direct_export_resolves_mapper_before_export(self, mock_exporter_cls):
        from main import export_frames_and_resolve_mapper
        mock_exporter = Mock()
        mock_exporter.estimate_direct_export_size.return_value = 100
        mock_exporter_cls.return_value = mock_exporter
        music_asm = self.temp_dir / "music.asm"
        args = Namespace(verbose=False, mapper='mmc1')
        pattern_result = {'patterns': {}, 'references': {}}
        frames = {"pulse1": []}

        resolved_mapper = Mock(name='mmc1-instance')

        with patch('mappers.factory.MapperFactory') as mock_factory, \
             patch('main.enforce_direct_export_dpcm_mapper') as mock_enforce, \
             patch('main.pack_dpcm_into_asm') as mock_pack:
            mock_factory.get_mapper.return_value = resolved_mapper
            mock_enforce.return_value = resolved_mapper
            mock_pack.return_value = DpcmPackResult(index_found=False)

            mapper, pack_result = export_frames_and_resolve_mapper(
                frames, pattern_result, music_asm, use_patterns=False, args=args)

        assert mapper is resolved_mapper
        # Resolved BEFORE export -- the export call itself already received
        # the concrete mapper, not None.
        assert mock_exporter.export_tables_with_patterns.call_args.kwargs['mapper'] is resolved_mapper

    @patch('main.CA65Exporter')
    def test_passes_pattern_result_references_through_to_exporter(self, mock_exporter_cls):
        """Regression (#379/PIPE-2026-07-19-3): run_full_pipeline's export
        step used to hardcode an empty `{}` for the exporter's `references`
        arg regardless of what pattern detection produced, while run_export
        (the step-by-step entry point) passes the detector's real
        `pattern_data['references']` through unmodified -- a latent
        divergence between the two entry points. Both must now feed the
        exporter the same `pattern_result['references']` value."""
        from main import export_frames_and_resolve_mapper
        mock_exporter = Mock()
        mock_exporter_cls.return_value = mock_exporter
        music_asm = self.temp_dir / "music.asm"
        args = Namespace(verbose=False, mapper=None)
        real_references = {'pattern_0': [0, 16, 32]}
        pattern_result = {'patterns': {'pattern_0': [1, 2, 3]}, 'references': real_references}
        frames = {"pulse1": []}

        with patch('main.resolve_mapper') as mock_resolve, \
             patch('main.pack_dpcm_into_asm') as mock_pack:
            mock_resolve.return_value = Mock(name='mmc3')
            mock_pack.return_value = DpcmPackResult(index_found=False)

            export_frames_and_resolve_mapper(
                frames, pattern_result, music_asm, use_patterns=True, args=args)

        assert mock_exporter.export_tables_with_patterns.call_args.args[2] == real_references

    @patch('main.CA65Exporter')
    def test_raises_on_invalid_mapper_choice(self, mock_exporter_cls):
        from main import export_frames_and_resolve_mapper
        mock_exporter_cls.return_value = Mock()
        music_asm = self.temp_dir / "music.asm"
        args = Namespace(verbose=False, mapper='mmc1')
        frames = {"pulse1": []}

        with patch('mappers.factory.MapperFactory') as mock_factory:
            mock_factory.get_mapper.side_effect = ValueError("unknown mapper")

            with pytest.raises(ValueError):
                export_frames_and_resolve_mapper(
                    frames, {'patterns': {}}, music_asm, use_patterns=False, args=args)


class TestBuildAndValidateRom:
    """Coverage for the #406/TD-11-FOLLOWUP extraction of run_full_pipeline's
    Steps 6-8. Each failure mode raises instead of calling sys.exit itself
    -- run_full_pipeline's own try/except/finally is still the only place
    that decides how to report it and whether to restore a backup (#26)."""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.music_asm = self.temp_dir / "music.asm"
        self.music_asm.write_text(".byte 1, 2, 3\n")
        self.project_path = self.temp_dir / "nes_project"
        self.output_rom = self.temp_dir / "out.nes"
        self.mapper = Mock(name="mmc3")
        self.mapper.name = "MMC3"

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('main.check_mapper_capacity')
    def test_raises_valueerror_on_capacity_overflow(self, mock_capacity):
        from main import build_and_validate_rom
        mock_capacity.side_effect = ValueError("music data exceeds capacity")
        args = Namespace(verbose=False)

        with pytest.raises(ValueError):
            build_and_validate_rom(
                self.mapper, self.music_asm, self.project_path, self.output_rom,
                debug_mode=False, skip_validation=True, args=args)

    @patch('main.NESProjectBuilder')
    @patch('main.check_mapper_capacity')
    def test_raises_exporterror_on_prepare_failure(self, mock_capacity, mock_builder_cls):
        """Regression (#457/SAFE-2026-08-21-3): a bare RuntimeError here used
        to fall through run_full_pipeline's typed/untyped split as an
        "Unexpected pipeline failure" instead of the ordinary, actionable
        outcome it is -- now a MIDI2NESError subclass (ExportError, matching
        prepare_project's own type for its other failure mode)."""
        from main import build_and_validate_rom
        from core.exceptions import ExportError, MIDI2NESError
        mock_capacity.return_value = 3
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = False
        mock_builder_cls.return_value = mock_builder
        args = Namespace(verbose=False)

        with pytest.raises(ExportError, match="prepare"):
            build_and_validate_rom(
                self.mapper, self.music_asm, self.project_path, self.output_rom,
                debug_mode=False, skip_validation=True, args=args)
        # Must be catchable through the pipeline's single expected-failure clause.
        with pytest.raises(MIDI2NESError):
            build_and_validate_rom(
                self.mapper, self.music_asm, self.project_path, self.output_rom,
                debug_mode=False, skip_validation=True, args=args)

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.check_mapper_capacity')
    def test_raises_compilationerror_on_compile_failure(
        self, mock_capacity, mock_builder_cls, mock_compile
    ):
        """Regression (#457/SAFE-2026-08-21-3): see prepare-failure test above."""
        from main import build_and_validate_rom
        from core.exceptions import CompilationError, MIDI2NESError
        mock_capacity.return_value = 3
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_cls.return_value = mock_builder
        mock_compile.return_value = False
        args = Namespace(verbose=False)

        with pytest.raises(CompilationError, match="compilation"):
            build_and_validate_rom(
                self.mapper, self.music_asm, self.project_path, self.output_rom,
                debug_mode=False, skip_validation=True, args=args)
        with pytest.raises(MIDI2NESError):
            build_and_validate_rom(
                self.mapper, self.music_asm, self.project_path, self.output_rom,
                debug_mode=False, skip_validation=True, args=args)

    @patch('main.validate_rom')
    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.check_mapper_capacity')
    def test_raises_validationerror_on_validation_failure(
        self, mock_capacity, mock_builder_cls, mock_compile, mock_validate
    ):
        """Regression (#457/SAFE-2026-08-21-3): see prepare-failure test above."""
        from main import build_and_validate_rom
        from core.exceptions import ValidationError, MIDI2NESError
        mock_capacity.return_value = 3
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_cls.return_value = mock_builder
        mock_compile.return_value = True
        mock_validate.return_value = False
        args = Namespace(verbose=False)

        with pytest.raises(ValidationError, match="validation"):
            build_and_validate_rom(
                self.mapper, self.music_asm, self.project_path, self.output_rom,
                debug_mode=False, skip_validation=False, args=args)
        with pytest.raises(MIDI2NESError):
            build_and_validate_rom(
                self.mapper, self.music_asm, self.project_path, self.output_rom,
                debug_mode=False, skip_validation=False, args=args)

    @patch('main.validate_rom')
    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.check_mapper_capacity')
    def test_skip_validation_never_calls_validate_rom(
        self, mock_capacity, mock_builder_cls, mock_compile, mock_validate
    ):
        from main import build_and_validate_rom
        mock_capacity.return_value = 3
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_cls.return_value = mock_builder
        mock_compile.return_value = True
        args = Namespace(verbose=False)

        build_and_validate_rom(
            self.mapper, self.music_asm, self.project_path, self.output_rom,
            debug_mode=False, skip_validation=True, args=args)

        mock_validate.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
