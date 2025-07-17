import os
from pathlib import Path

class NESProjectBuilder:
    """Prepares a complete NES project structure for CC65 compilation"""
    
    NES_HEADER = """; NES Header
.segment "HEADER"
.byte "NES", $1A      ; iNES header identifier
.byte 2               ; 2x 16KB PRG-ROM banks
.byte 1               ; 1x 8KB CHR-ROM bank
.byte $01, $00        ; Mapper 0, vertical mirroring
.byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding
"""

    LINKER_CONFIG = """MEMORY {
    # NES has 2KB of RAM
    ZP:     start = $00,    size = $0100, type = rw, file = "";
    RAM:    start = $0200,  size = $0600, type = rw, file = "";
    
    # NES ROM layout
    HEADER: start = $0000,  size = $0010, type = ro, file = %O, fill = yes;
    PRG:    start = $8000,  size = $8000, type = ro, file = %O, fill = yes;
    
    # 6502 vectors at end of ROM
    VECTORS: start = $FFFA, size = $0006, type = ro, file = %O, fill = yes;
}

SEGMENTS {
    HEADER:   load = HEADER,  type = ro;
    ZEROPAGE: load = ZP,      type = zp;
    BSS:      load = RAM,     type = bss, define = yes;
    CODE:     load = PRG,     type = ro;
    RODATA:   load = PRG,     type = ro;
    VECTORS:  load = VECTORS, type = ro;
}"""

    MAIN_ASM = """.segment "HEADER"
    .byte "NES", $1A      ; NES header identifier
    .byte $01             ; 1 x 16KB PRG ROM
    .byte $00             ; 0 x 8KB CHR ROM
    .byte $00             ; Mapper 0, horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00, $00  ; Padding

.segment "ZEROPAGE"
    ; Zero page variables here

.segment "CODE"
    .include "music.asm"

reset:
    sei                   ; Disable interrupts
    cld                   ; Clear decimal mode
    ldx #$FF
    txs                   ; Set up stack

    ; Initialize APU
    jsr init_music

mainloop:
    jsr update_music
    jmp mainloop

nmi:
    rti

irq:
    rti

.segment "VECTORS"
    .word nmi            ; NMI vector
    .word reset         ; Reset vector
    .word irq           ; IRQ vector
"""

    EMPTY_CHANNEL_DATA = """
; Empty channel data for unused channels
.segment "RODATA"
pulse1_frames:  .byte $00, $00, $00  ; Single silent frame
pulse2_frames:  .byte $00, $00, $00
triangle_frames: .byte $00, $00, $00
noise_frames:   .byte $00, $00
"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def prepare_project(self, music_asm_path: str):
        """Creates a complete NES project structure ready for CC65 compilation"""
        # Create project directory
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # Read music.asm content
        music_content = Path(music_asm_path).read_text()
        
        # Check if each channel's data exists, if not, add empty data
        required_symbols = ['pulse1_frames', 'pulse2_frames', 'triangle_frames', 'noise_frames']
        missing_symbols = []
        for symbol in required_symbols:
            if symbol not in music_content:
                missing_symbols.append(symbol)
        
        if missing_symbols:
            music_content = self.EMPTY_CHANNEL_DATA + "\n" + music_content
            
        # Write the modified music.asm
        (self.project_path / "music.asm").write_text(music_content)
        
        # Create main.asm
        (self.project_path / "main.asm").write_text(self.MAIN_ASM)
        
        # Create nes.cfg (linker configuration)
        (self.project_path / "nes.cfg").write_text(self.LINKER_CONFIG)
        
        # Create build script
        self._create_build_script()
        
        return True

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
