import os
import math

class DpcmPacker:
    BANK_SIZE = 8192
    START_ADDR = 0xC000

    def __init__(self):
        self.banks = []
        self.current_bank_id = 0
        self.current_bank_size = 0
        self.sample_metadata = {}

    def add_sample(self, sample_id: str, file_path: str, pitch_rate: int = 15):
        """Adds a sample to the packing queue, respecting NES 64-byte boundaries.
        
        Args:
            sample_id: Unique identifier for the sample.
            file_path: Path to the raw .dmc file.
            pitch_rate: DPCM playback rate (0-15). Defaults to 15 (max pitch).
        """
        size_bytes = os.path.getsize(file_path)
        
        if size_bytes > 4081:
            raise ValueError(f"Sample {sample_id} exceeds NES max length of 4081 bytes.")

        aligned_size = math.ceil(size_bytes / 64) * 64

        if self.current_bank_size + aligned_size > self.BANK_SIZE:
            self.current_bank_id += 1
            self.current_bank_size = 0
            
            if self.current_bank_id >= 60:
                raise OverflowError("Exceeded maximum allocated DPCM MMC3 banks (60 banks).")

        start_address = self.START_ADDR + self.current_bank_size
        dpcm_address_val = (start_address - 0xC000) // 64
        dpcm_length_val = (size_bytes - 1) // 16
        
        # Mask pitch_rate to ensure it only occupies the lower 4 bits (0-15)
        # We leave bits 6 (Loop) and 7 (IRQ) as 0.
        dpcm_pitch_val = pitch_rate & 0x0F

        self.sample_metadata[sample_id] = {
            "bank": self.current_bank_id,
            "address_reg": dpcm_address_val,
            "length_reg": dpcm_length_val,
            "pitch_reg": dpcm_pitch_val,
            "path": file_path
        }

        if len(self.banks) <= self.current_bank_id:
            self.banks.append([])
        
        self.banks[self.current_bank_id].append((sample_id, file_path))
        self.current_bank_size += aligned_size

    def generate_assembly(self) -> str:
        """Generates the CA65 assembly code to include the packed binaries."""
        asm_lines = ["; --- DPCM Sample Data ---"]
        
        for bank_id, samples in enumerate(self.banks):
            asm_lines.append(f'\n.segment "DPCM_{bank_id:02d}"')
            for sample_id, path in samples:
                asm_lines.append(f'    .align 64')
                asm_lines.append(f'    dpcm_sample_{sample_id}:')
                asm_lines.append(f'    .incbin "{path}"')

        asm_lines.append('\n.segment "RODATA"')
        asm_lines.append("; Lookup tables for DPCM triggers")
        
        ordered_ids = list(self.sample_metadata.keys())
        
        if not ordered_ids:
            # Provide dummy tables if no samples are loaded to prevent assembly errors
            asm_lines.append("dpcm_bank_table:\n    .byte $00")
            asm_lines.append("dpcm_pitch_table:\n    .byte $00")
            asm_lines.append("dpcm_addr_table:\n    .byte $00")
            asm_lines.append("dpcm_len_table:\n    .byte $00")
            return "\n".join(asm_lines)
            
        # Output all 4 lookup tables
        asm_lines.append("dpcm_bank_table:")
        asm_lines.append("    .byte " + ", ".join(f"${self.sample_metadata[k]['bank']:02X}" for k in ordered_ids))
        
        asm_lines.append("dpcm_pitch_table:")
        asm_lines.append("    .byte " + ", ".join(f"${self.sample_metadata[k]['pitch_reg']:02X}" for k in ordered_ids))
        
        asm_lines.append("dpcm_addr_table:")
        asm_lines.append("    .byte " + ", ".join(f"${self.sample_metadata[k]['address_reg']:02X}" for k in ordered_ids))
        
        asm_lines.append("dpcm_len_table:")
        asm_lines.append("    .byte " + ", ".join(f"${self.sample_metadata[k]['length_reg']:02X}" for k in ordered_ids))

        return "\n".join(asm_lines)