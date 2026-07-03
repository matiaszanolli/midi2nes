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


class TestNoiseDpcmReachAPU(unittest.TestCase):
    """Regression (NH-01 / #9): noise and DPCM frames must carry the fields the
    exporters turn into APU register writes, and both exporter paths must emit
    them. Previously percussion/samples were silent."""

    def setUp(self):
        self.core = NESEmulatorCore()
        self.exporter = CA65Exporter()

    def test_process_all_tracks_noise_frame_shape(self):
        mapped = {'noise': [{'frame': 0, 'note': 38, 'velocity': 100}]}
        frames = self.core.process_all_tracks(mapped)
        fd = frames['noise'][0]
        # note = 4-bit period index (floored at 1), volume scaled, mode in control.
        self.assertGreaterEqual(fd['note'], 1)
        self.assertLessEqual(fd['note'], 15)
        self.assertGreater(fd['volume'], 0)
        self.assertIn('control', fd)

    def test_process_all_tracks_dpcm_frame_shape(self):
        mapped = {'dpcm': [{'frame': 0, 'note': 36, 'velocity': 100, 'sample_id': 3}]}
        frames = self.core.process_all_tracks(mapped)
        fd = frames['dpcm'][0]
        # note = sample_id + 1 so the engine recovers sample_id as note-1.
        self.assertEqual(fd['note'], 4)
        self.assertGreater(fd['volume'], 0)

    def test_bytecode_path_emits_noise_and_dpcm_sequences(self):
        mapped = {
            'noise': [{'frame': 0, 'note': 38, 'velocity': 100}],
            'dpcm': [{'frame': 0, 'note': 36, 'velocity': 100, 'sample_id': 1}],
        }
        frames = self.core.process_all_tracks(mapped)
        patterns = {'p0': {'events': [{'note': 10, 'volume': 8}], 'positions': [0]}}
        refs = {'0': ('p0', 0)}
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, refs, out, standalone=False)
            content = Path(out).read_text()
        finally:
            if os.path.exists(out):
                os.remove(out)
        # Both sequences must carry real note data, not collapse to $FF/silence.
        noise_block = content.split('noise_sequence:')[1].split('_sequence:')[0]
        dpcm_block = content.split('dpcm_sequence:')[1].split('\n\n')[0]
        self.assertIn('Note 10', noise_block)   # period index 10
        self.assertIn('Note 2', dpcm_block)     # sample_id 1 -> note 2

    def test_direct_path_emits_noise_register_writes(self):
        mapped = {'noise': [{'frame': 0, 'note': 38, 'velocity': 100}]}
        frames = self.core.process_all_tracks(mapped)
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_direct_frames(frames, out, standalone=True)
            content = Path(out).read_text()
        finally:
            if os.path.exists(out):
                os.remove(out)
        self.assertIn('play_noise', content)
        self.assertIn('sta $400C', content)   # noise volume/envelope
        self.assertIn('sta $400E', content)   # noise period/mode
        self.assertIn('noise_note:', content)

    def test_noise_hit_decays_over_multiple_frames(self):
        # Regression (#162/NH-19): both playback paths force the length-counter
        # halt bit and constant-volume flag, so there is no hardware decay for a
        # single-frame hit to ride on. process_all_tracks must bake a software
        # volume ramp across several frames instead.
        mapped = {'noise': [{'frame': 0, 'note': 38, 'velocity': 127}]}
        frames = self.core.process_all_tracks(mapped)
        noise = frames['noise']
        self.assertGreater(len(noise), 1)
        ordered_frames = sorted(noise)
        volumes = [noise[f]['volume'] for f in ordered_frames]
        self.assertEqual(volumes, sorted(volumes, reverse=True))
        self.assertGreater(volumes[0], volumes[-1])
        # The period (drum pitch) must stay constant across the decay -- only
        # volume ramps down.
        periods = {noise[f]['note'] for f in ordered_frames}
        self.assertEqual(len(periods), 1)

    def test_noise_retrigger_cuts_previous_decay_short(self):
        # A second hit must cut the first hit's decay short, not blend with it.
        mapped = {'noise': [{'frame': 0, 'note': 38, 'velocity': 127},
                             {'frame': 2, 'note': 40, 'velocity': 100}]}
        frames = self.core.process_all_tracks(mapped)
        noise = frames['noise']
        self.assertEqual(noise[0]['note'], noise[1]['note'])
        self.assertNotEqual(noise[1]['note'], noise[2]['note'])

    def test_direct_path_play_noise_rewrites_ctrl_unconditionally(self):
        # Regression (#162/NH-19): play_noise used to skip $400C/$400E/$400F
        # whenever the period was unchanged from the previous frame, assuming
        # a hardware decay that can't happen (halted length counter, bypassed
        # envelope). It must rewrite the control byte every active frame so a
        # software volume ramp is actually heard.
        mapped = {'noise': [{'frame': 0, 'note': 38, 'velocity': 127}]}
        frames = self.core.process_all_tracks(mapped)
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_direct_frames(frames, out, standalone=True)
            content = Path(out).read_text()
        finally:
            if os.path.exists(out):
                os.remove(out)
        play_noise = content.split('.proc play_noise', 1)[1].split('.endproc', 1)[0]
        self.assertNotIn('last_noise_note', play_noise)
        self.assertNotIn('last_noise_note', content)
        self.assertIn('sta $400C', play_noise)
        self.assertIn('sta $400F', play_noise)

    def test_direct_path_emits_dpcm_trigger(self):
        mapped = {'dpcm': [{'frame': 0, 'note': 36, 'velocity': 100, 'sample_id': 1}]}
        frames = self.core.process_all_tracks(mapped)
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_direct_frames(frames, out, standalone=True)
            content = Path(out).read_text()
        finally:
            if os.path.exists(out):
                os.remove(out)
        self.assertIn('play_dpcm', content)
        self.assertIn('sta $4010', content)   # DMC rate
        self.assertIn('sta $4013', content)   # DMC length
        self.assertIn('dpcm_note:', content)

    def test_high_sample_id_not_clamped_to_note_95(self):
        # Regression (D-04 / #67): a DPCM sample_id is not a MIDI note, so it must
        # not borrow the 0-95 tone-note ceiling. sample_id 200 used to clamp to
        # note 95 (sample_id 94) — a wrong drum. The bound is the single-byte
        # frame note: note = sample_id + 1.
        mapped = {'dpcm': [{'frame': 0, 'note': 36, 'velocity': 100, 'sample_id': 200}]}
        frames = self.core.process_all_tracks(mapped)
        self.assertEqual(frames['dpcm'][0]['note'], 201)   # not 95
        # The byte format still caps at 255 so the emitted operand stays one byte.
        big = {'dpcm': [{'frame': 0, 'note': 36, 'velocity': 100, 'sample_id': 9999}]}
        self.assertEqual(self.core.process_all_tracks(big)['dpcm'][0]['note'], 255)

    def test_bytecode_dpcm_high_note_survives_tone_note_still_clamped(self):
        # Regression (D-04 / #67): the bytecode serializer's note clamp must be
        # channel-aware — DPCM keeps its high sample-id note (bounded only by the
        # byte format), while a tone channel still clamps to the 0-95 note range.
        frames = {
            'dpcm':   {'0': {'note': 201, 'volume': 15}},   # sample_id 200
            'pulse1': {'0': {'note': 100, 'volume': 8}},    # tone note > 95
        }
        patterns = {'p0': {'events': [{'note': 10, 'volume': 8}], 'positions': [0]}}
        refs = {'0': ('p0', 0)}
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, refs, out, standalone=False)
            content = Path(out).read_text()
        finally:
            if os.path.exists(out):
                os.remove(out)
        dpcm_block = content.split('dpcm_sequence:')[1].split('\n\n')[0]
        self.assertIn('Note 201', dpcm_block)   # not collapsed to 95
        self.assertIn('$C9', dpcm_block)         # 201 emitted as a single byte
        pulse_block = content.split('pulse1_sequence:')[1].split('_sequence:')[0]
        self.assertIn('Note 95', pulse_block)    # tone note still clamped

    def test_direct_play_dpcm_rest_guard_re_tests_note(self):
        # Regression (D-03 / #66): the standalone play_dpcm rest guard tested the
        # stale Z flag from `cmp last_dpcm_note` (STA does not affect Z), so a rest
        # (note 0) that differs from the last note fell through to `sbc #1` -> y=$FF
        # -> dpcm_*_table[$FF] over-read. The guard must re-set Z from the note.
        mapped = {'dpcm': [{'frame': 0, 'note': 36, 'velocity': 100, 'sample_id': 1}]}
        frames = self.core.process_all_tracks(mapped)
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_direct_frames(frames, out, standalone=True)
            content = Path(out).read_text()
        finally:
            if os.path.exists(out):
                os.remove(out)
        proc = content.split('.proc play_dpcm')[1].split('.endproc')[0]
        # Between storing last_dpcm_note and deriving sample_id (sbc #1), the note
        # value must be re-tested so the rest (note 0) skips the trigger.
        guard = proc[proc.index('sta last_dpcm_note'):proc.index('sbc #1')]
        self.assertIn('cmp #0', guard)
        self.assertIn('beq @done', guard)


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


