"""
Test suite for critical audio playback fixes.

This test file covers bugs that were causing buzzing/crackling audio:
1. Triangle channel control byte generation (volume=0 must be 0x00, not 0x80)
2. Track splitting by pitch range for polyphonic MIDI
3. Note sustain and change detection
4. Proper silence handling
"""

import unittest
import tempfile
import os
from pathlib import Path

from exporter.exporter_ca65 import CA65Exporter
from tracker.track_mapper import split_polyphonic_track, assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore


class TestTriangleControlByte(unittest.TestCase):
    """Test triangle channel control byte generation - critical for silence."""

    def setUp(self):
        self.exporter = CA65Exporter()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_triangle_volume_zero_control_byte(self):
        """CRITICAL: Triangle volume=0 must generate control=0x00, not 0x80"""
        frames = {
            'triangle': {
                '0': {'note': 48, 'pitch': 1000, 'volume': 0},  # Silent frame
                '1': {'note': 48, 'pitch': 1000, 'volume': 15}, # Loud frame
                '2': {'note': 48, 'pitch': 1000, 'volume': 7},  # Mid volume
            }
        }

        output_path = os.path.join(self.temp_dir, "test_triangle.s")
        self.exporter.export_direct_frames(frames, output_path, standalone=True)

        with open(output_path, 'r') as f:
            content = f.read()

        # Find the triangle_control table
        control_start = content.find('triangle_control:')
        control_section = content[control_start:control_start + 200]

        # Extract the first line of control bytes
        lines = control_section.split('\n')
        control_line = None
        for line in lines:
            if '.byte' in line:
                control_line = line
                break

        self.assertIsNotNone(control_line, "Should have triangle_control data")

        # Parse control bytes
        control_bytes = [b.strip() for b in control_line.split('.byte')[1].split(',')]

        # Frame 0 (volume=0) must be $00 (SILENT)
        self.assertEqual(control_bytes[0], '$00',
                        "Volume=0 MUST generate control=$00 (silent), not $80")

        # Frame 1 (volume=15) must be non-zero with bit 7 set
        frame1_value = int(control_bytes[1].replace('$', ''), 16)
        self.assertNotEqual(frame1_value, 0,
                           "Volume=15 should generate non-zero control")
        self.assertEqual(frame1_value & 0x80, 0x80,
                        "Volume>0 should have bit 7 set (control flag)")

        # Frame 2 (volume=7) should be between 0x80 and 0xFF
        frame2_value = int(control_bytes[2].replace('$', ''), 16)
        self.assertGreaterEqual(frame2_value, 0x80)
        self.assertLessEqual(frame2_value, 0xFF)

    def test_triangle_control_formula(self):
        """Test the control byte formula for various volumes"""
        test_cases = [
            (0, 0x00),      # Silent - CRITICAL FIX
            (1, 0x87),      # 0x80 | (1 * 7) = 0x87
            (5, 0xA3),      # 0x80 | (5 * 7) = 0x80 | 35 = 0xA3
            (10, 0xC6),     # 0x80 | (10 * 7) = 0x80 | 70 = 0xC6
            (15, 0xE9),     # 0x80 | (15 * 7) = 0x80 | 105 = 0xE9
        ]

        for volume, expected_control in test_cases:
            frames = {
                'triangle': {
                    '0': {'note': 48, 'pitch': 1000, 'volume': volume}
                }
            }

            output_path = os.path.join(self.temp_dir, f"test_vol_{volume}.s")
            self.exporter.export_direct_frames(frames, output_path, standalone=True)

            with open(output_path, 'r') as f:
                content = f.read()

            # Extract control byte
            control_start = content.find('triangle_control:')
            control_section = content[control_start:control_start + 200]
            lines = control_section.split('\n')
            for line in lines:
                if '.byte' in line:
                    control_bytes = [b.strip() for b in line.split('.byte')[1].split(',')]
                    actual_control = int(control_bytes[0].replace('$', ''), 16)
                    self.assertEqual(actual_control, expected_control,
                                   f"Volume={volume} should generate control=${expected_control:02X}, got ${actual_control:02X}")
                    break


