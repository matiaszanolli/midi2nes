# New file: tests/test_drum_mapping.py
import unittest
from dpcm_sampler.drum_engine import map_drums_to_dpcm, optimize_dpcm_samples

class TestDrumMapping(unittest.TestCase):
    def setUp(self):
        self.test_events = {
            9: [  # Channel 9 (drums)
                {"frame": 0, "note": 36, "velocity": 100},  # Kick hard
                {"frame": 10, "note": 36, "velocity": 50},  # Kick soft
                {"frame": 20, "note": 38, "velocity": 127}  # Snare hard
            ]
        }
        
    def test_velocity_ranges(self):
        dpcm_events, _ = map_drums_to_dpcm(
            self.test_events, 
            "test_dpcm_index.json",
            use_advanced=True
        )
        self.assertEqual(len(dpcm_events), 3)
        # Verify velocity-based sample selection
        
    def test_layered_samples(self):
        # Test layered sample handling
        pass
        
    def test_sample_optimization(self):
        # Test memory optimization
        pass
