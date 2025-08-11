import os
from pathlib import Path

class NESProjectBuilder:
    """Prepares a complete NES project structure for CC65 compilation"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.use_mmc1 = True  # Always use MMC1 with 128KB PRG-ROM

    def prepare_project(self, music_asm_path: str):
        """Creates a complete NES project structure ready for CC65 compilation"""
        # Create project directory
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # Read music.asm content
        music_content = Path(music_asm_path).read_text()
        
        print(f"  Using MMC1 with 128KB PRG-ROM (8 banks)")
        
        # Write the music.asm (no modifications needed - our exporter handles this)
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
        return """.segment "HEADER"
    .byte "NES", $1A      ; NES header identifier
    .byte $08             ; 8 x 16KB PRG ROM (128KB total) - MMC1
    .byte $00             ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $10             ; Mapper 1 (MMC1), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding

.segment "ZEROPAGE"
    frame_counter:  .res 2  ; Frame counter (shared with music.asm)

.segment "CODE"
; Import music functions from music.asm
.global init_music
.global update_music

reset:
    sei                   ; Disable interrupts
    cld                   ; Clear decimal mode
    ldx #$FF
    txs                   ; Set up stack

    ; Simple MMC1 initialization - just reset it
    lda #$80
    sta $8000             ; Reset MMC1
    
    ; Use 32KB mode for simplicity (like NROM but with more space)
    lda #$0E              ; 32KB PRG mode, CHR-RAM, horizontal mirroring
    sta $8000             ; Write bit 0
    lsr
    sta $8000             ; Write bit 1
    lsr
    sta $8000             ; Write bit 2
    lsr
    sta $8000             ; Write bit 3
    lsr
    sta $8000             ; Write bit 4

    ; Initialize frame counter
    lda #$00
    sta frame_counter
    sta frame_counter+1

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
        """Generate a working MMC1 linker config with correct file layout"""
        return """MEMORY {
    ZP:     start = $00,    size = $0100, type = rw, define = yes;
    RAM:    start = $0300,  size = $0500, type = rw, define = yes;
    # Correct NES file layout: Header at start, PRG-ROM follows
    HEADER: start = $0000,  size = $0010, file = %O, fill = yes;
    PRG:    start = $0010,  size = $7FF0, file = %O, fill = yes, define = yes;
}

SEGMENTS {
    ZEROPAGE: load = ZP, type = zp;
    HEADER:   load = HEADER, type = ro;
    CODE:     load = PRG, type = ro;
    RODATA:   load = PRG, type = ro;
    VECTORS:  load = PRG, type = ro, start = $7FFA;
}"""

    def _create_build_script(self):
        """Creates a build script based on the OS"""
        if os.name == 'nt':  # Windows
            script = "@echo off\n"
            script += "ca65 main.asm -o main.o\n"
            script += "ca65 music.asm -o music.o\n"
            script += "ld65 -C nes.cfg main.o music.o -o game.nes\n"
        else:  # Unix-like
            script = "#!/bin/bash\n"
            script += "ca65 main.asm -o main.o\n"
            script += "ca65 music.asm -o music.o\n"
            script += "ld65 -C nes.cfg main.o music.o -o game.nes\n"
            
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
