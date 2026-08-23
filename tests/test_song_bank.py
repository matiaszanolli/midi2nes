# tests/test_song_bank.py
import unittest
from pathlib import Path
import json
import tempfile
from nes.song_bank import SongBank, SongMetadata

class TestSongBank(unittest.TestCase):
    def setUp(self):
        self.bank = SongBank()
        self.temp_dir = tempfile.mkdtemp()
        self.test_bank_path = Path(self.temp_dir) / "test_bank.json"
        
        # Create a simple MIDI-like data structure for testing
        self.test_song_data = {
            'events': [
                {'frame': 0, 'note': 60, 'velocity': 100},
                {'frame': 4, 'note': 64, 'velocity': 100}
            ],
            'patterns': {},
            'frames': []
        }

    def tearDown(self):
        # Clean up temporary files
        if self.test_bank_path.exists():
            self.test_bank_path.unlink()

    def test_uses_parser_fast_not_old_parser(self):
        """Regression (#33 / F-14): SongBank must parse with the same
        parser front-end the real pipeline uses (parser_fast), not the
        older full parser -- otherwise a song stored in the bank could be
        parsed differently than the pipeline that would render it."""
        import nes.song_bank as song_bank_module
        from tracker.parser_fast import parse_midi_to_frames as fast_parse
        self.assertIs(song_bank_module.parse_midi_to_frames, fast_parse)

    def test_add_song_from_midi_matches_parser_fast_output(self):
        """The events SongBank stores for a MIDI file must match what
        parser_fast itself produces for the same file (parser parity)."""
        import mido

        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage('track_name', name='Test', time=0))
        track.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
        track.append(mido.Message('note_off', note=60, velocity=0, channel=0, time=480))
        midi_path = Path(self.temp_dir) / "song.mid"
        mid.save(str(midi_path))

        from tracker.parser_fast import parse_midi_to_frames as fast_parse
        expected = fast_parse(str(midi_path))

        self.bank.add_song_from_midi(str(midi_path), name="test_song")
        stored_events = self.bank.songs["test_song"]["segments"]["events"]

        self.assertEqual(stored_events, expected["events"])

    def test_add_song(self):
        """Test adding a song to the bank"""
        metadata = {
            'composer': 'Test Composer',
            'loop_point': 100,
            'tags': ['test', 'demo'],
            'tempo_base': 120
        }
        
        self.bank.add_song('test_song', self.test_song_data, metadata)
        
        # Verify song was added
        self.assertIn('test_song', self.bank.songs)
        song_data = self.bank.songs['test_song']
        
        # Verify metadata
        self.assertEqual(song_data['metadata']['composer'], 'Test Composer')
        self.assertEqual(song_data['metadata']['loop_point'], 100)
        self.assertEqual(song_data['metadata']['tags'], ['test', 'demo'])
        
        # Verify bank assignment
        self.assertIsInstance(song_data['bank'], int)
        self.assertGreaterEqual(song_data['bank'], 0)
        self.assertLess(song_data['bank'], self.bank.total_banks)

    def test_order_survives_remove_then_add_without_colliding(self):
        """Regression (#488/PIPE-2026-08-22-4): order used to be
        len(self.songs), which reuses a just-freed slot's index -- add A,
        B, C (order 0, 1, 2); remove B; add D used to give D order=2,
        colliding with C. order must stay monotonic and never reused."""
        self.bank.add_song('A', self.test_song_data, {})
        self.bank.add_song('B', self.test_song_data, {})
        self.bank.add_song('C', self.test_song_data, {})
        self.assertEqual(
            {n: s['metadata']['order'] for n, s in self.bank.songs.items()},
            {'A': 0, 'B': 1, 'C': 2})

        del self.bank.songs['B']  # mirrors run_song_remove's delete-without-renumber
        self.bank.add_song('D', self.test_song_data, {})

        orders = {n: s['metadata']['order'] for n, s in self.bank.songs.items()}
        self.assertEqual(len(orders), len(set(orders.values())),
                          f"order values must be unique after remove+add: {orders}")
        self.assertNotEqual(orders['D'], orders['C'],
                             "D must not reuse C's order after B was removed")

    def test_order_starts_at_zero_for_an_empty_bank(self):
        self.assertEqual(self.bank._next_order(), 0)

    def test_add_song_from_midi_order_matches_add_song_authoritative_value(self):
        """add_song_from_midi's own SongMetadata.order is informational only
        -- add_song recomputes it via _next_order(). Both must agree, so a
        future refactor that starts trusting the passed-through value
        doesn't silently diverge from what's actually stored."""
        import unittest.mock as mock
        with mock.patch('nes.song_bank.parse_midi_to_frames',
                         return_value={'events': [], 'patterns': {}, 'frames': []}):
            self.bank.add_song_from_midi('fake.mid', name='first')
            self.bank.add_song_from_midi('fake2.mid', name='second')
        self.assertEqual(self.bank.songs['first']['metadata']['order'], 0)
        self.assertEqual(self.bank.songs['second']['metadata']['order'], 1)

    def test_bank_size_limits(self):
        """Test bank size limitations"""
        # Create a song that will take about 1/4 of a bank
        quarter_bank_events = []
        for i in range(500):  # 500 events * 8 bytes = 4000 bytes
            quarter_bank_events.append({
                'frame': i,
                'note': 60,
                'velocity': 100
            })
        
        medium_song_data = {
            'events': quarter_bank_events,
            'patterns': {},
            'frames': list(range(200))  # 200 frames * 4 bytes = 800 bytes
        }
        
        # First, verify we can add at least one song
        self.bank.add_song('test_song_0', medium_song_data, {'tempo_base': 120})
        self.assertEqual(len(self.bank.songs), 1)
        
        # Now add more songs until we fill the banks
        songs_added = 1
        try:
            while True:
                self.bank.add_song(f'test_song_{songs_added}', 
                                medium_song_data, 
                                {'tempo_base': 120})
                songs_added += 1
                
                # Safety check to prevent infinite loop
                if songs_added > 50:
                    self.fail("Added too many songs without hitting bank limit")
        except ValueError as e:
            # Expected when banks are full
            self.assertIn("bank space", str(e).lower())
        
        # We should be able to add at least 3 songs per bank
        # With 8 banks, we should get at least 24 songs total
        self.assertGreater(songs_added, 3)
        
        # Verify bank usage
        usage = self.bank.calculate_bank_usage()
        self.assertTrue(any(size > 0 for size in usage.values()))
        # Fix: Use self.bank.max_bank_size instead of self.max_bank_size
        self.assertTrue(all(size <= self.bank.max_bank_size for size in usage.values()))

    def test_get_song_data(self):
        """Test retrieving song data"""
        metadata = {'composer': 'Test Composer', 'loop_point': 100}
        self.bank.add_song('test_song', self.test_song_data, metadata)
        
        song_data = self.bank.get_song_data('test_song')
        
        self.assertIsNotNone(song_data)
        self.assertEqual(song_data['metadata']['composer'], 'Test Composer')
        self.assertEqual(song_data['metadata']['loop_point'], 100)
        
        # Test non-existent song
        self.assertIsNone(self.bank.get_song_data('non_existent_song'))

    def test_calculate_bank_usage(self):
        """Test bank usage calculation"""
        # Add multiple songs
        self.bank.add_song('song1', self.test_song_data, {'tempo_base': 120})
        self.bank.add_song('song2', self.test_song_data, {'tempo_base': 120})
        
        usage = self.bank.calculate_bank_usage()
        
        # Verify usage data
        self.assertIsInstance(usage, dict)
        self.assertTrue(all(isinstance(bank, int) for bank in usage.keys()))
        self.assertTrue(all(isinstance(size, int) for size in usage.values()))
        self.assertTrue(all(size <= self.bank.max_bank_size for size in usage.values()))

    def test_duplicate_song_handling(self):
        """Test handling of duplicate song names"""
        self.bank.add_song('test_song', self.test_song_data, {'tempo_base': 120})
        
        # Attempt to add song with same name
        with self.assertRaises(ValueError):
            self.bank.add_song('test_song', self.test_song_data, {'tempo_base': 120})

    def test_metadata_validation(self):
        """Test metadata validation"""
        # Test with invalid tempo
        with self.assertRaises(ValueError):
            self.bank.add_song('test_song', self.test_song_data, 
                             {'tempo_base': -1})
        
        # Test with invalid loop point
        with self.assertRaises(ValueError):
            self.bank.add_song('test_song', self.test_song_data,
                             {'loop_point': -1})

    def test_import_bank_missing_file_raises_clear_error(self):
        """Regression (#220/SAFE-09): a missing --bank file must raise a
        clear FileNotFoundError, not a raw traceback from Path.read_text()."""
        missing = Path(self.temp_dir) / "does_not_exist.json"
        with self.assertRaises(FileNotFoundError):
            self.bank.import_bank(str(missing))

    def test_import_bank_invalid_json_raises_clear_error(self):
        """Regression (#220/SAFE-09): truncated/garbage JSON must raise a
        clear ValueError, not a raw json.JSONDecodeError traceback."""
        self.test_bank_path.write_text("{not valid json")
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_missing_bank_info_raises_clear_error(self):
        """Regression (#220/SAFE-09): a bank file missing 'bank_info' must
        raise a clear ValueError, not a raw KeyError."""
        self.test_bank_path.write_text(json.dumps({'songs': {}}))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_missing_songs_raises_clear_error(self):
        """Regression (#220/SAFE-09): a bank file missing 'songs' must raise
        a clear ValueError, not a raw KeyError."""
        self.test_bank_path.write_text(json.dumps({
            'bank_info': {'total_banks': 1, 'bank_size': 100}
        }))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_song_entry_not_a_dict_raises_clear_error(self):
        """Regression (#427/PIPE-2026-08-21-5): the bank-level guard (#220/
        SAFE-09) stops one level up -- a per-song entry that isn't even a
        JSON object must still raise a clear ValueError here, not reach a
        consumer's raw subscript."""
        self.test_bank_path.write_text(json.dumps({
            'bank_info': {'total_banks': 1, 'bank_size': 100},
            'songs': {'broken_song': "not an object"}
        }))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_song_entry_missing_metadata_raises_clear_error(self):
        """Regression (#427/PIPE-2026-08-21-5): a song entry missing
        'metadata' used to reach run_song_build's sort key
        (bank.songs[name]['metadata'].get('order', 0)) or run_song_list's
        print loop as an unguarded KeyError, outside any try/except -- must
        now raise a clear ValueError at import time instead."""
        self.test_bank_path.write_text(json.dumps({
            'bank_info': {'total_banks': 1, 'bank_size': 100},
            'songs': {'broken_song': {'bank': 0, 'size': 100}}
        }))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_song_entry_metadata_not_a_dict_raises_clear_error(self):
        """A 'metadata' value that parses but isn't itself a JSON object
        (e.g. a string) would raise AttributeError on the first .get() call
        downstream -- must be caught here instead."""
        self.test_bank_path.write_text(json.dumps({
            'bank_info': {'total_banks': 1, 'bank_size': 100},
            'songs': {'broken_song': {'metadata': "oops", 'bank': 0, 'size': 100}}
        }))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_song_entry_missing_bank_raises_clear_error(self):
        """Regression (#427/PIPE-2026-08-21-5): a song entry missing 'bank'
        used to reach run_song_list's print loop (song_data['bank']) as an
        unguarded KeyError."""
        self.test_bank_path.write_text(json.dumps({
            'bank_info': {'total_banks': 1, 'bank_size': 100},
            'songs': {'broken_song': {'metadata': {'title': 'x'}, 'size': 100}}
        }))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_song_entry_missing_size_raises_clear_error(self):
        """Regression (#427/PIPE-2026-08-21-5): a song entry missing 'size'
        used to reach get_bank_size's sum (song_data['size']) as an
        unguarded KeyError."""
        self.test_bank_path.write_text(json.dumps({
            'bank_info': {'total_banks': 1, 'bank_size': 100},
            'songs': {'broken_song': {'metadata': {'title': 'x'}, 'bank': 0}}
        }))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_import_bank_songs_not_a_dict_raises_clear_error(self):
        """A 'songs' value that parses but isn't a JSON object (e.g. a list)
        must raise a clear ValueError, not an AttributeError from .items()."""
        self.test_bank_path.write_text(json.dumps({
            'bank_info': {'total_banks': 1, 'bank_size': 100},
            'songs': ["not", "an", "object"]
        }))
        with self.assertRaises(ValueError):
            self.bank.import_bank(str(self.test_bank_path))

    def test_add_song_from_midi_stores_resolved_midi_path(self):
        """Regression (#30/F-13): `song build` re-parses/re-maps from the
        original MIDI (SongBank's stored `segments` are raw parsed events
        only, not compile-ready frames) -- so add_song_from_midi must record
        the source path, resolved to absolute so a build run from a
        different cwd than `song add` can still find it."""
        import mido

        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message('note_on', note=60, velocity=100, channel=0, time=0))
        track.append(mido.Message('note_off', note=60, velocity=0, channel=0, time=480))
        midi_path = Path(self.temp_dir) / "song.mid"
        mid.save(str(midi_path))

        self.bank.add_song_from_midi(str(midi_path), name="test_song")

        self.assertEqual(
            self.bank.songs["test_song"]["midi_path"], str(midi_path.resolve()))

    def test_add_song_midi_path_defaults_to_none(self):
        """`add_song` called directly (no MIDI file involved, e.g. a hand-built
        segments dict) must not require midi_path -- it's optional and absent
        songs are exactly what `song build` uses to raise a clear per-song
        error rather than crash (see main.py's run_song_build)."""
        self.bank.add_song('test_song', self.test_song_data, {'tempo_base': 120})
        self.assertIsNone(self.bank.songs['test_song']['midi_path'])

    def test_import_bank_valid_file_roundtrips(self):
        """A well-formed bank file (as produced by export_bank) must still
        import successfully after the new guard."""
        self.bank.add_song('test_song', self.test_song_data, {'tempo_base': 120})
        self.bank.export_bank(str(self.test_bank_path))

        reloaded = SongBank()
        reloaded.import_bank(str(self.test_bank_path))
        self.assertIn('test_song', reloaded.songs)
        self.assertEqual(reloaded.total_banks, self.bank.total_banks)
        self.assertEqual(reloaded.max_bank_size, self.bank.max_bank_size)

    def test_import_bank_keep_segments_false_drops_segments_payload(self):
        """#504/PERF-B-01: a caller that never reads `segments` (e.g. `song
        build`, `song list`) can opt out of retaining it in memory after
        import -- confirms the entry survives with everything else intact
        but `segments` itself is gone."""
        self.bank.add_song('test_song', self.test_song_data, {'tempo_base': 120})
        self.bank.export_bank(str(self.test_bank_path))

        reloaded = SongBank()
        reloaded.import_bank(str(self.test_bank_path), keep_segments=False)
        self.assertIn('test_song', reloaded.songs)
        entry = reloaded.songs['test_song']
        self.assertNotIn('segments', entry)
        # Everything else a consumer (run_song_build/run_song_list) actually
        # reads must still be present.
        self.assertIn('metadata', entry)
        self.assertIn('bank', entry)
        self.assertIn('midi_path', entry)

    def test_import_bank_default_keeps_segments_payload(self):
        """The default (keep_segments=True) must be unchanged -- callers
        that re-export the bank (`song add`/`song remove`) need every
        entry's `segments` intact or export_bank would silently drop it."""
        self.bank.add_song('test_song', self.test_song_data, {'tempo_base': 120})
        self.bank.export_bank(str(self.test_bank_path))

        reloaded = SongBank()
        reloaded.import_bank(str(self.test_bank_path))
        self.assertIn('segments', reloaded.songs['test_song'])
        self.assertEqual(
            reloaded.songs['test_song']['segments'], self.test_song_data)

    def test_export_bank_writes_atomically(self):
        """Regression (#456/SAFE-2026-08-21-2): export_bank must use
        core.io_utils.atomic_write_text (the same fix the CA65/FamiStudio
        exporters already got, #385), not a direct Path.write_text -- a
        failure mid-write must never truncate/overwrite a prior good bank."""
        from unittest.mock import patch
        self.bank.add_song('song1', self.test_song_data, {'tempo_base': 120})
        self.bank.export_bank(str(self.test_bank_path))
        original_content = self.test_bank_path.read_text()

        self.bank.add_song('song2', self.test_song_data, {'tempo_base': 120})
        with patch('os.replace', side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.bank.export_bank(str(self.test_bank_path))

        # The prior good bank (with only song1) must survive intact --
        # song2 must not appear in a truncated/partial file.
        self.assertEqual(self.test_bank_path.read_text(), original_content)
        self.assertNotIn('song2', original_content)

    def test_export_bank_leaves_no_leftover_temp_file(self):
        self.bank.add_song('song1', self.test_song_data, {'tempo_base': 120})
        self.bank.export_bank(str(self.test_bank_path))

        remaining = list(self.test_bank_path.parent.iterdir())
        self.assertEqual(remaining, [self.test_bank_path])


if __name__ == '__main__':
    unittest.main()
