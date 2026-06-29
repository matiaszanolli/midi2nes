# New file: tests/test_drum_mapping.py
import json
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
        self.test_index_path = "test_dpcm_index.json"
        
    def test_velocity_ranges(self):
        dpcm_events, noise_events = map_drums_to_dpcm(
            self.test_events, 
            self.test_index_path,
            use_advanced=True
        )
        # With advanced mapping, each drum hit produces layered samples
        # 3 drum hits with 2 layers each = 6 layer events + 3 main events = 9 total
        self.assertEqual(len(dpcm_events), 9)
        
        # Verify sample selection based on velocity by checking main velocity-based samples
        kick_hard_events = [e for e in dpcm_events if e['frame'] == 0 and e['sample_id'] in [0, 2]]  # kick or kick_hard
        kick_soft_events = [e for e in dpcm_events if e['frame'] == 10 and e['sample_id'] in [0, 1]]  # kick or kick_soft
        
        # Should have different velocity-based samples
        kick_hard_velocity_sample = next((e for e in kick_hard_events if e['sample_id'] == 2), None)  # kick_hard
        kick_soft_velocity_sample = next((e for e in kick_soft_events if e['sample_id'] == 1), None)  # kick_soft
        
        self.assertIsNotNone(kick_hard_velocity_sample, "Should have kick_hard sample for high velocity")
        self.assertIsNotNone(kick_soft_velocity_sample, "Should have kick_soft sample for low velocity")
        
    def test_sample_id_is_index_id_not_allocation_order(self):
        """Regression for #65: emitted sample_id must equal the dpcm_index.json
        'id' (which the packer orders its tables by), never the sample
        manager's allocation counter. Allocate snare (index id 4) before kick
        (index id 0); if sample_id followed allocation order the first event
        would be 0 and the second 1 — both wrong."""
        with open(self.test_index_path) as f:
            index = json.load(f)
        snare_id = index["snare"]["id"]
        kick_id = index["kick"]["id"]
        self.assertNotEqual(snare_id, 0,
                            "fixture must have snare at a non-zero id for this test to bite")

        events = {9: [
            {"frame": 0, "note": 38, "velocity": 100},   # snare first
            {"frame": 10, "note": 36, "velocity": 100},  # kick second
        ]}
        dpcm_events, _ = map_drums_to_dpcm(
            events, self.test_index_path, use_advanced=False
        )
        by_frame = {e["frame"]: e["sample_id"] for e in dpcm_events}
        self.assertEqual(by_frame[0], snare_id)   # index id, not allocation 0
        self.assertEqual(by_frame[10], kick_id)   # index id, not allocation 1

    def test_missing_index_file(self):
        with self.assertRaises(FileNotFoundError):
            map_drums_to_dpcm(self.test_events, "nonexistent.json")
            
    def test_invalid_index_file(self):
        with open("invalid.json", "w") as f:
            f.write("invalid json")
        with self.assertRaises(json.JSONDecodeError):
            map_drums_to_dpcm(self.test_events, "invalid.json")
            
    def test_noise_fallback(self):
        events = {9: [{"frame": 0, "note": 99, "velocity": 100}]}  # Invalid note
        dpcm_events, noise_events = map_drums_to_dpcm(events, self.test_index_path)
        self.assertEqual(len(dpcm_events), 0)
        self.assertEqual(len(noise_events), 1)
