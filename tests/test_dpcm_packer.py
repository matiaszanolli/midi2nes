import pytest
from unittest.mock import patch
from dpcm_sampler.dpcm_packer import DpcmPacker


class TestDpcmPacker:

    @patch('os.path.getsize')
    def test_ffd_algorithm_saves_space(self, mock_getsize):
        """
        Verify that First Fit Decreasing (FFD) packs samples more efficiently
        than naive sequential packing.
        
        Using sizes (unaligned): 2500, 4000, 2500, 4000, 2500
        Aligned to 64 bytes: 2560, 4032, 2560, 4032, 2560
        
        A naive sequential packer would require 3 banks (8192 bytes each):
        Bank 1: 2560 + 4032 = 6592
        Bank 2: 2560 + 4032 = 6592
        Bank 3: 2560
        
        FFD sorts largest first (4032, 4032, 2560, 2560, 2560) and requires only 2 banks:
        Bank 1: 4032 + 4032 = 8064 (fits within 8192)
        Bank 2: 2560 + 2560 + 2560 = 7680 (fits within 8192)
        """
        # Map sample ID to file size for the mock
        sizes = {
            "S1": 2500,
            "S2": 4000,
            "S3": 2500,
            "S4": 4000,
            "S5": 2500
        }
        
        # Configure the mock to return sizes based on the "file path" (which we set to the ID)
        mock_getsize.side_effect = lambda path: sizes.get(path, 0)
        
        packer = DpcmPacker()
        
        # Add samples in the inefficient sequential order
        packer.add_sample("S1", "S1")
        packer.add_sample("S2", "S2")
        packer.add_sample("S3", "S3")
        packer.add_sample("S4", "S4")
        packer.add_sample("S5", "S5")
        
        # Trigger the bin-packing algorithm
        packer._pack_samples()
        
        # Validate that FFD successfully fit them into 2 banks instead of 3
        assert len(packer.banks) == 2
        
        # Verify Bank 1 has the two 4000-byte samples
        bank_1_ids = [sample[0] for sample in packer.banks[0]]
        assert "S2" in bank_1_ids
        assert "S4" in bank_1_ids
        assert len(bank_1_ids) == 2
        
        # Verify Bank 2 has the three 2500-byte samples
        bank_2_ids = [sample[0] for sample in packer.banks[1]]
        assert "S1" in bank_2_ids
        assert "S3" in bank_2_ids
        assert "S5" in bank_2_ids
        assert len(bank_2_ids) == 3

    @patch('os.path.getsize')
    def test_oversized_sample_raises_error(self, mock_getsize):
        """Verify that samples larger than 4081 bytes are rejected based on NES hardware limits."""
        mock_getsize.return_value = 4082
        
        packer = DpcmPacker()
        with pytest.raises(ValueError, match="exceeds NES max length of 4081 bytes"):
            packer.add_sample("S1", "dummy_path.dmc")
            
    @patch('os.path.getsize')
    def test_oversized_sample_truncated_not_aborted(self, mock_getsize):
        """Regression for #68: with truncate=True an oversized file is clamped to
        4081 bytes instead of raising, so one big sample never discards the rest
        of the catalog. The truncated sample stays addressable (bounded .incbin,
        max length register) and keeps its table slot aligned with its index id."""
        sizes = {'ok.dmc': 1000, 'big.dmc': 69347}
        mock_getsize.side_effect = lambda p: sizes[p]

        packer = DpcmPacker()
        packer.add_sample('0', 'ok.dmc', truncate=True)
        packer.add_sample('1', 'big.dmc', truncate=True)  # would raise without truncate
        asm = packer.generate_assembly()

        # Both samples packed (not the dummy single-byte fallback).
        assert 'dpcm_sample_0:' in asm
        assert 'dpcm_sample_1:' in asm
        assert 'dpcm_bank_table:\n    .byte $00\ndpcm_pitch_table' not in asm
        # The oversized sample emits a bounded include; the in-range one does not.
        assert '.incbin "big.dmc", 0, 4081' in asm
        assert '.incbin "ok.dmc"\n' in asm
        # Truncated sample's length register is the hardware max ((4081-1)//16 = 255).
        assert packer.sample_metadata['1']['length_reg'] == 255

    @patch('os.path.getsize')
    def test_length_reg_rounds_up_not_floors(self, mock_getsize):
        """Regression (#75/D-12): the DMC plays back (length_reg*16)+1 bytes.
        Flooring (size-1)//16 for a size not of the form 16k+1 silently
        discarded up to 15 trailing bytes (1024 -> length_reg=63 -> only 1009
        of 1024 bytes played). length_reg must round UP so the full sample
        plays, with the gap up to the rounded boundary explicitly zero-padded
        rather than left to whatever bytes happen to follow in ROM."""
        mock_getsize.return_value = 1024
        packer = DpcmPacker()
        packer.add_sample('0', 'drum.dmc')
        asm = packer.generate_assembly()

        # ceil((1024-1)/16) = 64, not the floor 63.
        assert packer.sample_metadata['0']['length_reg'] == 64
        played_bytes = packer.sample_metadata['0']['length_reg'] * 16 + 1
        assert played_bytes >= 1024
        # Exactly 1 byte of padding needed to reach the 64*16+1 = 1025 boundary.
        assert packer.sample_metadata['0']['pad_bytes'] == 1
        assert '.incbin "drum.dmc"' in asm
        assert '.res 1, $00' in asm

    @patch('os.path.getsize')
    def test_length_reg_exact_16k_plus_1_needs_no_padding(self, mock_getsize):
        """A size already of the form 16k+1 needs no rounding or padding."""
        mock_getsize.return_value = 2049  # 16*128 + 1
        packer = DpcmPacker()
        packer.add_sample('0', 'exact.dmc')
        asm = packer.generate_assembly()

        assert packer.sample_metadata['0']['length_reg'] == 128
        assert packer.sample_metadata['0']['pad_bytes'] == 0
        assert '.res' not in asm

    @patch('os.path.getsize')
    def test_length_reg_never_exceeds_hardware_max_after_rounding(self, mock_getsize):
        """Regression (#75/D-12 RANGE check): rounding up must never push
        length_reg past the hardware max of 255, even for a size just under
        the 4081-byte ceiling."""
        mock_getsize.return_value = 4080  # one byte short of the 4081 max
        packer = DpcmPacker()
        packer.add_sample('0', 'near_max.dmc')
        packer.generate_assembly()
        assert packer.sample_metadata['0']['length_reg'] == 255
        assert packer.sample_metadata['0']['pad_bytes'] == 1

    @patch('os.path.getsize')
    def test_lookup_tables_are_positional_by_absolute_id(self, mock_getsize):
        """Regression for #140: the engine indexes the lookup tables by absolute
        sample id, so packing a sparse subset must emit a placeholder for every
        unpacked id and keep each real entry at its id's offset. Only the
        referenced sample binaries are included."""
        # len_reg rounds UP (#75/D-12): ceil((1000-1)/16) = 63 = 0x3F, not the
        # floor 62 = 0x3E (which would silently drop the last 15 bytes).
        mock_getsize.return_value = 1000
        packer = DpcmPacker()
        packer.add_sample('2', 'a.dmc')
        packer.add_sample('5', 'b.dmc')
        asm = packer.generate_assembly()

        def row(label):
            lines = asm.splitlines()
            i = next(k for k, l in enumerate(lines) if l.startswith(label))
            return [b.strip() for b in lines[i + 1].split('.byte')[1].split(',')]

        len_row = row('dpcm_len_table:')
        assert len(len_row) == 6                       # ids 0..5
        assert len_row[2] == '$3F' and len_row[5] == '$3F'
        assert len_row[0] == len_row[1] == len_row[3] == len_row[4] == '$00'
        assert asm.count('.incbin') == 2               # only the two referenced binaries

    def test_get_dpcm_sample_ids_from_frames(self):
        """get_dpcm_sample_ids_from_frames recovers dense_id = note - 1 from DPCM
        frames, mapped to the real catalog id via dpcm_sample_map. Without a
        dpcm_sample_map (older frames.json, #200/D-14), dense_id and catalog_id
        are treated as identical -- the pre-remap behavior."""
        from dpcm_sampler.generate_dpcm_index import get_dpcm_sample_ids_from_frames
        frames = {'dpcm': {'0': {'note': 3, 'volume': 15},
                           '8': {'note': 6, 'volume': 15},
                           '9': {'note': 0}}}              # rest sentinel ignored
        assert get_dpcm_sample_ids_from_frames(frames) == {2: 2, 5: 5}
        assert get_dpcm_sample_ids_from_frames({}) == {}
        assert get_dpcm_sample_ids_from_frames({'dpcm': {}}) == {}

    def test_get_dpcm_sample_ids_from_frames_uses_dpcm_sample_map(self):
        """Regression (#200/D-14): when dpcm_sample_map is present, the dense
        frame ids must resolve to the real catalog ids it records, not the
        dense ids themselves."""
        from dpcm_sampler.generate_dpcm_index import get_dpcm_sample_ids_from_frames
        frames = {
            'dpcm': {'0': {'note': 1, 'volume': 15}, '10': {'note': 2, 'volume': 15}},
            'dpcm_sample_map': {'0': 1318, '1': 1620},
        }
        assert get_dpcm_sample_ids_from_frames(frames) == {0: 1318, 1: 1620}

    @patch('dpcm_sampler.generate_dpcm_index.resolve_dpcm_sample_path')
    @patch('os.path.getsize')
    def test_load_packs_only_referenced_sample_ids(self, mock_getsize, mock_resolve):
        """Regression for #140: with sample_ids, only the referenced samples are
        added to the packer (not the whole catalog)."""
        from pathlib import Path
        from dpcm_sampler.generate_dpcm_index import load_dpcm_index_into_packer
        mock_getsize.return_value = 500
        mock_resolve.side_effect = lambda fn, ip: Path(fn)
        index = {f"s{i}": {"id": i, "filename": f"{i}.dmc"} for i in range(10)}
        packer = DpcmPacker()
        loaded, _ = load_dpcm_index_into_packer(
            packer, index, "dpcm_index.json", sample_ids={2, 5, 7})
        assert loaded == 3
        assert {s['id'] for s in packer.pending_samples} == {'2', '5', '7'}

    @patch('dpcm_sampler.generate_dpcm_index.resolve_dpcm_sample_path')
    @patch('os.path.getsize')
    def test_load_keys_by_dense_id_when_sample_ids_is_a_map(self, mock_getsize, mock_resolve):
        """Regression (#200/D-14): when sample_ids is a {dense_id: catalog_id}
        dict (get_dpcm_sample_ids_from_frames's new return shape), entries
        must be added to the packer keyed by the small dense id, not the
        (potentially huge, up to 1922) catalog id -- otherwise the packer's
        positional lookup tables would balloon to the catalog id's size, and
        wouldn't line up with what the bytecode's note-1 actually indexes."""
        from pathlib import Path
        from dpcm_sampler.generate_dpcm_index import load_dpcm_index_into_packer
        mock_getsize.return_value = 500
        mock_resolve.side_effect = lambda fn, ip: Path(fn)
        index = {
            "kick": {"id": 1318, "filename": "kick.dmc"},
            "snare": {"id": 1620, "filename": "snare.dmc"},
            "unused": {"id": 5, "filename": "unused.dmc"},
        }
        packer = DpcmPacker()
        loaded, skipped = load_dpcm_index_into_packer(
            packer, index, "dpcm_index.json", sample_ids={0: 1318, 1: 1620})
        assert loaded == 2
        assert skipped == 0
        assert {s['id'] for s in packer.pending_samples} == {'0', '1'}

    def test_empty_packing_generates_safe_assembly(self):
        """Verify that packing 0 samples doesn't crash the assembly generation."""
        packer = DpcmPacker()
        asm = packer.generate_assembly()
        assert "dpcm_bank_table:\n    .byte $00" in asm