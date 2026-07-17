import unittest
from tracker.track_mapper import (apply_arpeggio_pattern, apply_arpeggio_fallback, group_notes_by_frame, 
                                  detect_chord, get_arpeggio_pattern)

class TestArpeggioPatterns(unittest.TestCase):
    def setUp(self):
        # Test cases for different chord types
        self.major_triad = [60, 64, 67]      # C major (C E G)
        self.minor_triad = [60, 63, 67]      # C minor (C Eb G)
        self.diminished = [60, 63, 66]       # C diminished (C Eb Gb)
        self.augmented = [60, 64, 68]        # C augmented (C E G#)
        self.power_chord = [60, 67]          # C5 (C G)
        self.seventh = [60, 64, 67, 70]      # C7 (C E G Bb)
        
    def test_basic_patterns(self):
        """Test basic arpeggio patterns with a major triad"""
        patterns = {
            "up": [60, 64, 67],
            "down": [67, 64, 60],
            "up_down": [60, 64, 67, 64],
            "down_up": [67, 64, 60, 64, 67]
        }
        
        for pattern, expected in patterns.items():
            with self.subTest(pattern=pattern):
                result = apply_arpeggio_pattern(self.major_triad, pattern)
                self.assertEqual(result, expected)

    def test_chord_type_patterns(self):
        """Test different chord types with various patterns"""
        test_cases = [
            (self.major_triad, "Major triad"),
            (self.minor_triad, "Minor triad"),
            (self.diminished, "Diminished"),
            (self.augmented, "Augmented"),
            (self.power_chord, "Power chord"),
            (self.seventh, "Seventh chord")
        ]
        
        for notes, chord_type in test_cases:
            with self.subTest(chord_type=chord_type):
                # Test up pattern
                up_result = apply_arpeggio_pattern(notes, "up")
                self.assertEqual(up_result, notes)
                
                # Test down pattern
                down_result = apply_arpeggio_pattern(notes, "down")
                self.assertEqual(down_result, list(reversed(notes)))
                
                # Test that all notes are preserved in random pattern
                random_result = apply_arpeggio_pattern(notes, "random")
                self.assertEqual(sorted(random_result), sorted(notes))

    def test_arpeggio_speed_limits(self):
        """Test arpeggios don't exceed NES capabilities"""
        # Apply fallback with different max_notes values
        for max_notes in [2, 3, 4]:
            with self.subTest(max_notes=max_notes):
                events = [
                    {"frame": 0, "note": note, "velocity": 100}
                    for note in self.seventh  # Using seventh chord (4 notes)
                ]
                result = apply_arpeggio_fallback(events, max_notes=max_notes)
                
                # Check that no frame has more than max_notes notes
                frames = group_notes_by_frame(result)
                for frame_notes in frames.values():
                    self.assertLessEqual(len(frame_notes), max_notes)

    def test_chord_detection_patterns(self):
        """Test that chord detection influences arpeggio patterns"""
        test_cases = [
            (self.major_triad, "major"),
            (self.minor_triad, "minor"),
            (self.diminished, "diminished"),
            (self.augmented, "augmented")
        ]
        
        for notes, expected_type in test_cases:
            with self.subTest(chord_type=expected_type):
                # Detect chord
                chord_info = detect_chord(notes)
                self.assertEqual(chord_info["type"], expected_type)
                
                # Get pattern based on chord type
                pattern = get_arpeggio_pattern(chord_info, style="default")
                result = apply_arpeggio_pattern(notes, pattern)
                
                # Verify all original notes are present at least once
                for note in notes:
                    self.assertIn(note, result)
                
                # Verify the pattern makes musical sense
                self.assertGreaterEqual(len(result), len(notes))  # Can be longer due to repeats
                self.assertLessEqual(len(result), len(notes) * 2)  # But not too long

    def test_style_variations(self):
        """Test different arpeggio styles for each chord type"""
        styles = ["default", "heroic", "mysterious"]
        test_cases = [
            (self.major_triad, "major"),
            (self.minor_triad, "minor")
        ]
        
        for notes, chord_type in test_cases:
            chord_info = {"type": chord_type, "root": notes[0]}
            for style in styles:
                with self.subTest(chord_type=chord_type, style=style):
                    pattern = get_arpeggio_pattern(chord_info, style=style)
                    result = apply_arpeggio_pattern(notes, pattern)
                    
                    # Verify all original notes are present at least once
                    for note in notes:
                        self.assertIn(note, result)
                    
                    # Verify pattern length constraints
                    if style == "mysterious":  # random pattern
                        self.assertEqual(len(result), len(notes))  # No repeats
                    else:
                        self.assertGreaterEqual(len(result), len(notes))
                        self.assertLessEqual(len(result), len(notes) * 2)

    def test_invalid_inputs(self):
        """Test edge cases and invalid inputs"""
        # Empty notes list
        result = apply_arpeggio_pattern([], "up")
        self.assertEqual(result, [])
        
        # Single note
        result = apply_arpeggio_pattern([60], "up_down")
        self.assertEqual(result, [60])
        
        # Invalid pattern
        result = apply_arpeggio_pattern(self.major_triad, "invalid_pattern")
        self.assertEqual(result, self.major_triad)  # Should default to "up"
        
        # None pattern
        result = apply_arpeggio_pattern(self.major_triad, None)
        self.assertEqual(result, self.major_triad)  # Should default to "up"

    def test_random_pattern_consistency(self):
        """Test that random pattern includes all notes and maintains length"""
        for _ in range(5):  # Run multiple times to check consistency
            result = apply_arpeggio_pattern(self.major_triad, "random")
            # Check length
            self.assertEqual(len(result), len(self.major_triad))
            # Check all notes are present exactly once
            self.assertEqual(sorted(result), sorted(self.major_triad))

    def test_random_pattern_is_deterministic(self):
        """#92: 'random' must be reproducible so a MIDI builds the same ROM
        twice. The same chord always arpeggiates identically."""
        a = apply_arpeggio_pattern(self.major_triad, "random")
        b = apply_arpeggio_pattern(self.major_triad, "random")
        self.assertEqual(a, b)
        # Different chords generally get different orders (not all identity).
        other = apply_arpeggio_pattern(self.seventh, "random")
        self.assertEqual(sorted(other), sorted(self.seventh))


class TestArrangerArpStyleParity(unittest.TestCase):
    """#92/ARR-09: the --arranger front-end's ArpStyle / _order_arp_notes must
    implement every documented pattern by delegating to the one canonical
    apply_arpeggio_pattern, instead of silently falling through to up-order for
    down_up/random."""

    def setUp(self):
        from arranger.voice_allocator import ArpStyle
        self.ArpStyle = ArpStyle
        self.major_triad = [60, 64, 67]

    def _order(self, style):
        from arranger.voice_allocator import VoiceAllocator
        return VoiceAllocator(arp_style=style)._order_arp_notes(self.major_triad)

    def test_every_style_matches_canonical(self):
        for style in self.ArpStyle:
            with self.subTest(style=style.name):
                self.assertEqual(
                    self._order(style),
                    apply_arpeggio_pattern(list(self.major_triad), style.value))

    def test_down_up_no_longer_falls_through_to_up(self):
        # The exact regression: DOWN_UP used to return plain up-order.
        self.assertEqual(self._order(self.ArpStyle.DOWN_UP), [67, 64, 60, 64, 67])

    def test_random_style_shuffles_and_is_deterministic(self):
        r = self._order(self.ArpStyle.RANDOM)
        self.assertEqual(sorted(r), sorted(self.major_triad))
        self.assertEqual(r, self._order(self.ArpStyle.RANDOM))
