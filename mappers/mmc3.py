from .base import BaseMapper


class Mmc3Mapper(BaseMapper):
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
        return """
MEMORY {
    ZP:      start = $00,    size = $0100, type = rw, file = "";
    OAM:     start = $0200,  size = $0100, type = rw, file = "";
    RAM:     start = $0300,  size = $0500, type = rw, file = "";
    HDR:     start = $0000,  size = $0010, type = ro, file = %O, fill = yes, fillval = $00;
    
    # Pad 60 unused 8KB banks to achieve 512KB (Banks 0-59)
    PRG_PAD: start = $8000,  size = $78000, type = ro, file = %O, fill = yes, fillval = $FF;
    
    # Last 4 banks mapped into CPU space on boot (Banks 60-63)
    PRG_80:  start = $8000,  size = $2000, type = ro, file = %O, fill = yes, fillval = $FF;
    PRG_A0:  start = $A000,  size = $2000, type = ro, file = %O, fill = yes, fillval = $FF;
    PRG_C0:  start = $C000,  size = $2000, type = ro, file = %O, fill = yes, fillval = $FF;
    PRG_FIX: start = $E000,  size = $1FFA, type = ro, file = %O, fill = yes, fillval = $FF;
    VECTORS: start = $FFFA,  size = $0006, type = ro, file = %O, fill = yes;
}

SEGMENTS {
    HEADER:   load = HDR, type = ro;
    ZEROPAGE: load = ZP,  type = zp;
    BSS:      load = RAM, type = bss, define = yes;
    OAM:      load = OAM, type = bss, align = $100;
    CODE:     load = PRG_FIX, type = ro;
    RODATA:   load = PRG_FIX, type = ro;
    DPCM:     load = PRG_C0,  type = ro, optional = yes;
    VECTORS:  load = VECTORS, type = ro;
}
"""

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