class TestNoteTableGeneration(unittest.TestCase):
    """Test that note tables are generated correctly for reliable comparison."""

    def setUp(self):
        self.exporter = CA65Exporter()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_note_table_exists_for_all_channels(self):
        """Ensure note tables are generated for pulse1, pulse2, triangle"""
        frames = {
            'pulse1': {'0': {'note': 60, 'pitch': 1000, 'control': 0x8F}},
            'pulse2': {'0': {'note': 64, 'pitch': 800, 'control': 0x8F}},
            'triangle': {'0': {'note': 48, 'pitch': 2000, 'volume': 15}}
        }

        output_path = os.path.join(self.temp_dir, "test_notes.s")
        self.exporter.export_direct_frames(frames, output_path, standalone=True)

        with open(output_path, 'r') as f:
            content = f.read()

        # Verify all three note tables exist
        self.assertIn('pulse1_note:', content, "pulse1_note table missing")
        self.assertIn('pulse2_note:', content, "pulse2_note table missing")
        self.assertIn('triangle_note:', content, "triangle_note table missing")

        # Verify note values are correct
        self.assertIn('$3C', content, "MIDI note 60 (0x3C) should be in note table")
        self.assertIn('$40', content, "MIDI note 64 (0x40) should be in note table")
        self.assertIn('$30', content, "MIDI note 48 (0x30) should be in note table")

    def test_note_comparison_in_playback(self):
        """Verify playback code compares note numbers, not timer values"""
        frames = {
            'pulse1': {'0': {'note': 60, 'pitch': 1000, 'control': 0x8F}}
        }

        output_path = os.path.join(self.temp_dir, "test_playback.s")
        self.exporter.export_direct_frames(frames, output_path, standalone=True)

        with open(output_path, 'r') as f:
            content = f.read()

        # Find play_pulse1 subroutine
        play_pulse1_start = content.find('.proc play_pulse1')
        play_pulse1_section = content[play_pulse1_start:play_pulse1_start + 2000]

        # Verify it loads from pulse1_note table
        self.assertIn('pulse1_note', play_pulse1_section,
                     "Playback should load from pulse1_note table")

        # Verify it compares with last_pulse1_note
        self.assertIn('last_pulse1_note', play_pulse1_section,
                     "Playback should compare with last_pulse1_note")

        # Verify sustain logic exists
        self.assertIn('@sustain', play_pulse1_section,
                     "Playback should have sustain label")

        # Verify silence logic exists
        self.assertIn('@silence', play_pulse1_section,
                     "Playback should have silence label")


class TestTrackSplitting(unittest.TestCase):
    """Test polyphonic track splitting by pitch range."""

    def test_split_by_pitch_range(self):
        """Test that notes are correctly split by pitch range"""
        events = [
            {'frame': 0, 'note': 72, 'volume': 15},  # High C (>= 60) -> Pulse1
            {'frame': 0, 'note': 55, 'volume': 15},  # Mid G (48-59) -> Pulse2
            {'frame': 0, 'note': 36, 'volume': 15},  # Low C (< 48)  -> Triangle
            {'frame': 10, 'note': 64, 'volume': 15}, # Mid E (>= 60) -> Pulse1
            {'frame': 10, 'note': 48, 'volume': 15}, # C (48-59)    -> Pulse2
        ]

        split = split_polyphonic_track(events)

        # Verify split results
        # Note 72 (>=60) and 64 (>=60) -> Pulse1
        # Note 55 (48-59) and 48 (48-59) -> Pulse2
        # Note 36 (<48) -> Triangle
        self.assertEqual(len(split['pulse1']), 2, "Should have 2 high notes (>=60)")
        self.assertEqual(len(split['pulse2']), 2, "Should have 2 mid notes (48-59)")
        self.assertEqual(len(split['triangle']), 1, "Should have 1 low note (<48)")

        # Verify notes went to correct channels
        self.assertIn(72, [e['note'] for e in split['pulse1']])
        self.assertIn(64, [e['note'] for e in split['pulse1']])
        self.assertIn(55, [e['note'] for e in split['pulse2']])
        self.assertIn(48, [e['note'] for e in split['pulse2']])
        self.assertEqual(split['triangle'][0]['note'], 36)

    def test_split_boundary_cases(self):
        """Test pitch range boundaries (48, 60)"""
        events = [
            {'frame': 0, 'note': 59, 'volume': 15},  # Just below 60 -> Pulse2
            {'frame': 0, 'note': 60, 'volume': 15},  # Exactly 60 -> Pulse1
            {'frame': 0, 'note': 47, 'volume': 15},  # Just below 48 -> Triangle
            {'frame': 0, 'note': 48, 'volume': 15},  # Exactly 48 -> Pulse2
        ]

        split = split_polyphonic_track(events)

        # Verify boundaries
        self.assertEqual(len(split['pulse1']), 1, "Note 60 should be Pulse1")
        self.assertEqual(len(split['pulse2']), 2, "Notes 48, 59 should be Pulse2")
        self.assertEqual(len(split['triangle']), 1, "Note 47 should be Triangle")

    def test_skip_note_off_events(self):
        """Verify note-off events (volume=0) are skipped during split"""
        events = [
            {'frame': 0, 'note': 60, 'volume': 15},  # Note on
            {'frame': 10, 'note': 60, 'volume': 0},  # Note off - should be skipped
            {'frame': 20, 'note': 64, 'volume': 15}, # Note on
        ]

        split = split_polyphonic_track(events)

        # Should only have 2 events total (both note-ons)
        total_events = len(split['pulse1']) + len(split['pulse2']) + len(split['triangle'])
        self.assertEqual(total_events, 2, "Note-off events should be skipped")


