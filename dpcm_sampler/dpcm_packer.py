import os
import math

class DpcmPacker:
    BANK_SIZE = 8192
    START_ADDR = 0xC000

    def __init__(self):
        self.banks = []
        self.sample_metadata = {}
        self.pending_samples = []

    def add_sample(self, sample_id: str, file_path: str, pitch_rate: int = 15,
                   truncate: bool = False):
        """Adds a sample to the packing queue, respecting NES 64-byte boundaries.

        Args:
            sample_id: Unique identifier for the sample.
            file_path: Path to the raw .dmc file.
            pitch_rate: DPCM playback rate (0-15). Defaults to 15 (max pitch).
            truncate: When True, a file longer than the NES DMC limit is clamped
                to the first 4081 bytes (the maximum addressable length, L=255 ->
                255*16+1) instead of raising. This keeps one oversized sample from
                aborting the whole pack (#68); because the sample is truncated
                rather than skipped, its lookup-table slot stays aligned with its
                index id (the tables are positional — see generate_assembly).
        """
        size_bytes = os.path.getsize(file_path)
        incbin_size = None  # None => .incbin the whole file

        if size_bytes > 4081:
            if not truncate:
                raise ValueError(f"Sample {sample_id} exceeds NES max length of 4081 bytes.")
            # Clamp to the hardware maximum so the sample stays addressable.
            size_bytes = 4081
            incbin_size = 4081

        # The DMC plays back (length_reg*16)+1 bytes, so any size not of the
        # form 16k+1 needs its length register ROUNDED UP (not floored) to
        # cover every real byte -- flooring silently discarded up to 15
        # trailing bytes (#75/D-12). Round up and pad the gap with explicit
        # zero bytes (emitted in generate_assembly) rather than relying on
        # whatever bytes happen to follow in ROM.
        length_reg = math.ceil((size_bytes - 1) / 16) if size_bytes > 0 else 0
        padded_size = length_reg * 16 + 1
        pad_bytes = padded_size - size_bytes

        aligned_size = math.ceil(padded_size / 64) * 64

        self.pending_samples.append({
            'id': sample_id,
            'path': file_path,
            'pitch': pitch_rate,
            'size': size_bytes,
            'length_reg': length_reg,
            'pad_bytes': pad_bytes,
            'aligned_size': aligned_size,
            'incbin_size': incbin_size
        })

    def _pack_samples(self):
        """Pack pending samples into minimum number of banks using First Fit Decreasing."""
        # Sort pending samples by aligned size descending
        sorted_samples = sorted(self.pending_samples, key=lambda x: x['aligned_size'], reverse=True)
        
        self.banks = []
        bank_sizes = []
        
        for sample in sorted_samples:
            placed = False
            for bank_id in range(len(self.banks)):
                if bank_sizes[bank_id] + sample['aligned_size'] <= self.BANK_SIZE:
                    start_address = self.START_ADDR + bank_sizes[bank_id]
                    self._place_sample(sample, bank_id, start_address)
                    self.banks[bank_id].append((sample['id'], sample['path']))
                    bank_sizes[bank_id] += sample['aligned_size']
                    placed = True
                    break
            
            if not placed:
                if len(self.banks) >= 60:
                    raise OverflowError("Exceeded maximum allocated DPCM MMC3 banks (60 banks).")
                
                bank_id = len(self.banks)
                self.banks.append([(sample['id'], sample['path'])])
                bank_sizes.append(sample['aligned_size'])
                self._place_sample(sample, bank_id, self.START_ADDR)

    def _place_sample(self, sample: dict, bank_id: int, start_address: int):
        dpcm_address_val = (start_address - 0xC000) // 64
        dpcm_pitch_val = sample['pitch'] & 0x0F

        self.sample_metadata[sample['id']] = {
            "bank": bank_id,
            "address_reg": dpcm_address_val,
            "length_reg": sample['length_reg'],
            "pitch_reg": dpcm_pitch_val,
            "path": sample['path'],
            "incbin_size": sample.get('incbin_size'),
            "pad_bytes": sample['pad_bytes']
        }

    def generate_assembly(self) -> str:
        """Generates the CA65 assembly code to include the packed binaries."""
        self._pack_samples()
        
        asm_lines = ["; --- DPCM Sample Data ---"]
        
        for bank_id, samples in enumerate(self.banks):
            asm_lines.append(f'\n.segment "DPCM_{bank_id:02d}"')
            for sample_id, path in samples:
                asm_lines.append(f'    .align 64')
                asm_lines.append(f'    dpcm_sample_{sample_id}:')
                incbin_size = self.sample_metadata[sample_id].get('incbin_size')
                if incbin_size is not None:
                    # Bound the include so a truncated oversized sample emits
                    # only its first 4081 bytes (#68).
                    asm_lines.append(f'    .incbin "{path}", 0, {incbin_size}')
                else:
                    asm_lines.append(f'    .incbin "{path}"')
                # length_reg is rounded UP to the sample's real byte count
                # (#75/D-12), so explicitly zero-fill the gap up to the next
                # 16k+1 boundary instead of relying on whatever bytes happen
                # to follow in ROM.
                pad_bytes = self.sample_metadata[sample_id]['pad_bytes']
                if pad_bytes:
                    asm_lines.append(f'    .res {pad_bytes}, $00')

        asm_lines.append('\n.segment "RODATA"')
        asm_lines.append("; Lookup tables for DPCM triggers")
        
        ordered_ids = sorted(self.sample_metadata.keys(), key=lambda x: int(x))

        if not ordered_ids:
            # Provide dummy tables if no samples are loaded to prevent assembly errors
            asm_lines.append("dpcm_bank_table:\n    .byte $00")
            asm_lines.append("dpcm_pitch_table:\n    .byte $00")
            asm_lines.append("dpcm_addr_table:\n    .byte $00")
            asm_lines.append("dpcm_len_table:\n    .byte $00")
            return "\n".join(asm_lines)

        # The engine indexes the lookup tables by absolute sample id (note - 1),
        # so each table is POSITIONAL: entry N must hold sample N's registers.
        # When a song ships only the samples it references (#140) the packed ids
        # are sparse, so emit a placeholder ($00) for every id that isn't packed —
        # those slots are never indexed (no frame references them) and exist only
        # to keep the real entries at their id's offset. A full, dense catalog
        # (ids 0..N) emits exactly one entry per id, as before.
        max_id = int(ordered_ids[-1])

        def _table(field):
            return "    .byte " + ", ".join(
                f"${self.sample_metadata[str(i)][field]:02X}" if str(i) in self.sample_metadata else "$00"
                for i in range(max_id + 1)
            )

        asm_lines.append("dpcm_bank_table:")
        asm_lines.append(_table('bank'))
        asm_lines.append("dpcm_pitch_table:")
        asm_lines.append(_table('pitch_reg'))
        asm_lines.append("dpcm_addr_table:")
        asm_lines.append(_table('address_reg'))
        asm_lines.append("dpcm_len_table:")
        asm_lines.append(_table('length_reg'))

        return "\n".join(asm_lines)