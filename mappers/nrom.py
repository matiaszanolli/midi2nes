"""
NROM Mapper Implementation (Mapper 0).

The simplest NES mapper with no bank switching.
PRG-ROM: 32KB (fixed)
CHR-ROM: 8KB or CHR-RAM

Best for: Small music projects under 30KB
"""

from .base import BaseMapper


class NROMMapper(BaseMapper):
    """
    NROM mapper implementation (iNES Mapper 0).

    - 32KB PRG-ROM, no bank switching
    - Simple and reliable
    - Good for small projects
    """

    @property
    def mapper_number(self) -> int:
        return 0

    @property
    def name(self) -> str:
        return "NROM"

    @property
    def prg_rom_size(self) -> int:
        return 32 * 1024  # 32KB

    @property
    def prg_bank_size(self) -> int:
        return 16 * 1024  # 16KB banks

    def generate_header_asm(self) -> str:
        return """    .byte "NES", $1A      ; NES header identifier
    .byte $02             ; 2 x 16KB PRG ROM (32KB total) - NROM
    .byte $00             ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $00             ; Mapper 0 (NROM), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding"""

    def generate_linker_config(self) -> str:
        return """MEMORY {
    ZP:       start = $0000, size = $0100, type = rw, define = yes;
    RAM:      start = $0300, size = $0500, type = rw, define = yes;
    HEADER:   start = $0000, size = $0010, file = %O, fill = yes;
    PRG:      start = $8000, size = $8000, file = %O, fill = yes, fillval = $FF;
}

SEGMENTS {
    ZEROPAGE: load = ZP, type = zp;
    BSS:      load = RAM, type = bss;
    HEADER:   load = HEADER, type = ro;
    CODE:     load = PRG, type = ro;
    RODATA:   load = PRG, type = ro;
    VECTORS:  load = PRG, type = ro, start = $FFFA;
}"""

    def generate_init_code(self) -> str:
        """NROM requires no special initialization."""
        return """    ; NROM mapper - no initialization needed"""

    def get_data_capacity(self) -> int:
        # NROM has less room due to shared code/data space
        return 30 * 1024  # ~30KB for music data
