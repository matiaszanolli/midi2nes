"""Tests for exporter/base_exporter.py's atomic_write_text (#385/SAFE-2026-07-19-3)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from exporter.base_exporter import atomic_write_text


class TestAtomicWriteText(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_writes_full_content(self):
        output_path = self.temp_dir / "music.asm"
        atomic_write_text(output_path, "line1\nline2\nline3")
        self.assertEqual(output_path.read_text(), "line1\nline2\nline3")

    def test_no_leftover_temp_file_on_success(self):
        output_path = self.temp_dir / "music.asm"
        atomic_write_text(output_path, "content")
        remaining = list(self.temp_dir.iterdir())
        self.assertEqual(remaining, [output_path])

    def test_failed_write_leaves_prior_good_file_intact(self):
        """Regression (#385): a failed write must never truncate or partially
        overwrite a prior good file at output_path -- the old exporter code
        wrote straight to output_path via `open(output_path, 'w')`, so a
        failure mid-write (or right after truncation) left a corrupt file."""
        output_path = self.temp_dir / "music.asm"
        output_path.write_text("original good content")

        with patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                atomic_write_text(output_path, "new content that never lands")

        self.assertEqual(output_path.read_text(), "original good content")

    def test_failed_write_removes_its_own_temp_file(self):
        output_path = self.temp_dir / "music.asm"

        with patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                atomic_write_text(output_path, "content")

        leftover_temp_files = [
            p for p in self.temp_dir.iterdir() if p.name != output_path.name
        ]
        self.assertEqual(leftover_temp_files, [])
        self.assertFalse(output_path.exists())

    def test_accepts_str_and_path_output(self):
        output_path = self.temp_dir / "music.asm"
        atomic_write_text(str(output_path), "via str path")
        self.assertEqual(output_path.read_text(), "via str path")


if __name__ == "__main__":
    unittest.main()
