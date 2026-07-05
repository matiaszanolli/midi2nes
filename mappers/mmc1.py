"""
MMC1 Mapper Implementation (Mapper 1).

A versatile mapper with bank switching for larger ROMs.
PRG-ROM: Up to 256KB (we use 128KB)
CHR-ROM: Up to 128KB or CHR-RAM

Best for: Medium-sized music projects (30KB - 120KB)
"""

from typing import Dict, List, Optional

from .base import BaseMapper


class MMC1Mapper(BaseMapper):
    """
    MMC1 mapper implementation (iNES Mapper 1).

    - 128KB PRG-ROM with bank switching
    - 8 x 16KB switchable banks
    - Last bank ($C000-$FFFF) is fixed
    - Widely compatible with emulators and hardware
    """

    # 7 switchable 16KB banks (112KB) + 1 fixed 16KB bank = 128KB total.
    # Each switchable bank is declared as its own $8000-based MEMORY region
    # (like MMC3's PRG_BANK_NN) rather than one linear $1C000 region --
    # only ONE 16KB window is ever CPU-visible at $8000-$BFFF at a time, so a
    # single linear region let ld65 place data past the first 16KB at run
    # addresses >= $C000, aliasing the fixed engine/vectors bank at runtime
    # with no link error (#255/MAP-2026-07-05-1). CA65Exporter.export_direct_frames
    # bin-packs frame tables into these banks and bank-switches before each
    # read (direct_export_bank_size below).
    SWAP_BANK_COUNT = 7
    PRG_WINDOW_SIZE = 0x4000  # 16 KB switchable window

    @property
    def mapper_number(self) -> int:
        return 1

    @property
    def name(self) -> str:
        return "MMC1"

    @property
    def prg_rom_size(self) -> int:
        return 128 * 1024  # 128KB

    @property
    def prg_bank_size(self) -> int:
        return 16 * 1024  # 16KB banks

    def generate_header_asm(self) -> str:
        return """    .byte "NES", $1A      ; NES header identifier
    .byte $08             ; 8 x 16KB PRG ROM (128KB total) - MMC1
    .byte $00             ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $10             ; Mapper 1 (MMC1), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding"""

    def generate_linker_config(self) -> str:
        win = f'${self.PRG_WINDOW_SIZE:04X}'
        lines = [
            "MEMORY {",
            '    ZP:       start = $0000, size = $0100, type = rw, define = yes;',
            '    RAM:      start = $0300, size = $0500, type = rw, define = yes;',
            '    HEADER:   start = $0000, size = $0010, file = %O, fill = yes;',
            '',
            f'    # {self.SWAP_BANK_COUNT} switchable 16KB banks, each mapped at CPU',
            '    # $8000-$BFFF -- only one is active at a time (bank-switched via',
            '    # generate_bank_switch_code writing $E000).',
        ]
        for i in range(self.SWAP_BANK_COUNT):
            lines.append(
                f'    PRG_BANK_{i:02d}: start = $8000, size = {win}, '
                f'file = %O, fill = yes, fillval = $FF;')
        lines.extend([
            '',
            '    # Fixed bank (16KB) at end of ROM: engine code + vectors,',
            '    # always mapped at CPU address $C000-$FFFF.',
            '    PRGFIXED: start = $C000, size = $4000, file = %O, fill = yes, fillval = $FF;',
            '}',
            '',
            'SEGMENTS {',
            '    ZEROPAGE: load = ZP, type = zp;',
            '    BSS:      load = RAM, type = bss;',
            '    HEADER:   load = HEADER, type = ro;',
            '',
        ])
        for i in range(self.SWAP_BANK_COUNT):
            lines.append(
                f'    RODATA_BANK_{i:02d}: load = PRG_BANK_{i:02d}, type = ro, optional = yes;')
        lines.extend([
            '',
            '    # Plain RODATA still needs a home: the DPCM packer (and its',
            '    # project-builder stub fallback) emit `.segment "RODATA"`',
            '    # directly rather than going through the bank-packing this',
            '    # exporter does for frame tables, so it shares bank 0.',
            '    RODATA:   load = PRG_BANK_00, type = ro, optional = yes;',
            '',
            '    # Reset code and vectors in fixed bank (always at $C000-$FFFF)',
            '    CODE:     load = PRGFIXED, type = ro;',
            '    VECTORS:  load = PRGFIXED, type = ro, start = $FFFA;',
            '}',
        ])
        return "\n".join(lines)

    def generate_init_code(self) -> str:
        """Generate MMC1 initialization sequence."""
        return """    ; MMC1 initialization
    lda #$80
    sta $8000             ; Reset MMC1 state machine
    lda #$0C              ; Control: 16KB PRG mode, fixed high bank
    sta $8000
    lsr a
    sta $8000
    lsr a
    sta $8000
    lsr a
    sta $8000
    lsr a
    sta $8000             ; Write control register (5 writes)

    lda #$00              ; Select bank 0 for $8000-$BFFF
    sta $E000
    lsr a
    sta $E000
    lsr a
    sta $E000
    lsr a
    sta $E000
    lsr a
    sta $E000             ; Write bank register (5 writes)"""

    def generate_bank_switch_code(self, bank: int) -> str:
        """Generate code to switch to specified bank at $8000-$BFFF."""
        return f"""    ; Switch to bank {bank}
    lda #${bank:02X}
    sta $E000
    lsr a
    sta $E000
    lsr a
    sta $E000
    lsr a
    sta $E000
    lsr a
    sta $E000"""

    # No post-link vector fixup: generate_linker_config's `VECTORS: load =
    # PRGFIXED, start = $FFFA` already tells ld65 to place the vectors at CPU
    # address $FFFA within PRGFIXED, which resolves to file offset 0x2000A —
    # ld65 gets this right unassisted. A previous fixup step copied 6 bytes
    # from file offset 0xFFFA (which falls inside the switchable PRGSWAP
    # region, not the vectors) onto the correctly-placed vectors at 0x2000A,
    # overwriting valid reset/NMI/IRQ addresses with PRGSWAP fill data and
    # bricking every MMC1 ROM built via build.sh (#213). Falls back to
    # BaseMapper.generate_post_process_commands (no-op).

    def get_data_capacity(self) -> int:
        # 112KB in switchable banks, minus overhead
        return 112 * 1024

    def direct_export_bank_size(self) -> Optional[int]:
        # Only PRG_WINDOW_SIZE bytes of the switchable pool are CPU-visible
        # at once (#255/MAP-2026-07-05-1) -- see the class-level comment.
        return self.PRG_WINDOW_SIZE

    def validate_segment_sizes(self, segment_sizes: Dict[str, int]) -> List[str]:
        """Size each bank's combined segments against the 16KB switchable
        window (#255/MAP-2026-07-05-1), mirroring MMC3's per-bank check.

        CA65Exporter.export_direct_frames already refuses to emit a single
        table larger than one bank, so this is a defense-in-depth backstop
        (e.g. against hand-edited music.asm) rather than the primary guard.
        Plain `RODATA` (emitted by the DPCM packer/stub, which doesn't go
        through the exporter's bank-packing) shares bank 0 with
        RODATA_BANK_00, matching generate_linker_config -- so the two are
        summed together the same way MMC3 sums BANK_NN + DPCM_NN sharing a
        physical bank. Any other segment name falls through to the flat
        aggregate check.
        """
        errors: List[str] = []
        bank_totals: Dict[int, Dict[str, int]] = {}
        flat_total = 0
        for seg, size in segment_sizes.items():
            if seg == 'RODATA':
                bank_totals.setdefault(0, {})[seg] = size
                flat_total += size
            elif seg and seg.startswith('RODATA_BANK_'):
                try:
                    bank_idx = int(seg.rsplit('_', 1)[1])
                except (IndexError, ValueError):
                    flat_total += size
                    continue
                if bank_idx >= self.SWAP_BANK_COUNT:
                    errors.append(
                        f"music data needs bank {bank_idx}, but MMC1 defines only "
                        f"{self.SWAP_BANK_COUNT} switchable banks "
                        f"(RODATA_BANK_00..{self.SWAP_BANK_COUNT - 1})."
                    )
                bank_totals.setdefault(bank_idx, {})[seg] = size
                flat_total += size
            else:
                flat_total += size

        for bank_idx in sorted(bank_totals):
            contributors = bank_totals[bank_idx]
            combined = sum(contributors.values())
            if combined <= self.PRG_WINDOW_SIZE:
                continue
            if len(contributors) == 1:
                (seg, size), = contributors.items()
                errors.append(f"segment {seg} ({size:,} bytes) exceeds the "
                              f"{self.PRG_WINDOW_SIZE:,}-byte MMC1 switchable window.")
            else:
                detail = " + ".join(f"{size:,} bytes {seg}"
                                     for seg, size in sorted(contributors.items()))
                errors.append(
                    f"bank {bank_idx}: {detail} = {combined:,} bytes exceeds the shared "
                    f"{self.PRG_WINDOW_SIZE:,}-byte MMC1 switchable window."
                )

        if flat_total > self.get_data_capacity():
            errors.append(
                f"music data ({flat_total:,} bytes) exceeds {self.name} capacity "
                f"({self.get_data_capacity():,} bytes)"
            )
        return errors
