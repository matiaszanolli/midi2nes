"""Tests for debug/rom_tester.py's generate_test_summary header check."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from debug.rom_tester import generate_test_summary


class TestHeaderValidation:
    def test_valid_ines_header_reports_ok(self, tmp_path):
        rom = tmp_path / "test.nes"
        rom.write_bytes(b'NES\x1a' + b'\x00' * 32780)
        summary = generate_test_summary(str(rom))
        assert "Header: ✅" in summary

    def test_missing_file_reports_header_not_ok(self, tmp_path):
        rom = tmp_path / "missing.nes"
        summary = generate_test_summary(str(rom))
        assert "Header: ❌" in summary

    def test_bad_header_reports_not_ok(self, tmp_path):
        rom = tmp_path / "bad.nes"
        rom.write_bytes(b'\x00\x00\x00\x00')
        summary = generate_test_summary(str(rom))
        assert "Header: ❌" in summary

    def test_unreadable_file_degrades_gracefully(self, tmp_path):
        """OSError (e.g. a permission failure) on the header read is caught
        and degrades to header_ok=False rather than crashing."""
        rom = tmp_path / "unreadable.nes"
        rom.write_bytes(b'NES\x1a')
        with patch.object(Path, 'read_bytes', side_effect=OSError("denied")):
            summary = generate_test_summary(str(rom))
        assert "Header: ❌" in summary

    def test_non_os_error_is_not_swallowed(self, tmp_path):
        """Regression (#223/SAFE-12): the header check used a bare `except:`,
        which would also swallow KeyboardInterrupt/SystemExit and any
        unrelated bug. Narrowed to OSError -- any other exception must still
        propagate."""
        rom = tmp_path / "test.nes"
        rom.write_bytes(b'NES\x1a')
        with patch.object(Path, 'read_bytes', side_effect=ValueError("unexpected")):
            try:
                generate_test_summary(str(rom))
                assert False, "expected ValueError to propagate"
            except ValueError:
                pass
