"""Contract tests for arranger noise/DPCM frame keys (issue #84).

The CA65 exporter reads the noise period from `note` (low nibble) and gates DPCM
on `volume`, recovering the sample id from `note` = sample_id + 1 — the same
per-channel contract `NESEmulatorCore.process_all_tracks` emits (#9). The
arranger used to emit noise under a `period` key (no `note`) and DPCM under a
`sample` key (no `note`/`volume`), so every arranger noise hit read as period 0
and every DPCM frame was skipped. These tests pin that the arranger now shares
the legacy per-channel key set.
"""
import unittest
from unittest.mock import patch

from arranger.pipeline_integration import arrange_for_nes
from nes.emulator_core import NESEmulatorCore


def _legacy_keysets():
    """Per-channel frame key sets emitted by the canonical contract."""
    mapped = {
        'noise': [{'frame': 0, 'note': 7, 'volume': 100, 'noise_mode': 0}],
        'dpcm': [{'frame': 0, 'note': 0, 'sample_id': 4, 'volume': 100}],
    }
    frames = NESEmulatorCore().process_all_tracks(mapped)
    noise_keys = set(next(iter(frames['noise'].values())).keys())
    dpcm_keys = set(next(iter(frames['dpcm'].values())).keys())
    return noise_keys, dpcm_keys


class TestArrangerFrameContract(unittest.TestCase):
    def test_dpcm_frames_use_note_and_volume(self):
        """Live path: a detected channel-9 drum track yields DPCM frames keyed by
        note (= sample_id + 1) and volume, never a `sample` key."""
        events = {'drums': [
            {'frame': 0, 'note': 36, 'volume': 110, 'type': 'note_on', 'channel': 9},
            {'frame': 4, 'note': 36, 'volume': 0, 'type': 'note_off', 'channel': 9},
        ]}
        out = arrange_for_nes(events)
        self.assertTrue(out['dpcm'], "expected DPCM frames for a channel-9 drum track")
        for fd in out['dpcm'].values():
            self.assertIn('note', fd)
            self.assertIn('volume', fd)
            self.assertNotIn('sample', fd)
            self.assertGreaterEqual(fd['note'], 1)   # sample_id + 1, never the rest sentinel
            self.assertGreater(fd['volume'], 0)      # exporter gates on volume > 0

    @patch('arranger.pipeline_integration.allocate_with_arpeggiation')
    def test_noise_and_dpcm_conversion_matches_legacy_contract(self, mock_alloc):
        """Drive the conversion with a controlled allocator output and assert the
        emitted noise/DPCM frames carry exactly the legacy per-channel keys."""
        mock_alloc.return_value = {
            'pulse1': {}, 'pulse2': {}, 'triangle': {},
            'noise': {0: {'period': 7, 'volume': 9}},
            'dpcm': {0: {'sample': 4}},
        }
        out = arrange_for_nes({'drums': [
            {'frame': 0, 'note': 38, 'volume': 100, 'type': 'note_on', 'channel': 9},
            {'frame': 2, 'note': 38, 'volume': 0, 'type': 'note_off', 'channel': 9},
        ]})

        noise_keys, dpcm_keys = _legacy_keysets()
        self.assertEqual(set(out['noise'][0].keys()), noise_keys)
        self.assertEqual(set(out['dpcm'][0].keys()), dpcm_keys)

        # Values follow the contract: noise period under `note`, DPCM sample+1.
        self.assertEqual(out['noise'][0]['note'], 7)
        self.assertEqual(out['noise'][0]['control'], 0)   # mode 0
        self.assertEqual(out['dpcm'][0]['note'], 5)        # sample 4 + 1
        self.assertEqual(out['dpcm'][0]['volume'], 15)


if __name__ == '__main__':
    unittest.main()