class TestTrianglePitchOctave(unittest.TestCase):
    """Regression (NH-02 / #12): triangle uses the /32 timer table so it plays
    the intended note instead of an octave low."""

    def setUp(self):
        from nes.pitch_table import PitchProcessor
        self.pitch = PitchProcessor()
        self.exporter = CA65Exporter()

    def test_triangle_a4_timer_is_126_not_253(self):
        # Pulse A4 timer is 253 (/16); triangle A4 must be 126 (/32).
        self.assertEqual(self.pitch.get_channel_pitch(69, 'triangle'), 126)
        self.assertEqual(self.pitch.get_channel_pitch(69, 'pulse1'), 253)

    def test_triangle_is_octave_above_pulse_period(self):
        # For every in-range note the triangle period is ~half the pulse period.
        # Both tables independently round to the nearest integer CPU-cycle
        # count, so the exact 2:1 ratio drifts more at short periods (high
        # notes) -- delta=0.08 comfortably covers that integer-quantization
        # error across the whole range without masking a real off-by-large
        # regression.
        for note in range(36, 96):
            tri = self.pitch.get_channel_pitch(note, 'triangle')
            pul = self.pitch.get_channel_pitch(note, 'pulse1')
            self.assertAlmostEqual(pul / tri, 2.0, delta=0.08,
                                   msg=f"note {note}: pulse {pul} vs triangle {tri}")

    def test_exporter_base_timer_channel_aware(self):
        # Bytecode base timer must match the triangle frame pitch so the offset
        # is 0 (otherwise it clamps to +/-127 and corrupts the bass).
        for note in range(36, 96):
            base = self.exporter.midi_note_to_timer_value(note, 'triangle')
            frame_pitch = self.pitch.get_channel_pitch(note, 'triangle')
            offset = max(-128, min(127, frame_pitch - base))
            self.assertEqual(offset, 0, f"triangle note {note}: base {base} vs {frame_pitch}")

    def test_bytecode_emits_triangle_period_table(self):
        from nes.pitch_table import PitchProcessor
        pp = PitchProcessor()
        frames = {'triangle': {str(f): {'note': 60, 'volume': 8,
                                        'pitch': pp.get_channel_pitch(60, 'triangle')}
                               for f in range(8)}}
        patterns = {'p0': {'events': [{'note': 60, 'volume': 8}], 'positions': [0]}}
        references = {'0': ('p0', 0)}
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, references,
                                                      out, standalone=False)
            content = Path(out).read_text()
        finally:
            if os.path.exists(out):
                os.remove(out)
        self.assertIn('MMC3 Macro Bytecode', content)
        self.assertIn('triangle_period_low:', content)
        self.assertIn('.export triangle_period_low, triangle_period_high', content)


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

    def test_note_off_events_routed_by_pitch(self):
        """Regression (#160): note-off events must be preserved (routed by their
        own pitch, same as note-ons) rather than dropped, so
        compile_channel_to_frames can pair them with their note-on and recover
        the note's real duration instead of forcing a fixed sustain."""
        events = [
            {'frame': 0, 'note': 60, 'volume': 15},  # Note on -> pulse1
            {'frame': 10, 'note': 60, 'volume': 0},  # Note off -> pulse1
            {'frame': 20, 'note': 64, 'volume': 15}, # Note on -> pulse1
        ]

        split = split_polyphonic_track(events)

        total_events = len(split['pulse1']) + len(split['pulse2']) + len(split['triangle'])
        self.assertEqual(total_events, 3, "Note-off events must be preserved for duration pairing")
        self.assertEqual(len(split['pulse1']), 3)


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

        # Verify volume is calculated correctly using logarithmic curve
        import math
        expected_volume = max(1, int(15 * math.pow(80 / 127.0, 1.5)))
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


