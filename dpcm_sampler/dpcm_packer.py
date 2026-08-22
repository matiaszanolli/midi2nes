import os
import math

class DpcmPacker:
    BANK_SIZE = 8192
    START_ADDR = 0xC000

    def __init__(self):
        self.banks = []
        self.sample_metadata = {}
        self.pending_samples = []

    @staticmethod
    def _length_reg(size_bytes: int) -> int:
        """The DMC engine's $4013 length register for a sample of this size.

        Reads `(length_reg*16)+1` bytes (docs/APU_DMC_REFERENCE.md §2/§4).
        Ceiling division (not floor) so every sample not exactly 16k+1 bytes
        still gets its full tail read -- flooring under-read up to 15
        trailing bytes (regression of #75, #295/DP-01).

        Floored at 1 rather than 0 for any real (packed) sample: $4013=0 is
        the *valid* encoding for a genuine 1-byte sample (reads 1 byte), but
        this codebase also uses length_reg==0 as the "never packed" sentinel
        in generate_assembly's positional lookup tables (an unrelated,
        separate mechanism -- see _table()). Without this floor, a real
        0- or 1-byte sample computed the same 0 and was silently
        indistinguishable from "not packed," so it could never trigger
        (#447/DPCM-2026-08-21-4). Reading a 1-byte sample's 17-byte tail is
        harmless zero-pad within its 64-byte-aligned block.
        """
        return max(1, (size_bytes + 14) // 16)

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

        # The block reserved for this sample must cover both its own bytes
        # AND the engine's (length_reg*16)+1 read -- a ceiling-rounded
        # length_reg can read 1 byte past a 64-byte-aligned size_bytes with
        # no gap to absorb it (the next sample starts immediately at the
        # next 64-byte boundary), silently pulling in the next sample's
        # first byte or, for a bank-ending sample, an arbitrary byte from
        # the fixed PRG bank (#446/DPCM-2026-08-21-3).
        read_length = self._length_reg(size_bytes) * 16 + 1
        aligned_size = max(
            math.ceil(size_bytes / 64) * 64,
            math.ceil(read_length / 64) * 64,
        )

        self.pending_samples.append({
            'id': sample_id,
            'path': file_path,
            'pitch': pitch_rate,
            'size': size_bytes,
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
        # See _length_reg for the (length_reg*16)+1 read-length formula and
        # the floor-at-1 rationale. size is already bounded to 4081 by the
        # truncate/raise guard in add_sample, so this can't exceed the
        # register's 8-bit range. add_sample sizes this sample's
        # aligned_size block to always cover the read this produces
        # (#446/DPCM-2026-08-21-3).
        dpcm_length_val = self._length_reg(sample['size'])
        dpcm_pitch_val = sample['pitch'] & 0x0F
        
        self.sample_metadata[sample['id']] = {
            "bank": bank_id,
            "address_reg": dpcm_address_val,
            "length_reg": dpcm_length_val,
            "pitch_reg": dpcm_pitch_val,
            "path": sample['path'],
            "incbin_size": sample.get('incbin_size')
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