class TestSilenceHandling(unittest.TestCase):
    """Test that silence is handled correctly in playback code."""

    def setUp(self):
        self.exporter = CA65Exporter()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_pulse_silence_value(self):
        """Test that pulse channels use $30 for silence"""
        frames = {
            'pulse1': {'0': {'note': 60, 'pitch': 1000, 'control': 0x8F}}
        }

        output_path = os.path.join(self.temp_dir, "test_silence.s")
        self.exporter.export_direct_frames(frames, output_path, standalone=True)

        with open(output_path, 'r') as f:
            content = f.read()

        # Find silence handler in play_pulse1
        play_pulse1_start = content.find('.proc play_pulse1')
        play_pulse1_section = content[play_pulse1_start:play_pulse1_start + 2000]

        # Find @silence label
        silence_start = play_pulse1_section.find('@silence:')
        silence_section = play_pulse1_section[silence_start:silence_start + 200]

        # Verify it writes $30 to $4000
        self.assertIn('lda #$30', silence_section,
                     "Pulse silence should load $30")
        self.assertIn('sta $4000', silence_section,
                     "Pulse silence should write to $4000")

    def test_triangle_silence_value(self):
        """Test that triangle channel uses $00 for silence"""
        frames = {
            'triangle': {'0': {'note': 48, 'pitch': 2000, 'volume': 15}}
        }

        output_path = os.path.join(self.temp_dir, "test_tri_silence.s")
        self.exporter.export_direct_frames(frames, output_path, standalone=True)

        with open(output_path, 'r') as f:
            content = f.read()

        # Find silence handler in play_triangle
        play_triangle_start = content.find('.proc play_triangle')
        play_triangle_section = content[play_triangle_start:play_triangle_start + 2000]

        # Find @silence label
        silence_start = play_triangle_section.find('@silence:')
        silence_section = play_triangle_section[silence_start:silence_start + 200]

        # Verify it writes $00 to $4008
        self.assertIn('lda #$00', silence_section,
                     "Triangle silence should load $00")
        self.assertIn('sta $4008', silence_section,
                     "Triangle silence should write to $4008")


