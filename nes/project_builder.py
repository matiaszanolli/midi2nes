import os
from pathlib import Path

class NESProjectBuilder:
    """Prepares a complete NES project structure for CC65 compilation"""

    def __init__(self, project_path: str, debug_mode: bool = False):
        """Initialize NES project builder.

        Args:
            project_path: Directory to create project in
            debug_mode: If True, enables on-screen debug overlay
        """
        self.project_path = Path(project_path)
        self.use_mmc1 = True  # Use MMC1 for larger ROM capacity
        self.debug_mode = debug_mode

    def prepare_project(self, music_asm_path: str):
        """Creates a complete NES project structure ready for CC65 compilation"""
        # Create project directory
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Read music.asm content
        music_content = Path(music_asm_path).read_text()

        mapper_name = "MMC1 with 128KB PRG-ROM" if self.use_mmc1 else "NROM with 32KB PRG-ROM"
        print(f"  Using {mapper_name}")

        if self.debug_mode:
            print(f"  🐛 Debug mode enabled - adding on-screen diagnostics")
            # Add debug overlay to music.asm
            from nes.debug_overlay import NESDebugOverlay
            overlay = NESDebugOverlay(enable_overlay=True)
            music_content += "\n" + overlay.generate_full_debug_system()

        # Write the music.asm
        (self.project_path / "music.asm").write_text(music_content)

        # Create FIXED main.asm with NMI timing like our working debug ROM
        main_asm = self._generate_working_main_asm()
        (self.project_path / "main.asm").write_text(main_asm)

        # Create FIXED nes.cfg (simpler, working MMC1 config)
        linker_config = self._generate_working_linker_config()
        (self.project_path / "nes.cfg").write_text(linker_config)

        # Create build script
        self._create_build_script()

        return True

    def _generate_working_main_asm(self) -> str:
        """Generate main.asm that works - uses NMI timing like debug_fixed.nes"""

        # Add debug function imports if in debug mode
        debug_imports = ""
        debug_init_call = ""
        debug_update_call = ""

        if self.debug_mode:
            debug_imports = """; Import debug functions
.global debug_init
.global debug_update
.global debug_test_apu
"""
            debug_init_call = """
    ; Initialize debug overlay
    jsr debug_init

    ; Test APU initialization
    jsr debug_test_apu
"""
            debug_update_call = """
    ; Update debug overlay
    jsr debug_update
"""

        # Generate header based on mapper choice
        if self.use_mmc1:
            header = """    .byte "NES", $1A      ; NES header identifier
    .byte $08             ; 8 x 16KB PRG ROM (128KB total) - MMC1
    .byte $00             ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $10             ; Mapper 1 (MMC1), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding"""
        else:
            header = """    .byte "NES", $1A      ; NES header identifier
    .byte $02             ; 2 x 16KB PRG ROM (32KB total) - NROM
    .byte $00             ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $00             ; Mapper 0 (NROM), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding"""

        return f""".segment "HEADER"
{header}

.segment "ZEROPAGE"
    ; Export zeropage variables for music.asm
    ptr1:          .res 2  ; General purpose pointer
    temp1:         .res 1  ; Temporary variable
    temp2:         .res 1  ; Temporary variable
    temp_ptr:      .res 2  ; Temporary pointer for table lookups
    frame_counter: .res 2  ; Frame counter (shared with music.asm)
.exportzp ptr1, temp1, temp2, temp_ptr, frame_counter

.segment "CODE"
; Import music functions from music.asm
.global init_music
.global update_music
{debug_imports}

reset:
    sei                   ; Disable interrupts
    cld                   ; Clear decimal mode
    ldx #$FF
    txs                   ; Set up stack

    ; MMC1 initialization
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
    sta $E000             ; Write bank register (5 writes)

    ; Initialize frame counter
    lda #$00
    sta frame_counter
    sta frame_counter+1
{debug_init_call}
    ; Initialize APU and music
    jsr init_music

    ; CRITICAL: Enable NMI for 60Hz timing (like our working debug ROM)
    lda #$80
    sta $2000          ; Enable NMI, this makes music timing work!

mainloop:
    ; Just wait for NMI to handle timing (like debug ROM)
    jmp mainloop

nmi:
    ; NMI handler - called 60 times per second
    pha                   ; Save registers
    txa
    pha
    tya
    pha

    ; Update music - this calls our working frame-based music code
    jsr update_music
{debug_update_call}
    ; Restore registers and return
    pla
    tay
    pla
    tax
    pla
    rti

irq:
    rti

.segment "VECTORS"
    .word nmi            ; NMI vector - CRITICAL for music timing!
    .word reset          ; Reset vector
    .word irq            ; IRQ vector
"""

    def _generate_working_linker_config(self) -> str:
        """Generate a working linker config for NROM (32KB) or MMC1 (128KB)"""
        if self.use_mmc1:
            # MMC1 configuration: use separate memory regions for switchable and fixed banks
            # This ensures CODE ends up at the END of the file (bank 7)
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
        else:
            # NROM configuration (simple, 32KB)
            return """MEMORY {
    ZP:       start = $0000, size = $0100, type = rw, define = yes;
    RAM:      start = $0300, size = $0500, type = rw, define = yes;
    HEADER:   start = $0000, size = $0010, file = %O, fill = yes;
    PRG:      start = $0010, size = $8000, file = %O, fill = yes, fillval = $FF;
}

SEGMENTS {
    ZEROPAGE: load = ZP, type = zp;
    BSS:      load = RAM, type = bss;
    HEADER:   load = HEADER, type = ro;
    CODE:     load = PRG, type = ro, start = $8000;
    RODATA:   load = PRG, type = ro;
    VECTORS:  load = PRG, type = ro, start = $FFFA;
}"""

    def _create_build_script(self):
        """Creates a build script based on the OS"""
        if os.name == 'nt':  # Windows
            script = "@echo off\n"
            script += "ca65 main.asm -o main.o\n"
            script += "ca65 music.asm -o music.o\n"
            script += "ld65 -C nes.cfg main.o music.o -o game.nes\n"
            if self.use_mmc1:
                # Fix vectors for MMC1: copy from 0xFFFA to 0x2000A (last 6 bytes of bank 7)
                script += "python -c \"import sys; d=open('game.nes','r+b'); d.seek(0xFFFA); v=d.read(6); d.seek(0x2000A); d.write(v); d.close()\"\n"
        else:  # Unix-like
            script = "#!/bin/bash\n"
            script += "ca65 main.asm -o main.o\n"
            script += "ca65 music.asm -o music.o\n"
            script += "ld65 -C nes.cfg main.o music.o -o game.nes\n"
            if self.use_mmc1:
                # Fix vectors for MMC1: copy from 0xFFFA to 0x2000A (last 6 bytes of bank 7)
                script += "python3 -c \"import sys; d=open('game.nes','r+b'); d.seek(0xFFFA); v=d.read(6); d.seek(0x2000A); d.write(v); d.close()\"\n"
            
        script_name = "build.bat" if os.name == 'nt' else "build.sh"
        script_path = self.project_path / script_name
        script_path.write_text(script)
        
        if os.name != 'nt':
            # Make the script executable on Unix-like systems
            script_path.chmod(script_path.stat().st_mode | 0o755)

    # Legacy methods for compatibility
    def prepare_multi_song_project(self, music_asm_path: str, segments_data: dict):
        """Fallback to simple project preparation"""
        return self.prepare_project(music_asm_path)
    
    def add_song_bank(self, song_bank):
        """Legacy compatibility"""
        return True