class TestSameFrameNoteCollapse(unittest.TestCase):
    """Regression (TEMPO-04 / #96): two note-ons that quantize to the same 60Hz
    frame on a monophonic channel used to collapse — the later write silently
    overwrote (and dropped) the earlier note. The collapse must now be a
    deliberate, visible choice (loudest wins) rather than a silent last-write."""

    def setUp(self):
        self.core = NESEmulatorCore()

    def _notes(self, frames):
        return {f: d['note'] for f, d in frames.items()}

    def test_louder_same_frame_note_wins_not_last(self):
        # note 60 is louder than the later note 67, so it must survive; the old
        # last-write-wins behaviour kept note 67 and dropped the louder note 60.
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            frames = self.core.compile_channel_to_frames(
                [{'frame': 10, 'note': 60, 'volume': 120},
                 {'frame': 10, 'note': 67, 'volume': 50}], 'pulse')
        self.assertEqual(set(self._notes(frames).values()), {60})
        # The drop is surfaced, not silent.
        self.assertIn('dropped', buf.getvalue())

    def test_distinct_frame_notes_unaffected(self):
        # The collapse must not disturb notes on different frames: note 60 plays
        # until note 67 starts at frame 12 (the normal truncation).
        frames = self.core.compile_channel_to_frames(
            [{'frame': 10, 'note': 60, 'volume': 100},
             {'frame': 12, 'note': 67, 'volume': 100}], 'pulse')
        self.assertEqual(self._notes(frames)[10], 60)
        self.assertEqual(self._notes(frames)[11], 60)
        self.assertEqual(self._notes(frames)[12], 67)

    def test_collapse_applies_to_noise_channel(self):
        # CHANNEL: the same collapse covers the noise branch of process_all_tracks,
        # not just the tonal channels — two same-frame hits keep only one hit's
        # decay, not two hits blended together (#162/NH-19 made a single hit span
        # several frames, so this no longer collapses to a single frame key).
        out = self.core.process_all_tracks(
            {'noise': [{'frame': 5, 'note': 38, 'velocity': 40},
                       {'frame': 5, 'note': 40, 'velocity': 90}]})
        self.assertEqual(min(out['noise'].keys()), 5)
        periods = {d['note'] for d in out['noise'].values()}
        self.assertEqual(len(periods), 1)  # one surviving hit (the louder one)


if __name__ == '__main__':
    unittest.main()
