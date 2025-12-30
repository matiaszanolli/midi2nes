"""
MMC1 Mapper Implementation (Mapper 1).

A versatile mapper with bank switching for larger ROMs.
PRG-ROM: Up to 256KB (we use 128KB)
CHR-ROM: Up to 128KB or CHR-RAM

Best for: Medium-sized music projects (30KB - 120KB)
"""

from .base import BaseMapper


class MMC1Mapper(BaseMapper):
    """
    MMC1 mapper implementation (iNES Mapper 1).

    - 128KB PRG-ROM with bank switching
    - 8 x 16KB switchable banks
    - Last bank ($C000-$FFFF) is fixed
    - Widely compatible with emulators and hardware
    """

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
        return """MEMORY {
    ZP:       start = $0000, size = $0100, type = rw, define = yes;
    RAM:      start = $0300, size = $0500, type = rw, define = yes;
    HEADER:   start = $0000, size = $0010, file = %O, fill = yes;

    # Switchable banks 0-6 (112KB total)
    # These will be at file offsets $0010 - $1C00F
    PRGSWAP:  start = $8000, size = $1C000, file = %O, fill = yes, fillval = $FF;

    # Fixed bank 7 (16KB) at end of ROM
    # File offset $1C010 - $2000F, CPU address $C000 - $FFFF
    PRGFIXED: start = $C000, size = $4000, file = %O, fill = yes, fillval = $FF;
}

SEGMENTS {
    ZEROPAGE: load = ZP, type = zp;
    BSS:      load = RAM, type = bss;
    HEADER:   load = HEADER, type = ro;

    # Music data in switchable banks (accessible at $8000-$BFFF)
    RODATA:   load = PRGSWAP, type = ro;

    # Reset code and vectors in fixed bank (always at $C000-$FFFF)
    CODE:     load = PRGFIXED, type = ro;
    VECTORS:  load = PRGFIXED, type = ro, start = $FFFA;
}"""

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

    def generate_post_process_commands(self, is_windows: bool = False) -> str:
        """MMC1 needs vector table fixup for 128KB ROM."""
        python_cmd = "python" if is_windows else "python3"
        # Fix vectors: copy from linker output position to correct MMC1 position
        return f'{python_cmd} -c "import sys; d=open(\'game.nes\',\'r+b\'); d.seek(0xFFFA); v=d.read(6); d.seek(0x2000A); d.write(v); d.close()"\n'

    def get_data_capacity(self) -> int:
        # 112KB in switchable banks, minus overhead
        return 112 * 1024