class TestFrameDataGeneration(unittest.TestCase):
    """Test frame data generation from emulator core."""

    def setUp(self):
        self.core = NESEmulatorCore()

    def test_pulse_control_byte_generated(self):
        """Verify pulse channels get control bytes"""
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100}
        ]

        frames = self.core.compile_channel_to_frames(events, 'pulse1', default_duty=2)

        # Check frame 0
        self.assertIn(0, frames, "Frame 0 should exist")
        self.assertIn('control', frames[0], "Frame should have control byte")
        self.assertIn('pitch', frames[0], "Frame should have pitch")
        self.assertNotEqual(frames[0]['control'], 0,
                          "Control byte should be non-zero for velocity>0")

    def test_triangle_volume_generated(self):
        """Verify triangle channel gets volume field"""
        events = [
            {'frame': 0, 'note': 48, 'velocity': 80}
        ]

        frames = self.core.compile_channel_to_frames(events, 'triangle')

        # Check frame 0
        self.assertIn(0, frames, "Frame 0 should exist")
        self.assertIn('volume', frames[0], "Triangle frame should have volume")
        self.assertIn('pitch', frames[0], "Frame should have pitch")

        # Verify volume is calculated correctly (velocity // 8)
        expected_volume = min(15, 80 // 8)
        self.assertEqual(frames[0]['volume'], expected_volume)

    def test_note_sustain_duration(self):
        """Test that notes sustain for correct duration"""
        events = [
            {'frame': 0, 'note': 60, 'velocity': 100},
            {'frame': 10, 'note': 64, 'velocity': 100}  # New note at frame 10
        ]

        frames = self.core.compile_channel_to_frames(events, 'pulse1',
                                                     default_duty=2, sustain_frames=8)

        # First note should sustain for sustain_frames (8) or until next note (frame 10)
        # Since sustain_frames=8, it will sustain from frame 0-7 (8 frames total)
        for f in range(0, 8):
            self.assertIn(f, frames, f"Frame {f} should have data (sustain)")
            self.assertEqual(frames[f]['note'], 60,
                           f"Frame {f} should have note 60")

        # Frames 8-9 should be silent (gap before next note)
        self.assertNotIn(8, frames, "Frame 8 should be silent (beyond sustain)")
        self.assertNotIn(9, frames, "Frame 9 should be silent (beyond sustain)")

        # Second note should exist at frame 10+ (and sustain for 8 frames)
        self.assertIn(10, frames, "Frame 10 should have second note")
        self.assertEqual(frames[10]['note'], 64)

        # Verify second note sustains
        for f in range(10, 18):
            self.assertIn(f, frames, f"Frame {f} should have note 64")
            self.assertEqual(frames[f]['note'], 64)


class TestAssemblyCodeGeneration(unittest.TestCase):
    """Test that generated assembly code has correct structure."""

    def setUp(self):
        self.exporter = CA65Exporter()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for file in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file))
        os.rmdir(self.temp_dir)

    def test_bss_segment_exists(self):
        """Verify BSS segment is generated for note tracking"""
        frames = {
            'pulse1': {'0': {'note': 60, 'pitch': 1000, 'control': 0x8F}}
        }

        output_path = os.path.join(self.temp_dir, "test_bss.s")
        self.exporter.export_direct_frames(frames, output_path, standalone=True)

        with open(output_path, 'r') as f:
            content = f.read()

        # Verify BSS segment exists
        self.assertIn('.segment "BSS"', content, "BSS segment should exist")
        self.assertIn('last_pulse1_note: .res 1', content,
                     "last_pulse1_note variable should be in BSS")
        self.assertIn('last_pulse2_note: .res 1', content,
                     "last_pulse2_note variable should be in BSS")
        self.assertIn('last_triangle_note: .res 1', content,
                     "last_triangle_note variable should be in BSS")

    def test_sustain_branch_exists(self):
        """Verify all channels have sustain branches"""
        frames = {
            'pulse1': {'0': {'note': 60, 'pitch': 1000, 'control': 0x8F}},
            'pulse2': {'0': {'note': 64, 'pitch': 800, 'control': 0x8F}},
            'triangle': {'0': {'note': 48, 'pitch': 2000, 'volume': 15}}
        }

        output_path = os.path.join(self.temp_dir, "test_sustain.s")
        self.exporter.export_direct_frames(frames, output_path, standalone=True)

        with open(output_path, 'r') as f:
            content = f.read()

        # Verify each channel has sustain logic
        for channel in ['pulse1', 'pulse2', 'triangle']:
            proc_start = content.find(f'.proc play_{channel}')
            proc_section = content[proc_start:proc_start + 2000]

            self.assertIn('beq @sustain', proc_section,
                         f"{channel} should have sustain branch")
            self.assertIn('@sustain:', proc_section,
                         f"{channel} should have @sustain label")


if __name__ == '__main__':
    unittest.main()
