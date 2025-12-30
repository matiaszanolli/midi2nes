"""
MMC3 Mapper Implementation (Mapper 4).

A powerful mapper with fine-grained bank switching.
PRG-ROM: Up to 512KB
CHR-ROM: Up to 256KB or CHR-RAM

Best for: Large music projects (120KB+)
"""

from .base import BaseMapper


class MMC3Mapper(BaseMapper):
    """
    MMC3 mapper implementation (iNES Mapper 4).

    - 512KB PRG-ROM with bank switching
    - 32 x 16KB banks (or 64 x 8KB banks)
    - Scanline counter for advanced features
    - Maximum capacity for large music collections
    """

    @property
    def mapper_number(self) -> int:
        return 4

    @property
    def name(self) -> str:
        return "MMC3"

    @property
    def prg_rom_size(self) -> int:
        return 512 * 1024  # 512KB

    @property
    def prg_bank_size(self) -> int:
        return 8 * 1024  # 8KB banks (MMC3 uses 8KB PRG banks)

    def generate_header_asm(self) -> str:
        return """    .byte "NES", $1A      ; NES header identifier
    .byte $20             ; 32 x 16KB PRG ROM (512KB total) - MMC3
    .byte $00             ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $40             ; Mapper 4 (MMC3), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding"""

    def generate_linker_config(self) -> str:
        return """MEMORY {
    ZP:       start = $0000, size = $0100, type = rw, define = yes;
    RAM:      start = $0300, size = $0500, type = rw, define = yes;
    HEADER:   start = $0000, size = $0010, file = %O, fill = yes;

    # Switchable banks (480KB total)
    # Banks 0-59 at $8000-$9FFF and $A000-$BFFF (switchable)
    PRGSWAP:  start = $8000, size = $78000, file = %O, fill = yes, fillval = $FF;

    # Fixed banks (32KB) at end of ROM
    # $C000-$DFFF: second-to-last 8KB bank
    # $E000-$FFFF: last 8KB bank (fixed)
    PRGFIXED: start = $C000, size = $8000, file = %O, fill = yes, fillval = $FF;
}

SEGMENTS {
    ZEROPAGE: load = ZP, type = zp;
    BSS:      load = RAM, type = bss;
    HEADER:   load = HEADER, type = ro;

    # Music data in switchable banks
    RODATA:   load = PRGSWAP, type = ro;

    # Reset code and vectors in fixed bank
    CODE:     load = PRGFIXED, type = ro;
    VECTORS:  load = PRGFIXED, type = ro, start = $FFFA;
}"""

    def generate_init_code(self) -> str:
        """Generate MMC3 initialization sequence."""
        return """    ; MMC3 initialization
    ; Bank mode: $8000-$9FFF swappable, $C000-$DFFF fixed
    lda #$00
    sta $8000             ; Bank select register (R0)
    lda #$00
    sta $8001             ; Bank 0 at $8000-$9FFF

    lda #$01
    sta $8000             ; Bank select register (R1)
    lda #$02
    sta $8001             ; Bank 2 at $A000-$BFFF

    ; Disable IRQ
    sta $E000             ; Disable scanline counter

    ; Enable PRG-RAM if present
    lda #$80
    sta $A001"""

    def generate_bank_switch_code(self, bank: int) -> str:
        """Generate code to switch bank at $8000-$9FFF."""
        return f"""    ; Switch to bank {bank} at $8000-$9FFF
    lda #$06              ; Bank select R6 ($8000-$9FFF)
    sta $8000
    lda #${bank:02X}
    sta $8001"""

    def generate_post_process_commands(self, is_windows: bool = False) -> str:
        """MMC3 needs vector table fixup for 512KB ROM."""
        python_cmd = "python" if is_windows else "python3"
        # Fix vectors: copy to correct position in 512KB ROM
        # Vectors should be at end of last 8KB bank
        return f'{python_cmd} -c "import sys; d=open(\'game.nes\',\'r+b\'); d.seek(0xFFFA); v=d.read(6); d.seek(0x8000A); d.write(v); d.close()"\n'

    def get_data_capacity(self) -> int:
        # 480KB in switchable banks
        return 480 * 1024
