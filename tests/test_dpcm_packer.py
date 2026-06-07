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
            
    def test_empty_packing_generates_safe_assembly(self):
        """Verify that packing 0 samples doesn't crash the assembly generation."""
        packer = DpcmPacker()
        asm = packer.generate_assembly()
        assert "dpcm_bank_table:\n    .byte $00" in asm