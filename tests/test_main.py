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
    run_parse, run_map, run_frames, run_prepare, run_export, run_compile,
    run_detect_patterns, run_song_add, run_song_list, run_song_remove,
    load_config, run_config_init, run_config_validate,
    run_benchmark, run_benchmark_memory, run_full_pipeline, main,
    DETECTOR_MAX_EVENTS, resolve_mapper, get_mapper_choice,
    enforce_direct_export_dpcm_mapper,
)
from core.exceptions import ConfigurationError


class TestMainArgumentParsing:
    """Test argument parsing functionality."""
    
    def test_version_argument(self):
        """Test --version argument."""
        with patch('sys.argv', ['main.py', '--version']):
            with pytest.raises(SystemExit):
                main()

    def test_version_combined_with_midi_file_prints_and_exits(self):
        """Regression (#179/PL-06): --version alongside a MIDI filename used to
        be filed into global_args where nothing consumed it, so the manual
        default-path loop ran a full pipeline build instead of printing the
        version. It must print-and-exit immediately, like argparse's bare
        --version case, without ever reaching run_full_pipeline."""
        with patch('sys.argv', ['main.py', '--version', 'nonexistent_song.mid']):
            with patch('main.run_full_pipeline') as mock_pipeline:
                with patch('builtins.print') as mock_print:
                    with pytest.raises(SystemExit) as exc:
                        main()
                    assert exc.value.code == 0
                    mock_pipeline.assert_not_called()
                    out = " ".join(str(c[0][0]) for c in mock_print.call_args_list if c[0])
                    import main as main_module
                    assert main_module.__version__ in out
    
    def test_help_argument(self):
        """Test --help argument."""
        with patch('sys.argv', ['main.py', '--help']):
            with pytest.raises(SystemExit):
                main()
    
    def test_verbose_argument_parsing(self):
        """Test verbose flag parsing with no MIDI file shows error message."""
        with patch('sys.argv', ['main.py', '--verbose']):
            with patch('builtins.print') as mock_print:
                with pytest.raises(SystemExit):
                    main()
                # Should print error message about missing MIDI file
                mock_print.assert_any_call("Error: Please provide an input MIDI file")
    
    def test_no_command_shows_help(self):
        """Test that no command shows help."""
        with patch('sys.argv', ['main.py']):
            with patch('argparse.ArgumentParser.print_help') as mock_help:
                main()
                mock_help.assert_called_once()

    def test_unknown_default_path_flag_errors(self):
        """Regression (#8): a typo'd flag on the default path must error with a
        nonzero exit, not be silently swallowed (which would build a wrong ROM)."""
        for bad in ['--no-pattern', '--arrange', '--skipvalidation']:
            with patch('sys.argv', ['main.py', bad, 'song.mid', 'out.nes']):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 2, f"{bad} should exit 2, got {exc.value.code}"

    def test_global_arranger_before_subcommand_errors(self):
        """Regression (#174): --arranger before a subcommand is a global flag
        that argparse accepts but no subcommand consumes. It must error loudly
        instead of silently falling back to legacy (non-arranger) mapping."""
        for flag in ['--arranger', '-a']:
            with patch('sys.argv', ['main.py', flag, 'map', 'parsed.json', 'mapped.json']):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 2, f"{flag} before a subcommand should exit 2, got {exc.value.code}"

    def test_arranger_after_subcommand_still_rejected_by_argparse(self):
        """--arranger placed after a subcommand (which doesn't declare it) must
        keep failing via argparse's own 'unrecognized arguments' error."""
        with patch('sys.argv', ['main.py', 'map', '--arranger', 'parsed.json', 'mapped.json']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_global_arranger_on_default_path_still_works(self):
        """--arranger before a MIDI file (no subcommand) is the supported form
        and must not be rejected by the new subcommand guard."""
        with patch('sys.argv', ['main.py', '--arranger', 'song.mid', 'out.nes']):
            with patch('builtins.print'):
                with pytest.raises(SystemExit) as exc:
                    main()
                # Fails later on missing input file, not on flag parsing (exit 1),
                # confirming --arranger was accepted and reached the pipeline.
                assert exc.value.code != 2

    def test_default_path_config_flag_is_accepted_and_threaded(self):
        """Regression (#219): --config on the default (no-subcommand) pipeline
        must be accepted (a value-taking flag, unlike the boolean ones) and
        reach run_full_pipeline's args.config, not be rejected as unknown."""
        with patch('main.run_full_pipeline') as mock_run:
            with patch('sys.argv', ['main.py', '--config', 'cfg.yaml', 'song.mid', 'out.nes']):
                main()
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0].config == 'cfg.yaml'

    def test_default_path_config_flag_requires_value(self):
        """--config with no trailing path must exit 2, not crash or hang."""
        with patch('sys.argv', ['main.py', '--config']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_default_path_mapper_flag_is_accepted_and_threaded(self):
        """Regression (#217/MAP-6): --mapper on the default (no-subcommand)
        pipeline must be accepted and reach run_full_pipeline's args.mapper."""
        with patch('main.run_full_pipeline') as mock_run:
            with patch('sys.argv', ['main.py', '--mapper', 'auto', 'song.mid', 'out.nes']):
                main()
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0].mapper == 'auto'

    def test_default_path_mapper_flag_defaults_to_mmc3(self):
        """With no --mapper on the default path, args.mapper must default to
        'mmc3' so run_full_pipeline's behavior is unchanged for existing callers."""
        with patch('main.run_full_pipeline') as mock_run:
            with patch('sys.argv', ['main.py', 'song.mid', 'out.nes']):
                main()
        assert mock_run.call_args[0][0].mapper == 'mmc3'

    def test_default_path_mapper_flag_rejects_unknown_value(self):
        """--mapper with an unrecognized value must exit 2, not silently pass
        a bad string through to resolve_mapper deep in the pipeline."""
        with patch('sys.argv', ['main.py', '--mapper', 'bogus', 'song.mid', 'out.nes']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_default_path_mapper_flag_requires_value(self):
        """--mapper with no trailing value must exit 2, not crash or hang."""
        with patch('sys.argv', ['main.py', '--mapper']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_prepare_subcommand_accepts_mapper_choices(self):
        """The `prepare` subcommand must expose --mapper with the auto/nrom/
        mmc1/mmc3 choices (#217/MAP-6)."""
        with patch('main.run_prepare') as mock_run:
            with patch('sys.argv', ['main.py', 'prepare', 'music.asm', 'out_dir', '--mapper', 'nrom']):
                main()
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0].mapper == 'nrom'

    def test_prepare_subcommand_rejects_unknown_mapper(self):
        with patch('sys.argv', ['main.py', 'prepare', 'music.asm', 'out_dir', '--mapper', 'bogus']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_compile_subcommand_accepts_mapper_but_not_auto(self):
        """The `compile` subcommand's --mapper must accept concrete mapper
        names but not 'auto' -- there is no music.asm data size to derive an
        auto-selection from once a project directory is already prepared."""
        with patch('main.run_compile') as mock_run:
            with patch('sys.argv', ['main.py', 'compile', 'project_dir', 'out.nes', '--mapper', 'mmc1']):
                main()
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0].mapper == 'mmc1'

        with patch('sys.argv', ['main.py', 'compile', 'project_dir', 'out.nes', '--mapper', 'auto']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2


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
    
    @patch('tracker.parser_fast.parse_midi_to_frames')
    @patch('builtins.print')
    def test_run_parse_success(self, mock_print, mock_parse):
        """Test successful MIDI parsing."""
        # Create a test MIDI file to avoid FileNotFoundError
        self.test_input.touch()
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}}
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_parse(args)
        
        mock_parse.assert_called_once_with(str(self.test_input))
        assert self.test_output.exists()
        
        # Verify JSON content
        content = json.loads(self.test_output.read_text())
        assert "events" in content
        
        mock_print.assert_called_once_with(f"[OK] Parsed MIDI -> {args.output}")
    
    @patch('tracker.parser_fast.parse_midi_to_frames')
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
    
    @patch('main.assign_tracks_to_nes_channels')
    @patch('builtins.print')
    def test_run_map_honors_dpcm_index(self, mock_print, mock_assign):
        """Regression (#13): --dpcm-index must be passed to the mapper, not the default."""
        mock_assign.return_value = {"channel_0": []}
        # The index must exist so the #256 missing-index guard doesn't fire
        # before the forwarding this test checks; write a minimal one.
        custom_index = self.temp_dir / "custom_dpcm.json"
        custom_index.write_text("{}")
        args = Namespace(input=str(self.test_input), output=str(self.test_output),
                         dpcm_index=str(custom_index))

        run_map(args)

        mock_assign.assert_called_once_with({"0": [{"frame": 0, "note": 60}]}, str(custom_index))

    @patch('main.assign_tracks_to_nes_channels')
    def test_run_map_missing_dpcm_index_exits_cleanly(self, mock_assign):
        """Regression (#256/D-18): a missing DPCM index made the `map` subcommand
        crash with a raw FileNotFoundError traceback (unlike the packer path).
        It must exit cleanly with an [ERROR] and never reach the mapper."""
        missing = self.temp_dir / "does_not_exist.json"
        args = Namespace(input=str(self.test_input), output=str(self.test_output),
                         dpcm_index=str(missing))

        with patch('builtins.print') as mock_print:
            with pytest.raises(SystemExit) as exc:
                run_map(args)

        assert exc.value.code == 1
        mock_assign.assert_not_called()
        assert not self.test_output.exists()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        assert "[ERROR]" in printed and "DPCM index not found" in printed

    def test_map_parser_has_no_silent_config_flag(self):
        """Regression (#13): the unused --config flag was dropped from `map`."""
        from main import main as main_entry
        with patch('sys.argv', ['main.py', 'map', '--config', 'x.yaml', 'i.json', 'o.json']):
            with pytest.raises(SystemExit):
                main_entry()

    def test_detect_patterns_parser_consumes_config_flag(self):
        """Regression (#219, supersedes the #109 removal): `detect-patterns
        --config` is now read and forwarded to run_detect_patterns to override
        the sequential detector's max_events sampling cap, instead of being an
        unrecognized/silently-dropped flag."""
        from main import main as main_entry
        with patch('main.run_detect_patterns') as mock_run:
            with patch('sys.argv', ['main.py', 'detect-patterns', '--config', 'x.yaml',
                                     'i.json', 'o.json']):
                main_entry()
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert called_args.config == 'x.yaml'

    def test_song_add_parser_has_no_silent_config_flag(self):
        """Regression (#109, SIBLING): the unused --config flag was dropped from
        `song add` (it was declared but never read by run_song_add)."""
        from main import main as main_entry
        with patch('sys.argv', ['main.py', 'song', 'add', '--config', 'x.yaml', 'i.mid']):
            with pytest.raises(SystemExit):
                main_entry()

    def test_run_map_missing_events_key(self):
        """Regression (#110, #120): a parse output without an 'events' key must
        fail with a clear [ERROR] message and exit 1, not a bare KeyError
        traceback."""
        self.test_input.write_text(json.dumps({"tracks": {}}))
        args = Namespace(input=str(self.test_input), output=str(self.test_output))

        with patch('builtins.print') as mock_print:
            with pytest.raises(SystemExit) as exc:
                run_map(args)
        assert exc.value.code == 1
        mock_print.assert_any_call(
            "[ERROR] parse input missing expected key(s) ['events']: "
            f"{self.test_input} (is this the right stage's JSON?)")

    def test_run_map_invalid_json(self):
        """Regression (#120): invalid JSON must fail with a clear [ERROR]
        message and exit 1, not a bare JSONDecodeError traceback."""
        self.test_input.write_text("invalid json")
        args = Namespace(input=str(self.test_input), output=str(self.test_output))

        with pytest.raises(SystemExit) as exc:
            run_map(args)
        assert exc.value.code == 1

    def test_run_map_missing_file(self):
        """Regression (#120): a missing input file must fail with a clear
        [ERROR] message and exit 1, not a bare FileNotFoundError traceback."""
        args = Namespace(input="nonexistent.json", output=str(self.test_output))

        with pytest.raises(SystemExit) as exc:
            run_map(args)
        assert exc.value.code == 1


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

    def test_run_frames_missing_file(self):
        """Regression (#120): a missing input file must fail with a clear
        [ERROR] message and exit 1, not a bare FileNotFoundError traceback."""
        args = Namespace(input="nonexistent.json", output=str(self.test_output))
        with pytest.raises(SystemExit) as exc:
            run_frames(args)
        assert exc.value.code == 1

    def test_run_frames_invalid_json(self):
        """Regression (#120): invalid JSON must fail with a clear [ERROR]
        message and exit 1, not a bare JSONDecodeError traceback."""
        self.test_input.write_text("not json")
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        with pytest.raises(SystemExit) as exc:
            run_frames(args)
        assert exc.value.code == 1


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
        
        mock_builder_class.assert_called_once()
        assert mock_builder_class.call_args[0][0] == str(self.test_output)
        mock_builder.prepare_project.assert_called_once_with(str(self.test_input))
        
        # Check success print calls (now includes the `compile` hint line, #15,
        # and the mapper-capacity line, #217/MAP-6)
        assert mock_print.call_count == 7
        mock_print.assert_any_call(f" Prepared NES project -> {args.output}")
        mock_print.assert_any_call(" Ready for CC65 compilation!")

    @patch('main.NESProjectBuilder')
    def test_run_prepare_failure(self, mock_builder_class):
        """Test failed project preparation exits nonzero (#15), not exit 0 silently."""
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = False
        mock_builder_class.return_value = mock_builder

        args = Namespace(input=str(self.test_input), output=str(self.test_output))

        with pytest.raises(SystemExit) as exc:
            run_prepare(args)
        assert exc.value.code == 1
        mock_builder_class.assert_called_once()

    @patch('main.NESProjectBuilder')
    @patch('builtins.print')
    def test_run_prepare_honors_debug_flag(self, mock_print, mock_builder_class):
        """Regression (#175): global --debug must reach the builder's debug_mode,
        not be silently discarded like --arranger was (#174)."""
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        args = Namespace(input=str(self.test_input), output=str(self.test_output), debug=True)

        run_prepare(args)

        assert mock_builder_class.call_args.kwargs['debug_mode'] is True

    @patch('main.NESProjectBuilder')
    @patch('builtins.print')
    def test_run_prepare_defaults_debug_false(self, mock_print, mock_builder_class):
        """Without --debug (or on a Namespace that lacks the attribute), the
        builder must still be built in non-debug mode."""
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        args = Namespace(input=str(self.test_input), output=str(self.test_output))

        run_prepare(args)

        assert mock_builder_class.call_args.kwargs['debug_mode'] is False
        assert mock_builder_class.call_args[0][0] == str(self.test_output)

    @patch('main.NESProjectBuilder')
    @patch('builtins.print')
    def test_run_prepare_defaults_to_mmc3(self, mock_print, mock_builder_class):
        """Regression (#217/MAP-6): with no --mapper, prepare must still
        default to MMC3, matching pre-existing behavior."""
        from mappers.mmc3 import MMC3Mapper
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        run_prepare(args)

        used_mapper = mock_builder_class.call_args.kwargs['mapper']
        assert isinstance(used_mapper, MMC3Mapper)

    @patch('main.NESProjectBuilder')
    @patch('builtins.print')
    def test_run_prepare_honors_explicit_mapper(self, mock_print, mock_builder_class):
        """Regression (#217/MAP-6): --mapper nrom must reach the builder as an
        NROMMapper instance, not always MMC3Mapper."""
        from mappers.nrom import NROMMapper
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        args = Namespace(input=str(self.test_input), output=str(self.test_output), mapper='nrom')
        run_prepare(args)

        used_mapper = mock_builder_class.call_args.kwargs['mapper']
        assert isinstance(used_mapper, NROMMapper)

    @patch('main.NESProjectBuilder')
    @patch('builtins.print')
    def test_run_prepare_mapper_auto_selects_smallest_that_fits(self, mock_print, mock_builder_class):
        """Regression (#217/MAP-6): --mapper auto must reach
        MapperFactory.auto_select() via a real pipeline path, not just
        tests/test_mappers.py. A tiny music.asm easily fits NROM."""
        from mappers.nrom import NROMMapper
        self.test_input.write_text('.segment "CODE"\n.byte 1, 2, 3, 4\n')

        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_class.return_value = mock_builder

        args = Namespace(input=str(self.test_input), output=str(self.test_output), mapper='auto')
        run_prepare(args)

        used_mapper = mock_builder_class.call_args.kwargs['mapper']
        assert isinstance(used_mapper, NROMMapper)


