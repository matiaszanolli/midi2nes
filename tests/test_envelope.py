# tests/test_envelope.py
import unittest
import sys
import os

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from nes.envelope_processor import EnvelopeProcessor


class TestNoDuplicateEmulatorCore(unittest.TestCase):
    """Regression (#38/NH-10): nes/envelope_processor.py used to carry a second,
    dead copy of NESEmulatorCore whose vibrato path added pitch_mod after
    clamping with no re-clamp (a latent 11-bit overflow trap if it were ever
    wired in). The duplicate is removed; nes.emulator_core.NESEmulatorCore
    stays the sole implementation."""

    def test_envelope_processor_does_not_export_emulator_core(self):
        import nes.envelope_processor as envelope_processor_module
        self.assertFalse(hasattr(envelope_processor_module, "NESEmulatorCore"))

    def test_live_emulator_core_is_the_only_one(self):
        from nes.emulator_core import NESEmulatorCore
        self.assertIsNotNone(NESEmulatorCore)


class TestEnvelopeProcessor(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.processor = EnvelopeProcessor()

    def test_default_envelope_definitions(self):
        """Test that default envelope definitions are properly initialized"""
        expected_envelopes = {
            "default", "piano", "pad", "pluck", "percussion"
        }
        self.assertEqual(set(self.processor.envelope_definitions.keys()), 
                        expected_envelopes)

    def test_default_envelope_behavior(self):
        """Test default envelope behavior (constant volume)"""
        envelope_type = "default"
        # Test at different frame offsets
        self.assertEqual(self.processor.get_envelope_value(envelope_type, 0, 10), 15)
        self.assertEqual(self.processor.get_envelope_value(envelope_type, 5, 10), 15)
        self.assertEqual(self.processor.get_envelope_value(envelope_type, 9, 10), 15)

    def test_piano_envelope(self):
        """Test piano envelope characteristics"""
        envelope_type = "piano"
        note_duration = 30  # frames
        
        # Test attack phase (should reach max volume quickly)
        attack_value = self.processor.get_envelope_value(envelope_type, 0, note_duration)
        self.assertLess(attack_value, 15)  # Should start below max
        
        # Test decay and sustain
        sustain_value = self.processor.get_envelope_value(envelope_type, 5, note_duration)
        # Note: This test gets the base envelope value (without velocity scaling)
        # The piano envelope sustain level is 10 when called directly
        self.assertEqual(sustain_value, 10)  # Piano sustain level
        
        # Test release
        release_value = self.processor.get_envelope_value(envelope_type, 29, note_duration)
        self.assertLess(release_value, sustain_value)  # Should decrease during release

    def test_percussion_envelope(self):
        """Test percussion envelope (immediate attack, quick decay)"""
        envelope_type = "percussion"
        note_duration = 10
        
        # Test immediate attack - should start at maximum volume
        start_value = self.processor.get_envelope_value(envelope_type, 0, note_duration)
        self.assertEqual(start_value, 15)  # Should start at max volume (15)
        
        # Test decay phase - should gradually decrease
        next_value = self.processor.get_envelope_value(envelope_type, 1, note_duration)
        self.assertLess(next_value, 15)  # Should be less than initial value
        self.assertGreater(next_value, 0)  # But still greater than 0
        
        # Test end of decay
        end_value = self.processor.get_envelope_value(envelope_type, note_duration - 1, note_duration)
        self.assertEqual(end_value, 0)  # Should reach zero by the end


    def test_control_byte_generation(self):
        """Test envelope control byte generation"""
        envelope_type = "default"
        frame_offset = 0
        note_duration = 10
        
        # Test with different duty cycles (without base velocity)
        for duty in range(4):
            control_byte = self.processor.get_envelope_control_byte(
                envelope_type, frame_offset, note_duration, duty_cycle=duty
            )
            
            # Check duty cycle bits (bits 6-7)
            expected_duty_bits = (duty & 0x03) << 6
            self.assertEqual(control_byte & 0xC0, expected_duty_bits)
            
            # Check envelope bits (bit 4 should be 0x10 for constant volume)
            self.assertEqual(control_byte & 0x10, 0x10)
            
            # Check volume bits (bits 0-3)
            volume = control_byte & 0x0F
            self.assertEqual(volume, 15)  # Default envelope has full volume without base_velocity
        
        # Test with base velocity
        base_velocity = 100  # MIDI velocity
        control_byte = self.processor.get_envelope_control_byte(
            envelope_type, frame_offset, note_duration, duty_cycle=2, base_velocity=base_velocity
        )
        
        # Check that MIDI velocity is properly scaled using logarithmic curve
        volume = control_byte & 0x0F
        import math
        expected_volume = max(1, int(15 * math.pow(base_velocity / 127.0, 1.5)))
        self.assertEqual(volume, expected_volume)

    def test_invalid_envelope_type(self):
        """Test handling of invalid envelope types"""
        # Should fall back to default envelope
        value = self.processor.get_envelope_value("nonexistent", 0, 10)
        self.assertEqual(value, 15)  # Default envelope has constant volume of 15

    def test_envelope_phases(self):
        """Test all envelope phases for pad envelope"""
        envelope_type = "pad"
        note_duration = 30
        
        # Test attack phase (0-4 frames)
        attack_start = self.processor.get_envelope_value(envelope_type, 0, note_duration)
        attack_mid = self.processor.get_envelope_value(envelope_type, 2, note_duration)
        attack_end = self.processor.get_envelope_value(envelope_type, 4, note_duration)
        self.assertLess(attack_start, attack_mid)
        self.assertLess(attack_mid, attack_end)
        
        # Test decay phase (5-14 frames)
        decay_start = self.processor.get_envelope_value(envelope_type, 5, note_duration)
        decay_end = self.processor.get_envelope_value(envelope_type, 14, note_duration)
        self.assertGreater(decay_start, decay_end)
        
        # Test sustain phase (15-24 frames)
        sustain_start = self.processor.get_envelope_value(envelope_type, 15, note_duration)
        sustain_end = self.processor.get_envelope_value(envelope_type, 24, note_duration)
        self.assertEqual(sustain_start, sustain_end)
        self.assertEqual(sustain_start, 8)  # Pad sustain level
        
        # Test release phase (25-29 frames)
        release_start = self.processor.get_envelope_value(envelope_type, 25, note_duration)
        release_end = self.processor.get_envelope_value(envelope_type, 29, note_duration)
        self.assertGreater(release_start, release_end)
        self.assertGreater(release_end, 0)  # Should not necessarily end at zero
        
    def test_tremolo_effects(self):
        """Test tremolo effect application in envelopes"""
        envelope_type = "default"
        note_duration = 20
        
        # Test without tremolo
        base_volume = self.processor.get_envelope_value(envelope_type, 10, note_duration)
        
        # Test with tremolo effect
        tremolo_effects = {
            "tremolo": {
                "speed": 4.0,
                "depth": 3
            }
        }
        
        tremolo_volumes = []
        # Use frame offsets that will show tremolo variation better
        # With speed 4.0, use offsets that don't land on sine wave zeros
        for frame_offset in [0, 1, 2, 3, 4, 5, 6, 7]:
            volume = self.processor.get_envelope_value(
                envelope_type, frame_offset, note_duration, tremolo_effects
            )
            tremolo_volumes.append(volume)
        
        # Check that tremolo creates variation in volume
        self.assertGreater(max(tremolo_volumes), min(tremolo_volumes))
        
        # Check that volumes stay within valid range
        for volume in tremolo_volumes:
            self.assertGreaterEqual(volume, 0)
            self.assertLessEqual(volume, 15)
            
    def test_duty_cycle_sequences(self):
        """Test duty cycle sequence processing"""
        # Test default duty cycle (no sequence)
        default_duty = self.processor.get_duty_cycle(0)
        self.assertEqual(default_duty, 2)
        
        default_duty_with_none = self.processor.get_duty_cycle(5, None)
        self.assertEqual(default_duty_with_none, 2)
        
        # Test invalid sequence name
        invalid_duty = self.processor.get_duty_cycle(0, "nonexistent")
        self.assertEqual(invalid_duty, 2)
        
        # Test Follin lead sequence
        follin_duties = []
        for frame in range(16):  # Test one full cycle (4 entries * 4 frames each)
            duty = self.processor.get_duty_cycle(frame, "follin_lead")
            follin_duties.append(duty)
            
        # Check that we get the expected pattern
        expected_pattern = [2, 2, 2, 2, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]
        self.assertEqual(follin_duties, expected_pattern)
        
        # Test Follin sweep sequence  
        sweep_duties = []
        for frame in range(8):  # 4 entries * 2 frames each
            duty = self.processor.get_duty_cycle(frame, "follin_sweep")
            sweep_duties.append(duty)
            
        expected_sweep = [0, 0, 1, 1, 2, 2, 3, 3]
        self.assertEqual(sweep_duties, expected_sweep)
        
        # Test sequence cycling (should repeat after full cycle)
        duty_start = self.processor.get_duty_cycle(0, "follin_lead")
        duty_cycle = self.processor.get_duty_cycle(16, "follin_lead")  # One full cycle later
        self.assertEqual(duty_start, duty_cycle)
        
    def test_envelope_control_byte_with_duty_sequence(self):
        """Test control byte generation with dynamic duty sequences"""
        envelope_type = "default"
        frame_offset = 0
        note_duration = 10
        
        # Test with duty sequence effect
        effects = {
            "duty_sequence": "follin_lead"
        }
        
        control_byte = self.processor.get_envelope_control_byte(
            envelope_type, frame_offset, note_duration, duty_cycle=1, effects=effects
        )
        
        # Extract duty from control byte (bits 6-7)
        duty_from_byte = (control_byte & 0xC0) >> 6
        
        # Should use duty from sequence (2 for follin_lead at frame 0), not passed duty_cycle
        expected_duty = 2  # First duty in follin_lead sequence
        self.assertEqual(duty_from_byte, expected_duty)
        
        # Test at different frame offset to get different duty
        control_byte_frame4 = self.processor.get_envelope_control_byte(
            envelope_type, 4, note_duration, duty_cycle=1, effects=effects
        )
        
        duty_from_byte_frame4 = (control_byte_frame4 & 0xC0) >> 6
        expected_duty_frame4 = 1  # Fifth frame (index 4) in follin_lead sequence
        self.assertEqual(duty_from_byte_frame4, expected_duty_frame4)
        
    def test_volume_envelope_application(self):
        """Test application of volume envelope patterns to frames"""
        frames = {}
        pattern = [15, 12, 9, 6, 3, 0]
        channel = "pulse1"
        start_frame = 10
        
        self.processor.apply_volume_envelope(frames, pattern, channel, start_frame)
        
        # Check that frames were created and populated correctly
        for i, expected_volume in enumerate(pattern):
            frame_key = str(start_frame + i)
            self.assertIn(frame_key, frames)
            self.assertIn(channel, frames[frame_key])
            self.assertEqual(frames[frame_key][channel]['volume'], expected_volume)
            
        # Test applying to existing frames structure
        existing_frames = {
            "10": {"pulse2": {"note": 60}},
            "12": {"pulse1": {"pitch": 1000}}
        }
        
        self.processor.apply_volume_envelope(existing_frames, pattern, channel, start_frame)
        
        # Check that existing data is preserved and volume is added
        self.assertEqual(existing_frames["10"]["pulse2"]["note"], 60)
        self.assertEqual(existing_frames["10"][channel]["volume"], 15)
        self.assertEqual(existing_frames["12"][channel]["pitch"], 1000)
        self.assertEqual(existing_frames["12"][channel]["volume"], 9)
        
    def test_duty_envelope_application(self):
        """Test application of duty envelope patterns to frames"""
        frames = {}
        pattern = [0, 1, 2, 3, 2, 1]  # Duty cycle pattern
        channel = "pulse1"
        start_frame = 5
        
        self.processor.apply_duty_envelope(frames, pattern, channel, start_frame)
        
        # Check that frames were created with correct duty values
        for i, expected_duty in enumerate(pattern):
            frame_key = str(start_frame + i)
            self.assertIn(frame_key, frames)
            self.assertIn(channel, frames[frame_key])
            # Duty should be converted to NES duty values (multiplied by 64)
            expected_nes_duty = expected_duty * 64
            self.assertEqual(frames[frame_key][channel]['duty'], expected_nes_duty)
            
        # Test edge cases
        self.assertEqual(frames["5"][channel]['duty'], 0)    # 0 * 64 = 0
        self.assertEqual(frames["7"][channel]['duty'], 128)  # 2 * 64 = 128
        self.assertEqual(frames["8"][channel]['duty'], 192)  # 3 * 64 = 192
        
    def test_envelope_edge_cases(self):
        """Test envelope processing edge cases"""
        # Test with zero note duration
        volume_zero_duration = self.processor.get_envelope_value("default", 0, 0)
        self.assertEqual(volume_zero_duration, 0)  # Should handle gracefully
        
        # Test with frame offset beyond note duration
        volume_beyond = self.processor.get_envelope_value("piano", 50, 10)
        self.assertEqual(volume_beyond, 0)  # Should be in release/silent phase
        
        # Test percussion envelope with very short duration (duration=1)
        # With duration=1, percussion envelope goes straight to decay end (frame 0)
        perc_short = self.processor.get_envelope_value("percussion", 0, 1)
        self.assertEqual(perc_short, 0)  # Actually reaches zero at the end frame
        
        # Test percussion envelope with slightly longer duration (duration=2)
        perc_normal = self.processor.get_envelope_value("percussion", 0, 2)
        self.assertEqual(perc_normal, 15)  # Should start at max with longer duration
        
        # Test percussion envelope decay over time
        perc_mid = self.processor.get_envelope_value("percussion", 1, 10) 
        perc_end = self.processor.get_envelope_value("percussion", 9, 10)
        self.assertGreater(perc_mid, perc_end)  # Should decay over time
        
    def test_control_byte_velocity_scaling(self):
        """Test detailed MIDI velocity scaling in control bytes"""
        envelope_type = "default"
        frame_offset = 0
        note_duration = 10
        duty_cycle = 2
        
        # Test various MIDI velocities
        test_velocities = [0, 8, 16, 32, 64, 96, 127]
        
        for velocity in test_velocities:
            control_byte = self.processor.get_envelope_control_byte(
                envelope_type, frame_offset, note_duration, duty_cycle, 
                base_velocity=velocity
            )
            
            volume = control_byte & 0x0F
            import math
            if velocity > 0:
                expected_volume = max(1, int(15 * math.pow(velocity / 127.0, 1.5)))
            else:
                expected_volume = 0
                
            self.assertEqual(volume, expected_volume)
            
        # Test velocity scaling with different envelope types
        for envelope_type in ["piano", "pad", "pluck"]:
            control_byte = self.processor.get_envelope_control_byte(
                envelope_type, 5, 20, 2, base_velocity=80
            )
            volume = control_byte & 0x0F
            # Should be scaled by both envelope and velocity
            self.assertGreaterEqual(volume, 0)
            self.assertLessEqual(volume, 15)


if __name__ == '__main__':
    unittest.main()
