from .base import BaseMapper


class MMC3Mapper(BaseMapper):
    """
    MMC3 Mapper implementation (iNES Mapper 004).
    Designed to support 512KB ROMs with large DPCM drum libraries.
    """

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
        return """
.segment "HEADER"
    .byte "NES", $1A
    .byte 32        ; 32 * 16KB = 512KB PRG
    .byte 0         ; 0 * 8KB CHR = CHR-RAM
    .byte $40       ; Mapper 4 (MMC3), horizontal mirroring
    .byte $00       ; NES 2.0 / Submapper / extended bits
    .byte $00, $00, $00, $00, $00, $00, $00, $00
"""

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
        for i in range(60):
            lines.append(f'    PRG_BANK_{i:02d}: start = $C000,  size = $2000, type = ro, file = %O, fill = yes, fillval = $FF;')

        # Last 4 banks mapped into CPU space on boot (Banks 60-63)
        lines.extend([
            '    PRG_80:  start = $8000,  size = $2000, type = ro, file = %O, fill = yes, fillval = $FF;',
            '    PRG_A0:  start = $A000,  size = $2000, type = ro, file = %O, fill = yes, fillval = $FF;',
            '    PRG_C0:  start = $C000,  size = $2000, type = ro, file = %O, fill = yes, fillval = $FF;',
            '    PRG_FIX: start = $E000,  size = $1FFA, type = ro, file = %O, fill = yes, fillval = $FF;',
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
        for i in range(60):
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