class TestResolveMapper:
    """Regression tests for resolve_mapper() (#217/MAP-6): wires
    MapperFactory.auto_select()/get_mapper() to a real CLI path instead of
    leaving them reachable only from tests/test_mappers.py."""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_explicit_name_returns_matching_mapper(self):
        from mappers.mmc1 import MMC1Mapper
        assert isinstance(resolve_mapper('mmc1'), MMC1Mapper)

    def test_get_mapper_choice_defaults_for_magicmock_args(self):
        """Regression: discovered via tests/test_e2e_pipeline.py's
        MagicMock()-based args fixture. MagicMock auto-vivifies any accessed
        attribute instead of raising AttributeError, so a plain
        getattr(args, 'mapper', 'mmc3') silently returns a MagicMock instead
        of falling back to 'mmc3' -- get_mapper_choice() must catch this."""
        args = MagicMock()
        assert get_mapper_choice(args) == 'mmc3'

    def test_get_mapper_choice_honors_real_string(self):
        args = Namespace(mapper='nrom')
        assert get_mapper_choice(args) == 'nrom'

    def test_get_mapper_choice_defaults_for_missing_attribute(self):
        args = Namespace()
        assert get_mapper_choice(args) == 'mmc3'

    def test_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError):
            resolve_mapper('not-a-real-mapper')

    def test_auto_selects_smallest_mapper_that_fits(self):
        from mappers.nrom import NROMMapper
        music_asm = self.temp_dir / "music.asm"
        music_asm.write_text('.segment "CODE"\n.byte 1, 2, 3\n')
        assert isinstance(resolve_mapper('auto', str(music_asm)), NROMMapper)

    def test_auto_selects_larger_mapper_for_larger_data(self):
        from mappers.nrom import NROMMapper
        from mappers.mmc3 import MMC3Mapper
        music_asm = self.temp_dir / "music.asm"
        # NROM's usable capacity is well under 32KB; emit enough .byte data
        # to overflow it so auto-select must skip up to a bigger mapper.
        nrom_capacity = NROMMapper().get_data_capacity()
        lines = ['.segment "CODE"']
        row = ", ".join(["1"] * 40)
        rows_needed = (nrom_capacity // 40) + 100
        lines.extend([f'.byte {row}'] * rows_needed)
        music_asm.write_text("\n".join(lines))
        mapper = resolve_mapper('auto', str(music_asm))
        assert not isinstance(mapper, NROMMapper)

    def test_auto_forces_mmc3_for_bytecode_music_asm(self):
        """Regression: discovered while wiring up #217/MAP-6. A music.asm
        built by the MMC3 macro-bytecode exporter references
        `switch_dpcm_bank`, which only MMC3's generate_bank_switch_code()
        actually defines as a labeled routine -- NROM/MMC1 builds in this
        mode fail to link. 'auto' must not pick a smaller mapper just
        because the (tiny) data would otherwise fit it."""
        from mappers.mmc3 import MMC3Mapper
        music_asm = self.temp_dir / "music.asm"
        music_asm.write_text('; CA65 Assembly Export (MMC3 Macro Bytecode)\n.segment "CODE"\n.byte 1\n')
        assert isinstance(resolve_mapper('auto', str(music_asm)), MMC3Mapper)

    def test_explicit_non_mmc3_mapper_rejected_for_bytecode_music_asm(self):
        """Regression: same discovery as above, for an explicit (non-auto)
        --mapper choice. Must fail with a clear ValueError, not proceed to a
        cryptic ld65 'unresolved external' at link time."""
        music_asm = self.temp_dir / "music.asm"
        music_asm.write_text('; CA65 Assembly Export (MMC3 Macro Bytecode)\n.segment "CODE"\n.byte 1\n')
        with pytest.raises(ValueError, match="MMC3 macro-bytecode"):
            resolve_mapper('nrom', str(music_asm))

    def test_explicit_mmc3_accepted_for_bytecode_music_asm(self):
        from mappers.mmc3 import MMC3Mapper
        music_asm = self.temp_dir / "music.asm"
        music_asm.write_text('; CA65 Assembly Export (MMC3 Macro Bytecode)\n.segment "CODE"\n.byte 1\n')
        assert isinstance(resolve_mapper('mmc3', str(music_asm)), MMC3Mapper)

    def test_non_bytecode_music_asm_does_not_force_mmc3(self):
        """A direct-frame-export music.asm (no patterns) has no bank-switching
        dependency, so a small/explicit non-MMC3 mapper choice must proceed
        normally."""
        from mappers.nrom import NROMMapper
        music_asm = self.temp_dir / "music.asm"
        music_asm.write_text('; CA65 Assembly Export (Direct Frame Data)\n.segment "CODE"\n.byte 1\n')
        assert isinstance(resolve_mapper('nrom', str(music_asm)), NROMMapper)

    # --- Direct-export bank-pack mapper-identity guard (#283/MAP-2026-07-05B-3,
    # #285/PL-09). CA65Exporter.export_direct_frames stamps a "; Direct export
    # bank-packed for <name>" marker when it bin-packs frame tables into
    # RODATA_BANK_NN segments only that mapper's linker config defines, so a
    # mismatched --mapper at prepare/compile is caught up front instead of via a
    # raw ld65 "Missing memory area assignment" error. Mirrors the bytecode
    # marker guard above. ---

    def _bank_packed_music_asm(self, name='MMC1'):
        music_asm = self.temp_dir / "music.asm"
        music_asm.write_text(
            '; CA65 Assembly Export (Direct Frame Data)\n'
            f'; Direct export bank-packed for {name}\n'
            '.segment "RODATA_BANK_00"\n.byte 1\n')
        return music_asm

    def test_bank_packed_music_asm_rejects_mismatched_explicit_mapper(self):
        music_asm = self._bank_packed_music_asm('MMC1')
        with pytest.raises(ValueError, match="bank-packed for MMC1"):
            resolve_mapper('mmc3', str(music_asm))

    def test_bank_packed_music_asm_rejects_nrom(self):
        music_asm = self._bank_packed_music_asm('MMC1')
        with pytest.raises(ValueError, match="bank-packed for MMC1"):
            resolve_mapper('nrom', str(music_asm))

    def test_bank_packed_music_asm_accepts_matching_explicit_mapper(self):
        from mappers.mmc1 import MMC1Mapper
        music_asm = self._bank_packed_music_asm('MMC1')
        assert isinstance(resolve_mapper('mmc1', str(music_asm)), MMC1Mapper)

    def test_auto_honors_bank_pack_marker_over_size(self):
        """'auto' must pick the mapper the tables were bank-packed for, not
        re-estimate a smaller one by (tiny) data size."""
        from mappers.mmc1 import MMC1Mapper
        music_asm = self._bank_packed_music_asm('MMC1')
        assert isinstance(resolve_mapper('auto', str(music_asm)), MMC1Mapper)

    def test_unpacked_direct_export_has_no_bank_pack_constraint(self):
        """A direct export that did NOT bank-pack (no marker) leaves the mapper
        choice unconstrained -- a plain NROM/MMC3 build proceeds normally."""
        from mappers.nrom import NROMMapper
        music_asm = self.temp_dir / "music.asm"
        music_asm.write_text('; CA65 Assembly Export (Direct Frame Data)\n.segment "RODATA"\n.byte 1\n')
        assert isinstance(resolve_mapper('nrom', str(music_asm)), NROMMapper)

    def test_bank_pack_marker_is_emitted_by_the_exporter(self):
        """End-to-end pin: the MMC1 direct export actually stamps the marker
        resolve_mapper reads back (guards against the two drifting apart)."""
        from exporter.exporter_ca65 import CA65Exporter
        from mappers.mmc1 import MMC1Mapper
        frames = {'pulse1': {str(i): {'note': 60, 'volume': 8} for i in range(300)}}
        out = self.temp_dir / "packed.asm"
        CA65Exporter().export_direct_frames(frames, str(out), standalone=False, mapper=MMC1Mapper())
        assert "; Direct export bank-packed for MMC1" in out.read_text()


class TestEnforceDirectExportDpcmMapper:
    """Regression tests for enforce_direct_export_dpcm_mapper()
    (#281/MAP-2026-07-05B-1, #282/MAP-2026-07-05B-2).

    Direct-export DPCM emits two hardcoded MMC3-only pieces: play_dpcm writes
    MMC3's R6 bank-select port ($8000/$8001) -- which is MMC1's serial shift
    register, corrupting its Control word (#281) -- and DpcmPacker emits
    DPCM_NN segments only mmc3's nes.cfg defines (#282). The gate must force
    MMC3 for 'auto' and reject an explicit non-MMC3 mapper, but leave a song
    with no DPCM channel untouched."""

    def _dpcm_frames(self):
        return {'dpcm': {'0': {'note': 60, 'volume': 0}}}

    def _no_dpcm_frames(self):
        return {'pulse1': {'0': {'note': 60, 'volume': 8}}}

    def test_auto_forces_mmc3_when_song_has_dpcm(self):
        from mappers.nrom import NROMMapper
        from mappers.mmc3 import MMC3Mapper
        # auto_select on tiny data would pick NROM; DPCM must override to MMC3.
        result = enforce_direct_export_dpcm_mapper(
            NROMMapper(), 'auto', self._dpcm_frames())
        assert isinstance(result, MMC3Mapper)

    def test_explicit_mmc1_rejected_when_song_has_dpcm(self):
        from mappers.mmc1 import MMC1Mapper
        with pytest.raises(ValueError, match="DPCM"):
            enforce_direct_export_dpcm_mapper(
                MMC1Mapper(), 'mmc1', self._dpcm_frames())

    def test_explicit_nrom_rejected_when_song_has_dpcm(self):
        from mappers.nrom import NROMMapper
        with pytest.raises(ValueError, match="DPCM"):
            enforce_direct_export_dpcm_mapper(
                NROMMapper(), 'nrom', self._dpcm_frames())

    def test_explicit_mmc3_accepted_when_song_has_dpcm(self):
        from mappers.mmc3 import MMC3Mapper
        result = enforce_direct_export_dpcm_mapper(
            MMC3Mapper(), 'mmc3', self._dpcm_frames())
        assert isinstance(result, MMC3Mapper)

    def test_non_mmc3_untouched_without_dpcm_channel(self):
        from mappers.mmc1 import MMC1Mapper
        result = enforce_direct_export_dpcm_mapper(
            MMC1Mapper(), 'mmc1', self._no_dpcm_frames())
        assert isinstance(result, MMC1Mapper)

    def test_empty_dpcm_channel_is_not_a_trigger(self):
        """An empty dpcm channel emits no play_dpcm (mirrors the exporter's
        has_dpcm = non-empty channel), so it must not force/reject a mapper."""
        from mappers.mmc1 import MMC1Mapper
        result = enforce_direct_export_dpcm_mapper(
            MMC1Mapper(), 'mmc1', {'dpcm': {}})
        assert isinstance(result, MMC1Mapper)


class TestRunCompile:
    """Test run_compile's --mapper wiring (#217/MAP-6)."""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_dir = self.temp_dir / "project"
        self.project_dir.mkdir()
        self.output_rom = self.temp_dir / "out.nes"

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('main.validate_rom')
    @patch('main.compile_rom')
    def test_run_compile_defaults_to_mmc3(self, mock_compile, mock_validate):
        from mappers.mmc3 import MMC3Mapper
        mock_compile.return_value = True
        mock_validate.return_value = True

        args = Namespace(input=str(self.project_dir), output=str(self.output_rom),
                          skip_validation=True, verbose=False)
        run_compile(args)

        used_mapper = mock_compile.call_args.kwargs['mapper']
        assert isinstance(used_mapper, MMC3Mapper)

    @patch('main.validate_rom')
    @patch('main.compile_rom')
    def test_run_compile_honors_explicit_mapper(self, mock_compile, mock_validate):
        from mappers.nrom import NROMMapper
        mock_compile.return_value = True
        mock_validate.return_value = True

        args = Namespace(input=str(self.project_dir), output=str(self.output_rom),
                          skip_validation=True, verbose=False, mapper='nrom')
        run_compile(args)

        used_mapper = mock_compile.call_args.kwargs['mapper']
        assert isinstance(used_mapper, NROMMapper)


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
        
        # Export must report success. Don't assert this is the *only* print:
        # run_export also packs DPCM from the repo's dpcm_index.json, which can
        # legitimately emit a warning (e.g. an oversized sample, #68) without
        # affecting the export dispatch this test covers.
        mock_print.assert_any_call(f" Exported CA65 ASM -> {args.output}")
    
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

    @patch('main.CA65Exporter')
    @patch('builtins.print')
    def test_run_export_resolves_explicit_mapper_before_direct_export(self, mock_print, mock_exporter_class):
        """Regression (#255/MAP-2026-07-05-1): a bank-switching-aware direct
        export needs to know the target mapper up front, not after the fact
        (unlike the old behavior of measuring an already-exported file).
        run_export must resolve --mapper and pass a real mapper instance into
        export_tables_with_patterns for a direct (no-patterns) export."""
        from mappers.mmc1 import MMC1Mapper
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        args = Namespace(
            input=str(self.test_input),
            output=str(self.test_output),
            format="ca65",
            patterns=None,
            mapper='mmc1'
        )
        run_export(args)

        call_kwargs = mock_exporter.export_tables_with_patterns.call_args.kwargs
        assert isinstance(call_kwargs['mapper'], MMC1Mapper)
        # estimate_direct_export_size is only needed for 'auto'.
        mock_exporter.estimate_direct_export_size.assert_not_called()

    @patch('main.CA65Exporter')
    @patch('builtins.print')
    def test_run_export_auto_mapper_estimates_size_before_export(self, mock_print, mock_exporter_class):
        """--mapper auto must estimate size from `frames` (via the exporter's
        own estimate_direct_export_size) BEFORE exporting, then pass the
        resolved mapper through -- not measure the file after export."""
        from mappers.nrom import NROMMapper
        mock_exporter = Mock()
        mock_exporter.estimate_direct_export_size.return_value = 1024
        mock_exporter_class.return_value = mock_exporter

        args = Namespace(
            input=str(self.test_input),
            output=str(self.test_output),
            format="ca65",
            patterns=None,
            mapper='auto'
        )
        run_export(args)

        mock_exporter.estimate_direct_export_size.assert_called_once()
        call_kwargs = mock_exporter.export_tables_with_patterns.call_args.kwargs
        assert isinstance(call_kwargs['mapper'], NROMMapper)

    @patch('main.CA65Exporter')
    @patch('builtins.print')
    def test_run_export_bytecode_mode_leaves_mapper_unresolved(self, mock_print, mock_exporter_class):
        """When real patterns are supplied (bytecode/MMC3 path), run_export
        must not try to resolve a mapper itself -- it passes mapper=None
        through, matching prior behavior for that path."""
        mock_exporter = Mock()
        mock_exporter_class.return_value = mock_exporter

        args = Namespace(
            input=str(self.test_input),
            output=str(self.test_output),
            format="ca65",
            patterns=str(self.test_patterns),
            mapper='mmc1'
        )
        run_export(args)

        call_kwargs = mock_exporter.export_tables_with_patterns.call_args.kwargs
        assert call_kwargs['mapper'] is None

    def test_run_export_missing_frames_file(self):
        """Regression (#120): a missing frames file must fail with a clear
        [ERROR] message and exit 1, not a bare FileNotFoundError traceback."""
        args = Namespace(input="nonexistent.json", output=str(self.test_output),
                          format="ca65", patterns=None)
        with pytest.raises(SystemExit) as exc:
            run_export(args)
        assert exc.value.code == 1

    def test_run_export_missing_patterns_file(self):
        """Regression (#120): a missing --patterns file must fail with a clear
        [ERROR] message and exit 1, not a bare FileNotFoundError traceback."""
        args = Namespace(input=str(self.test_input), output=str(self.test_output),
                          format="ca65", patterns="nonexistent_patterns.json")
        with pytest.raises(SystemExit) as exc:
            run_export(args)
        assert exc.value.code == 1

    def test_run_export_wrong_stage_patterns_file(self):
        """Regression (#120): a --patterns file from the wrong stage (missing
        'patterns'/'references') must fail with a clear [ERROR] message and
        exit 1, not a bare KeyError traceback."""
        wrong_stage_file = self.temp_dir / "frames_not_patterns.json"
        wrong_stage_file.write_text(json.dumps({"channel_0": {}}))
        args = Namespace(input=str(self.test_input), output=str(self.test_output),
                          format="ca65", patterns=str(wrong_stage_file))
        with pytest.raises(SystemExit) as exc:
            run_export(args)
        assert exc.value.code == 1

    @patch('main.CA65Exporter')
    def test_run_export_dpcm_pack_failure_surfaced_prominently(self, mock_exporter_class):
        """Regression (#123): a corrupt dpcm_index.json must not be silently
        swallowed -- the failure must be surfaced after the main success line
        (prominent), not just as an easy-to-miss warning printed above it."""
        import shutil
        mock_exporter_class.return_value = Mock()
        cwd = os.getcwd()
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "dpcm_index.json").write_text("not valid json")
            os.chdir(tmp)
            args = Namespace(input=str(self.test_input), output=str(self.test_output),
                              format="ca65", patterns=None)
            with patch('builtins.print') as mock_print:
                run_export(args)
            messages = [str(c.args[0]) for c in mock_print.call_args_list if c.args]
            exported_idx = next(i for i, m in enumerate(messages) if "Exported CA65 ASM" in m)
            warning_idx = next(i for i, m in enumerate(messages) if "NO DRUMS" in m)
            assert warning_idx > exported_idx, "the NO DRUMS warning must come after the success line"
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_export_rerun_on_same_output_does_not_duplicate_dpcm_block(self):
        """Regression (#23/F-10): run_export appends the packed DPCM assembly
        with open(args.output, 'a'). Re-running export onto the same
        step-by-step output path must not produce a second DPCM block (which
        would fail assembly with duplicate dpcm_* symbols) -- the CA65 table
        write ahead of the append always opens output_path in 'w' mode, so
        any prior content (including a previously-appended DPCM block) is
        truncated before this run's own single append happens."""
        import shutil
        cwd = os.getcwd()
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "dpcm_index.json").write_text(json.dumps({
                "test_kick": {"id": 0, "filename": "test_kick.dmc"}
            }))
            os.chdir(tmp)
            args = Namespace(input=str(self.test_input), output=str(self.test_output),
                              format="ca65", patterns=None)

            run_export(args)
            first_content = self.test_output.read_text()
            assert first_content.count("dpcm_bank_table:") == 1

            run_export(args)
            second_content = self.test_output.read_text()
            assert second_content.count("dpcm_bank_table:") == 1
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_export_rejects_nsf_format(self):
        """Regression (#79): `--format nsf` used to be accepted by argparse but
        dispatched on the impossible string "nsftxt", so it silently wrote
        nothing. NSF is dropped from the choices until the exporter is real
        (#81), so the parser must now reject it up front instead of no-oping."""
        from main import main as main_entry
        with patch('sys.argv', ['main.py', 'export', 'i.json', 'o.asm',
                                 '--format', 'nsf']):
            with pytest.raises(SystemExit):
                main_entry()


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
            'stats': {'compression_ratio': 2.5, 'total_events': 40,
                      'coverage_ratio': 30.0}
        }
        mock_detector_class.return_value = mock_detector
        
        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        
        run_detect_patterns(args)
        
        # Verify mocks were called correctly
        mock_tempo_class.assert_called_once_with(initial_tempo=500000)
        # Shared pattern bounds keep this path in sync with the full pipeline (#19).
        # max_events defaults to DETECTOR_MAX_EVENTS unless --config overrides it (#219).
        # analyze_tempo=False: this tempo_map has no real tempo-change data, so
        # the per-pattern tempo analysis would only produce a discarded
        # constant result (#119).
        mock_detector_class.assert_called_once_with(
            mock_tempo, min_pattern_length=3, max_pattern_length=12,
            max_events=DETECTOR_MAX_EVENTS, analyze_tempo=False)
        mock_detector.detect_patterns.assert_called_once()
        
        # Verify output file was created
        assert self.test_output.exists()
        content = json.loads(self.test_output.read_text())
        assert 'patterns' in content
        assert 'references' in content
        assert 'stats' in content
        assert content['stats']['compression_ratio'] == 2.5
        
        # Verify print calls
        assert mock_print.call_count == 3
        mock_print.assert_any_call(f" Detected patterns -> {args.output}")
        # Regression (#17): compression_ratio is a percentage reduction, so it is
        # printed with a `%` unit, never a bare number or an `x` multiplier.
        # Regression (#169/PAT-03): labeled as a patterned-subset-only dedup
        # ratio, not a whole-song metric, with a separate coverage line.
        mock_print.assert_any_call(" Pattern dedup ratio: 2.5% reduction (patterned subset only)")
        mock_print.assert_any_call(" Pattern coverage: 30.0% of 40 events matched a detected pattern")

    @patch('main.EnhancedPatternDetector')
    @patch('main.EnhancedTempoMap')
    @patch('builtins.print')
    def test_run_detect_patterns_labels_coverage_as_lossy_when_sampled(
            self, mock_print, mock_tempo_class, mock_detector_class):
        # Regression (#312/PAT-11): uniform sampling for a large input can put
        # retained samples out of phase with the song's period, collapsing
        # coverage_ratio well below what the full song would report. The
        # printed coverage line must say so instead of reading like a
        # full-song measurement.
        large_frames = {
            "channel_0": {
                str(i): {"note": 60 + (i % 12), "volume": 15}
                for i in range(DETECTOR_MAX_EVENTS + 500)
            }
        }
        self.test_input.write_text(json.dumps(large_frames))

        mock_tempo_class.return_value = Mock()
        mock_detector = Mock()
        mock_detector.detect_patterns.return_value = {
            'patterns': {},
            'references': {},
            'stats': {'compression_ratio': 1.0, 'total_events': DETECTOR_MAX_EVENTS,
                      'coverage_ratio': 1.0}
        }
        mock_detector_class.return_value = mock_detector

        args = Namespace(input=str(self.test_input), output=str(self.test_output))
        run_detect_patterns(args)

        mock_print.assert_any_call(
            " Pattern coverage: 1.0% of 1,000 events matched a detected pattern "
            "(lossy — measured over the sampled subset, detection quality reduced)")

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
                    'stats': {'compression_ratio': 1.0, 'total_events': 0,
                              'coverage_ratio': 0}
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

    @patch('builtins.print')
    def test_run_song_add_corrupt_bank_exits_cleanly(self, mock_print):
        """Regression (#220/SAFE-09): a corrupt --bank file must exit(1)
        with a clean [ERROR] message, not a raw traceback."""
        self.test_bank.write_text("{not valid json")

        args = Namespace(
            input=str(self.test_midi),
            bank=str(self.test_bank),
            name="Test Song",
            composer=None,
            loop_point=None,
            tags=None,
            tempo=120
        )

        with pytest.raises(SystemExit) as exc_info:
            run_song_add(args)
        assert exc_info.value.code == 1
        printed_text = " ".join(str(call[0][0]) for call in mock_print.call_args_list)
        assert "[ERROR]" in printed_text

    @patch('builtins.print')
    def test_run_song_list_corrupt_bank_exits_cleanly(self, mock_print):
        """Regression (#220/SAFE-09): same guard for `song list`."""
        self.test_bank.write_text("{not valid json")

        args = Namespace(bank=str(self.test_bank))

        with pytest.raises(SystemExit) as exc_info:
            run_song_list(args)
        assert exc_info.value.code == 1
        printed_text = " ".join(str(call[0][0]) for call in mock_print.call_args_list)
        assert "[ERROR]" in printed_text

    @patch('builtins.print')
    def test_run_song_remove_corrupt_bank_exits_cleanly(self, mock_print):
        """Regression (#220/SAFE-09): same guard for `song remove`."""
        self.test_bank.write_text("{not valid json")

        args = Namespace(bank=str(self.test_bank), name="Test Song")

        with pytest.raises(SystemExit) as exc_info:
            run_song_remove(args)
        assert exc_info.value.code == 1
        printed_text = " ".join(str(call[0][0]) for call in mock_print.call_args_list)
        assert "[ERROR]" in printed_text


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


