from typing import Dict, List

from .base import BaseMapper


class MMC3Mapper(BaseMapper):
    """
    MMC3 Mapper implementation (iNES Mapper 004).
    Designed to support 512KB ROMs with large DPCM drum libraries.
    """

    # PRG layout constants — the single source of truth for both the linker
    # config emitted by generate_linker_config and the capacity pre-flight in
    # validate_segment_sizes, so the two cannot drift (#126, #127).
    SWAP_BANK_COUNT = 60          # PRG_BANK_00..59, shared by BANK_NN and DPCM_NN
    PRG_WINDOW_SIZE = 0x2000      # 8 KB swap/window bank ($2000)
    PRG_FIX_SIZE = 0x1FFA         # $E000-$FFF9 fixed bank (engine + direct tables + CODE)
    # Conservative slice of the fixed bank the audio engine itself occupies, so
    # the direct-export table budget is approximate (ld65 is the exact backstop).
    FIXED_BANK_ENGINE_RESERVE = 2048

    @property
    def mapper_number(self) -> int:
        return 4

    @property
    def name(self) -> str:
        return "MMC3"

    @property
    def prg_rom_size(self) -> int:
        return 512 * 1024  # 512KB PRG-ROM

    @property
    def prg_bank_size(self) -> int:
        return 8 * 1024  # MMC3 uses 8KB banks

    def generate_header_asm(self) -> str:
        # Bare iNES header bytes only — the caller (project builder / CA65
        # exporter) owns the single `.segment "HEADER"`. Mirrors the NROM/MMC1
        # contract; emitting our own .segment here double-declared the builder's
        # segment (#22).
        return """    .byte "NES", $1A
    .byte 32        ; 32 * 16KB = 512KB PRG
    .byte 0         ; 0 * 8KB CHR = CHR-RAM
    .byte $40       ; Mapper 4 (MMC3), horizontal mirroring
    .byte $00       ; NES 2.0 / Submapper / extended bits
    .byte $00, $00, $00, $00, $00, $00, $00, $00"""

    def generate_linker_config(self) -> str:
        lines = [
            "MEMORY {",
            '    ZP:      start = $00,    size = $0100, type = rw, file = "";',
            '    OAM:     start = $0200,  size = $0100, type = rw, file = "";',
            '    RAM:     start = $0300,  size = $0500, type = rw, file = "";',
            '    HDR:     start = $0000,  size = $0010, type = ro, file = %O, fill = yes, fillval = $00;'
        ]

        # Generate Banks 0-59 (DPCM and Padding)
        # All mapped to $C000 so their addresses resolve correctly for the APU!
        win = f'${self.PRG_WINDOW_SIZE:04X}'
        for i in range(self.SWAP_BANK_COUNT):
            lines.append(f'    PRG_BANK_{i:02d}: start = $C000,  size = {win}, type = ro, file = %O, fill = yes, fillval = $FF;')

        # Last 4 banks mapped into CPU space on boot (Banks 60-63)
        lines.extend([
            f'    PRG_80:  start = $8000,  size = {win}, type = ro, file = %O, fill = yes, fillval = $FF;',
            f'    PRG_A0:  start = $A000,  size = {win}, type = ro, file = %O, fill = yes, fillval = $FF;',
            f'    PRG_C0:  start = $C000,  size = {win}, type = ro, file = %O, fill = yes, fillval = $FF;',
            f'    PRG_FIX: start = $E000,  size = ${self.PRG_FIX_SIZE:04X}, type = ro, file = %O, fill = yes, fillval = $FF;',
            '    VECTORS: start = $FFFA,  size = $0006, type = ro, file = %O, fill = yes;',
            '}',
            '',
            'SEGMENTS {',
            '    HEADER:   load = HDR, type = ro;',
            '    ZEROPAGE: load = ZP,  type = zp;',
            '    BSS:      load = RAM, type = bss, define = yes;',
            '    OAM:      load = OAM, type = bss, align = $100;',
            # Lookup/macro/instrument tables are read with absolute addressing by
            # the engine, so they must live in an always-mapped bank. In PRG mode 1
            # the $8000-$9FFF window is the fixed second-to-last bank.
            '    CODE_8000: load = PRG_80, type = ro, optional = yes;'
        ])

        # Generate DPCM + sequence-bank segments for Banks 0-59.
        # BANK_NN holds the per-channel sequence bytecode; fetch_sequence_byte
        # swaps the bank into the $A000 (R7) window and translates the pointer,
        # so a BANK_NN linked into PRG_BANK_NN (PRG-pool bank N) resolves correctly.
        for i in range(self.SWAP_BANK_COUNT):
            lines.append(f'    DPCM_{i:02d}:   load = PRG_BANK_{i:02d}, type = ro, optional = yes;')
            lines.append(f'    BANK_{i:02d}:   load = PRG_BANK_{i:02d}, type = ro, optional = yes;')

        lines.extend([
            '    CODE:     load = PRG_FIX, type = ro;',
            '    RODATA:   load = PRG_FIX, type = ro;',
            '    DPCM:     load = PRG_C0,  type = ro, optional = yes;',
            '    VECTORS:  load = VECTORS, type = ro;',
            '}'
        ])

        return "\n".join(lines)

    def generate_init_code(self) -> str:
        return """
    ; MMC3 Init for Audio Engine (PRG Mode 1)
    sta $E000       ; Disable MMC3 IRQs

    ; Configure PRG Bank Mode 1 (Bit 6 = 1) and select R6
    lda #$46
    sta $8000

    ; Initialize DPCM window ($C000-$DFFF) to Bank 0
    lda #$00
    sta $8001

    ; Select R7 to set up pattern data window ($A000-$BFFF)
    lda #$47
    sta $8000

    ; Initialize Pattern window to Bank 1
    lda #$01
    sta $8001
"""

    def generate_bank_switch_code(self, bank: int) -> str:
        return """
; ------------------------------------------------------------------
; switch_dpcm_bank
; Swaps the DPCM sample window at $C000-$DFFF
; Expects target bank in A
; ------------------------------------------------------------------
switch_dpcm_bank:
    pha
    ; Select R6 (DPCM Window), preserve Mode 1
    lda #$46
    sta $8000
    ; Write new bank number
    pla
    sta $8001
    rts
"""

    def generate_build_script(self, is_windows: bool = False) -> str:
        """MMC3 builds with debug symbols (-g) and fails fast on toolchain errors.

        MMC3 needs no vector fixup (the fixed last bank already holds the
        vectors at $E000-$FFFF), so there is no post-process step.
        """
        if is_windows:
            return (
                "@echo off\n"
                "echo Compiling MMC3 Audio Engine...\n"
                "ca65 main.asm -g -o main.o\n"
                "if %errorlevel% neq 0 exit /b %errorlevel%\n"
                "ca65 music.asm -g -o music.o\n"
                "if %errorlevel% neq 0 exit /b %errorlevel%\n"
                "ld65 -C nes.cfg -o game.nes main.o music.o\n"
                "if %errorlevel% neq 0 exit /b %errorlevel%\n"
                "echo Done!\n"
            )
        return (
            "#!/bin/bash\n"
            "set -e\n"
            "echo \"Compiling MMC3 Audio Engine...\"\n"
            "ca65 main.asm -g -o main.o\n"
            "ca65 music.asm -g -o music.o\n"
            "ld65 -C nes.cfg -o game.nes main.o music.o\n"
            "echo \"Done!\"\n"
        )

    def validate_segment_sizes(self, segment_sizes: Dict[str, int]) -> List[str]:
        """Size each music.asm segment against the MMC3 region it loads into.

        Unlike the flat base check, MMC3 spreads data across distinct regions
        (see generate_linker_config): the direct-export frame tables (RODATA) and
        any music CODE share the 8 KB fixed bank PRG_FIX; the instrument/macro
        tables live in the fixed $8000 window (CODE_8000 -> PRG_80); and the
        sequence bytecode (BANK_NN) and DPCM (DPCM_NN) share the 60-bank swap
        pool. A single 510 KB ceiling is only meaningful for the banked path, so
        checking the total (the old behavior) let an oversized direct export
        through to a raw ld65 PRG_FIX overflow (#126).
        """
        errors: List[str] = []

        # PRG_FIX holds the engine plus the direct tables (RODATA) and music CODE.
        fixed_budget = self.PRG_FIX_SIZE - self.FIXED_BANK_ENGINE_RESERVE
        fixed_used = segment_sizes.get('RODATA', 0) + segment_sizes.get('CODE', 0)
        if fixed_used > fixed_budget:
            errors.append(
                f"fixed-bank data ({fixed_used:,} bytes of CODE+RODATA) exceeds the MMC3 "
                f"PRG_FIX budget (~{fixed_budget:,} bytes). The direct (--no-patterns) export "
                f"packs frame tables into the 8 KB fixed bank — enable pattern compression or "
                f"shorten the song."
            )

        code_8000 = segment_sizes.get('CODE_8000', 0)
        if code_8000 > self.PRG_WINDOW_SIZE:
            errors.append(
                f"instrument/macro tables (CODE_8000, {code_8000:,} bytes) exceed the MMC3 "
                f"$8000 window ({self.PRG_WINDOW_SIZE:,} bytes)."
            )

        # BANK_NN (sequence bytecode) and DPCM_NN both load into the PRG_BANK pool.
        max_bank = -1
        for seg, size in segment_sizes.items():
            if not seg or not (seg.startswith('BANK_') or seg.startswith('DPCM_')):
                continue
            if size > self.PRG_WINDOW_SIZE:
                errors.append(f"segment {seg} ({size:,} bytes) exceeds the 8 KB bank size "
                              f"({self.PRG_WINDOW_SIZE:,} bytes).")
            try:
                max_bank = max(max_bank, int(seg.rsplit('_', 1)[1]))
            except (IndexError, ValueError):
                pass
        if max_bank >= self.SWAP_BANK_COUNT:
            errors.append(
                f"music data needs bank {max_bank}, but MMC3 defines only {self.SWAP_BANK_COUNT} "
                f"swap banks (BANK_00..{self.SWAP_BANK_COUNT - 1}). The sequence/DPCM data is too "
                f"large for MMC3."
            )

        return errors