class TestGetPatternDetectionCaps:
    """Regression tests for #219: get_pattern_detection_caps must default to
    the hardcoded constants and honor a config file override when given."""

    def test_defaults_when_no_config_path(self):
        from main import (
            get_pattern_detection_caps, DETECTOR_MAX_EVENTS, MAX_PATTERN_EVENTS,
            LARGE_FILE_THRESHOLD_DEFAULT
        )
        max_events, max_pattern_events, large_file_threshold = get_pattern_detection_caps(None)
        assert max_events == DETECTOR_MAX_EVENTS
        assert max_pattern_events == MAX_PATTERN_EVENTS
        assert large_file_threshold == LARGE_FILE_THRESHOLD_DEFAULT
        # #334/PERF-14: the advisory threshold defaults in lockstep with the
        # parallel detector's real sampling cap, not an unrelated magic number.
        assert large_file_threshold == MAX_PATTERN_EVENTS

    def test_overridden_by_config_file(self):
        from main import get_pattern_detection_caps
        temp_dir = Path(tempfile.mkdtemp())
        try:
            config_path = temp_dir / "config.yaml"
            config_path.write_text(
                "processing:\n"
                "  pattern_detection:\n"
                "    max_events: 250\n"
                "    max_pattern_events: 5000\n"
                "    large_file_threshold: 4000\n"
            )
            max_events, max_pattern_events, large_file_threshold = get_pattern_detection_caps(str(config_path))
            assert max_events == 250
            assert max_pattern_events == 5000
            assert large_file_threshold == 4000
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_missing_config_path_exits_cleanly(self):
        """Regression (#267/PL-07): a --config path that doesn't exist must
        print a clean [ERROR] and exit 1, not silently use defaults and not
        propagate a raw ConfigurationError traceback (this function has no
        outer caller on the `detect-patterns` subcommand path)."""
        from main import get_pattern_detection_caps
        with patch('builtins.print') as mock_print, \
             patch('sys.exit', side_effect=SystemExit) as mock_exit:
            with pytest.raises(SystemExit):
                get_pattern_detection_caps("/nonexistent/path/to/config.yaml")
            mock_exit.assert_called_once_with(1)
            printed = mock_print.call_args[0][0]
            assert printed.startswith("[ERROR]")


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
        """Test loading config from non-existent file raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            load_config("nonexistent.json")

        mock_config_class.assert_not_called()
        mock_config_class.from_file.assert_not_called()


class TestMainIntegration:
    """Integration tests for main function."""
    
    @patch('main.run_parse')
    def test_main_parse_command(self, mock_run_parse):
        """Test main function with parse command."""
        test_args = ['main.py', 'parse', 'input.mid', 'output.json']
        
        with patch('sys.argv', test_args):
            main()
            
            # Should have called run_parse with appropriate args
            mock_run_parse.assert_called_once()
            called_args = mock_run_parse.call_args[0][0]
            assert called_args.command == 'parse'
            assert called_args.input == 'input.mid'
            assert called_args.output == 'output.json'
    
    @patch('main.run_export')
    def test_main_export_command(self, mock_run_export):
        """Test main function with export command."""
        test_args = ['main.py', 'export', 'frames.json', 'output.asm', '--format', 'ca65']
        
        with patch('sys.argv', test_args):
            main()
            
            # Should have called run_export with appropriate args
            mock_run_export.assert_called_once()
            called_args = mock_run_export.call_args[0][0]
            assert called_args.command == 'export'
            assert called_args.input == 'frames.json'
            assert called_args.output == 'output.asm'
            assert called_args.format == 'ca65'
    
    def test_main_invalid_command(self):
        """Test main function with invalid MIDI filename (treated as default behavior)."""
        with patch('sys.argv', ['main.py', 'invalid.mid']):
            with patch('builtins.print') as mock_print:
                with pytest.raises(SystemExit):
                    main()
                # Should print error about missing MIDI file since 'invalid.mid' doesn't exist
                mock_print.assert_any_call("[ERROR] Input MIDI file not found: invalid.mid")
    
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
        """Regression (#120): invalid JSON must fail with a clear [ERROR]
        message and exit 1, not a bare JSONDecodeError traceback."""
        invalid_json_file = self.temp_dir / "invalid.json"
        invalid_json_file.write_text("invalid json content")

        args = Namespace(input=str(invalid_json_file), output="output.json")

        with pytest.raises(SystemExit) as exc:
            run_map(args)
        assert exc.value.code == 1
    
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


class TestFullPipelineBackupCleanup:
    """Regression tests for .nes.backup handling in run_full_pipeline (issue #29).

    The backup is created when an output ROM already exists and acts as a
    rollback safety net: it must be RESTORED and kept on failure, but REMOVED
    once the new ROM is final on success.
    """

    def _make_args(self, input_path, output_path):
        # --no-patterns and --skip-validation keep the pipeline path minimal.
        return Namespace(
            input=str(input_path),
            output=str(output_path),
            no_patterns=True,
            arranger=False,
            verbose=False,
            debug=False,
            skip_validation=True,
        )

    def _common_mocks(self, mock_parse, mock_assign, mock_emu_cls,
                       mock_exporter_cls, mock_packer_cls, mock_builder_cls):
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}}
        mock_assign.return_value = {}
        mock_emu = Mock()
        mock_emu.process_all_tracks.return_value = {"pulse1": {"0": {"note": 60, "volume": 15}}}
        mock_emu_cls.return_value = mock_emu
        mock_exporter_cls.return_value = Mock()
        mock_packer = Mock()
        mock_packer.generate_assembly.return_value = ""
        mock_packer.banks = []
        mock_packer_cls.return_value = mock_packer
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_cls.return_value = mock_builder

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('dpcm_sampler.dpcm_packer.DpcmPacker')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_backup_removed_on_success(self, mock_parse, mock_assign, mock_emu_cls,
                                       mock_exporter_cls, mock_packer_cls,
                                       mock_builder_cls, mock_compile):
        self._common_mocks(mock_parse, mock_assign, mock_emu_cls,
                           mock_exporter_cls, mock_packer_cls, mock_builder_cls)

        def fake_compile(project_path, out_rom, **kwargs):
            Path(out_rom).write_bytes(b"\x00" * 1024)
            return True
        mock_compile.side_effect = fake_compile

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            input_midi = tdp / "song.mid"
            input_midi.write_bytes(b"MThd")
            output_rom = tdp / "song.nes"
            output_rom.write_bytes(b"\x01" * 16)  # pre-existing ROM -> backup created
            backup_path = output_rom.with_suffix('.nes.backup')

            run_full_pipeline(self._make_args(input_midi, output_rom))

            assert output_rom.exists()
            assert not backup_path.exists(), ".nes.backup must be removed on success"

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_corrupt_dpcm_index_warns_prominently_in_success_banner(
            self, mock_parse, mock_assign, mock_emu_cls, mock_exporter_cls,
            mock_builder_cls, mock_compile):
        """Regression (#123): a corrupt dpcm_index.json must not be silently
        swallowed -- the ROM still builds (DPCM is optional) but the success
        banner must prominently warn it has no drums, not just an
        easy-to-miss warning line buried earlier in the output."""
        mock_parse.return_value = {"events": {"0": [{"frame": 0, "note": 60}]}}
        mock_assign.return_value = {}
        mock_emu = Mock()
        mock_emu.process_all_tracks.return_value = {"pulse1": {"0": {"note": 60, "volume": 15}}}
        mock_emu_cls.return_value = mock_emu
        mock_exporter_cls.return_value = Mock()
        mock_builder = Mock()
        mock_builder.prepare_project.return_value = True
        mock_builder_cls.return_value = mock_builder

        def fake_compile(project_path, out_rom, **kwargs):
            Path(out_rom).write_bytes(b"\x00" * 1024)
            return True
        mock_compile.side_effect = fake_compile

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "dpcm_index.json").write_text("not valid json")
            input_midi = tdp / "song.mid"
            input_midi.write_bytes(b"MThd")
            output_rom = tdp / "song.nes"

            os.chdir(tdp)
            try:
                with patch('builtins.print') as mock_print:
                    run_full_pipeline(self._make_args(input_midi, output_rom))
                messages = [str(c.args[0]) for c in mock_print.call_args_list if c.args]
            finally:
                os.chdir(cwd)

        success_idx = next(i for i, m in enumerate(messages) if "SUCCESS! ROM created" in m)
        warning_idx = next(i for i, m in enumerate(messages) if "NO DRUMS" in m)
        assert warning_idx > success_idx, "the NO DRUMS warning must come after the success banner"

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('dpcm_sampler.dpcm_packer.DpcmPacker')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_backup_kept_and_restored_on_compile_failure(self, mock_parse, mock_assign,
                                                         mock_emu_cls, mock_exporter_cls,
                                                         mock_packer_cls, mock_builder_cls,
                                                         mock_compile):
        self._common_mocks(mock_parse, mock_assign, mock_emu_cls,
                           mock_exporter_cls, mock_packer_cls, mock_builder_cls)
        mock_compile.return_value = False  # compilation fails -> rollback path

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            input_midi = tdp / "song.mid"
            input_midi.write_bytes(b"MThd")
            output_rom = tdp / "song.nes"
            original = b"\x02" * 16
            output_rom.write_bytes(original)  # pre-existing ROM -> backup created
            backup_path = output_rom.with_suffix('.nes.backup')

            with pytest.raises(SystemExit):
                run_full_pipeline(self._make_args(input_midi, output_rom))

            # On failure the backup is restored over the output and kept on disk.
            assert backup_path.exists(), ".nes.backup must be kept on failure"
            assert output_rom.read_bytes() == original, "original ROM must be restored"

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('dpcm_sampler.dpcm_packer.DpcmPacker')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_backup_restored_on_prepare_failure(self, mock_parse, mock_assign,
                                                mock_emu_cls, mock_exporter_cls,
                                                mock_packer_cls, mock_builder_cls,
                                                mock_compile):
        """Regression (#26): restore must fire when prepare_project returns False."""
        self._common_mocks(mock_parse, mock_assign, mock_emu_cls,
                           mock_exporter_cls, mock_packer_cls, mock_builder_cls)
        # prepare_project returns False; compile is never reached.
        mock_builder_cls.return_value.prepare_project.return_value = False

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            input_midi = tdp / "song.mid"
            input_midi.write_bytes(b"MThd")
            output_rom = tdp / "song.nes"
            original = b"\x03" * 16
            output_rom.write_bytes(original)
            backup_path = output_rom.with_suffix('.nes.backup')

            with pytest.raises(SystemExit):
                run_full_pipeline(self._make_args(input_midi, output_rom))

            assert backup_path.exists(), ".nes.backup must be kept on prepare failure"
            assert output_rom.read_bytes() == original, "original ROM must be restored on prepare failure"

    @patch('main.compile_rom')
    @patch('main.NESProjectBuilder')
    @patch('dpcm_sampler.dpcm_packer.DpcmPacker')
    @patch('main.CA65Exporter')
    @patch('main.NESEmulatorCore')
    @patch('main.assign_tracks_to_nes_channels')
    @patch('tracker.parser_fast.parse_midi_to_frames')
    def test_backup_restored_on_top_level_exception(self, mock_parse, mock_assign,
                                                    mock_emu_cls, mock_exporter_cls,
                                                    mock_packer_cls, mock_builder_cls,
                                                    mock_compile):
        """Regression (#26): restore must fire on an unhandled exception in the try block."""
        self._common_mocks(mock_parse, mock_assign, mock_emu_cls,
                           mock_exporter_cls, mock_packer_cls, mock_builder_cls)
        # Cause an unexpected exception inside the pipeline try block.
        mock_builder_cls.return_value.prepare_project.side_effect = RuntimeError("boom")

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            input_midi = tdp / "song.mid"
            input_midi.write_bytes(b"MThd")
            output_rom = tdp / "song.nes"
            original = b"\x04" * 16
            output_rom.write_bytes(original)
            backup_path = output_rom.with_suffix('.nes.backup')

            with pytest.raises(SystemExit):
                run_full_pipeline(self._make_args(input_midi, output_rom))

            assert backup_path.exists(), ".nes.backup must be kept on unexpected exception"
            assert output_rom.read_bytes() == original, "original ROM must be restored on unexpected exception"


class TestParserSelection:
    """Regression (#112/P-04): main.py must parse only via the fast parser.

    A dangling module-top `from tracker.parser import parse_midi_to_frames`
    (the older full parser) was a foot-gun: deleting a local `parse_fast`
    import would silently switch a path to the slower, behaviorally-different
    parser with no error. Every live path now imports parser_fast locally as
    `parse_fast`; pin that the old parser is not reachable through `main`."""

    def test_main_has_no_module_level_old_parser_binding(self):
        # Reference the module explicitly: the test namespace's bare `main`
        # is the imported main() function (from main import main), not the module.
        import sys
        main_module = sys.modules["main"]
        # The old parser is never imported at module scope, so the module must
        # not expose a top-level `parse_midi_to_frames` name at all.
        assert not hasattr(main_module, "parse_midi_to_frames"), \
            "main.py must not bind the old full parser at module scope (#112)"

    def test_main_source_does_not_import_old_parser(self):
        import inspect
        import sys
        src = inspect.getsource(sys.modules["main"])
        assert "from tracker.parser import" not in src, \
            "main.py must import only tracker.parser_fast (#112)"
        # The fast parser is the only sanctioned front-end and is imported
        # locally as parse_fast at every call site.
        assert "parser_fast import parse_midi_to_frames as parse_fast" in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
