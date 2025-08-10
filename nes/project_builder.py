import os
from pathlib import Path

class NESProjectBuilder:
    """Prepares a complete NES project structure for CC65 compilation"""
    
    # Default configuration for small files (Mapper 0)
    NES_HEADER = """; NES Header
.segment "HEADER"
.byte "NES", $1A      ; iNES header identifier
.byte 2               ; 2x 16KB PRG-ROM banks
.byte 1               ; 1x 8KB CHR-ROM bank
.byte $01, $00        ; Mapper 0, vertical mirroring
.byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding
"""
    
    # MMC1 configuration for large files (Mapper 1, 128KB PRG-ROM)
    MMC1_HEADER = """; MMC1 NES Header for Large Music Files
.segment "HEADER"
.byte "NES", $1A      ; iNES header identifier
.byte 8               ; 8x 16KB PRG-ROM banks (128KB total)
.byte 0               ; 0x 8KB CHR-ROM bank (CHR-RAM)
.byte $10, $00        ; Mapper 1 (MMC1), vertical mirroring
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
    .byte $02             ; 2 x 16KB PRG ROM (32KB total)
    .byte $00             ; 0 x 8KB CHR ROM
    .byte $00             ; Mapper 0, horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding (8 bytes)

.segment "ZEROPAGE"
    ptr1:           .res 2  ; General purpose pointer
    temp1:          .res 1  ; Temporary variable 1
    temp2:          .res 1  ; Temporary variable 2
    frame_counter:  .res 2  ; Current frame counter

.exportzp ptr1, temp1, temp2, frame_counter

.segment "CODE"
; Import music functions as absolute addresses
.global init_music
.global update_music

reset:
    sei                   ; Disable interrupts
    cld                   ; Clear decimal mode
    ldx #$FF
    txs                   ; Set up stack

    ; Initialize variables
    lda #0
    sta frame_counter
    sta frame_counter+1
    sta temp1
    sta temp2
    sta ptr1
    sta ptr1+1

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

    MULTI_SONG_MAIN_ASM = """.segment "HEADER"
    .byte "NES", $1A      ; NES header identifier
    .byte $02             ; 2 x 16KB PRG ROM (32KB total)
    .byte $00             ; 0 x 8KB CHR ROM
    .byte $00             ; Mapper 0, horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding (8 bytes)

.segment "ZEROPAGE"
    current_song:     .res 1  ; Current song index
    current_segment:  .res 1  ; Current segment within song
    current_frame:    .res 2  ; Current frame counter

.segment "CODE"
    .include "music.asm"

reset:
    sei                   ; Disable interrupts
    cld                   ; Clear decimal mode
    ldx #$FF
    txs                   ; Set up stack

    ; Initialize APU and song
    jsr init_music
    lda #0               ; Start with first song
    sta current_song
    sta current_segment
    sta current_frame
    sta current_frame+1

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

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.song_segments = None
        self.use_mmc1 = False  # Will be set based on music data size

    def prepare_multi_song_project(self, music_asm_path: str, segments_data: dict):
        """Creates a complete NES project structure with multi-song support"""
        self.song_segments = segments_data
        
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
            
        # Add segment tables
        music_content = self._generate_segment_tables() + "\n" + music_content
            
        # Write the modified music.asm
        (self.project_path / "music.asm").write_text(music_content)
        
        # Create main.asm with multi-song support
        (self.project_path / "main.asm").write_text(self.MULTI_SONG_MAIN_ASM)
        
        # Create nes.cfg with expanded PRG-ROM
        (self.project_path / "nes.cfg").write_text(self._generate_multi_bank_config())
        
        # Create build script
        self._create_build_script()
        
        return True

    def _generate_segment_tables(self):
        """Generate assembly code for segment tables"""
        lines = [
            "; Song segment tables",
            ".segment \"RODATA\"",
            "",
            "song_segment_table:"
        ]
        
        for song_id, song_data in self.song_segments.items():
            for segment_id, segment in enumerate(song_data["segments"]):
                lines.append(f"    .word segment_{song_id}_{segment_id}_start  ; Song {song_id}, Segment {segment_id}")
        
        lines.extend([
            "",
            "song_segment_loop_table:"
        ])
        
        for song_id, song_data in self.song_segments.items():
            for segment_id, segment in enumerate(song_data["segments"]):
                loop_to = segment.get("loop_to", segment["start_frame"])
                lines.append(f"    .word {loop_to}  ; Song {song_id}, Segment {segment_id}")
        
        lines.extend([
            "",
            "song_segment_length_table:"
        ])
        
        for song_id, song_data in self.song_segments.items():
            for segment_id, segment in enumerate(song_data["segments"]):
                length = segment["end_frame"] - segment["start_frame"] + 1
                lines.append(f"    .word {length}  ; Song {song_id}, Segment {segment_id}")
        
        return "\n".join(lines)

    def _generate_multi_bank_config(self):
        """Generate linker config with expanded PRG-ROM"""
        return """MEMORY {
    # NES has 2KB of RAM
    ZP:     start = $00,    size = $0100, type = rw, file = "";
    RAM:    start = $0200,  size = $0600, type = rw, file = "";
    
    # NES ROM layout with 32KB PRG-ROM
    HEADER: start = $0000,  size = $0010, type = ro, file = %O, fill = yes;
    PRG1:   start = $8000,  size = $4000, type = ro, file = %O, fill = yes;
    PRG2:   start = $C000,  size = $4000, type = ro, file = %O, fill = yes;
    
    # 6502 vectors at end of ROM
    VECTORS: start = $FFFA, size = $0006, type = ro, file = %O, fill = yes;
}

SEGMENTS {
    HEADER:   load = HEADER,  type = ro;
    ZEROPAGE: load = ZP,      type = zp;
    BSS:      load = RAM,     type = bss, define = yes;
    CODE:     load = PRG2,    type = ro;  # Fixed bank
    RODATA:   load = PRG1,    type = ro;  # Switchable bank
    VECTORS:  load = VECTORS, type = ro;
}"""

    def add_song_bank(self, song_bank):
        """Add multi-song bank support to the project"""
        self.song_bank = song_bank
        return True

    def prepare_project(self, music_asm_path: str):
        """Creates a complete NES project structure ready for CC65 compilation"""
        # Create project directory
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # Read music.asm content
        music_content = Path(music_asm_path).read_text()
        
        # Estimate music data size and determine if we need MMC1
        music_size = self._estimate_music_data_size(music_content)
        print(f"  Estimated music data size: {music_size:,} bytes")
        
        self.use_mmc1 = music_size > 15000  # Use MMC1 if estimated size > 15KB
        
        if self.use_mmc1:
            print(f"  Large music data detected - switching to MMC1 mapper")
            print(f"  Using MMC1 with 128KB PRG-ROM (8 banks)")
        else:
            print(f"  Using standard Mapper 0 with 32KB PRG-ROM")
        
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
        
        # Create main.asm with appropriate header
        main_asm = self._generate_main_asm()
        (self.project_path / "main.asm").write_text(main_asm)
        
        # Create nes.cfg (linker configuration)
        linker_config = self._generate_linker_config()
        (self.project_path / "nes.cfg").write_text(linker_config)
        
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
    
    def _estimate_music_data_size(self, music_content: str) -> int:
        """Estimate the size of music data in bytes"""
        # Count the number of data bytes in the assembly content
        # This is a rough estimate based on .byte directives and pattern data
        
        byte_count = 0
        
        # Count .byte directives
        lines = music_content.split('\n')
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith('.byte'):
                # Count comma-separated values
                byte_values = stripped_line[5:].split(',')
                byte_count += len([v for v in byte_values if v.strip()])
            elif stripped_line.startswith('.word'):
                # Each .word takes 2 bytes
                word_values = stripped_line[5:].split(',')
                byte_count += len([v for v in word_values if v.strip()]) * 2
        
        # Add estimates for pattern data structures
        if 'pattern_' in music_content:
            # Rough estimate: each pattern averages 10 bytes
            pattern_count = music_content.count('pattern_')
            byte_count += pattern_count * 10
        
        # Add estimates for note tables and other data structures
        if 'note_table' in music_content:
            byte_count += 96  # Note table is ~96 bytes
        
        return byte_count
    
    def _generate_main_asm(self) -> str:
        """Generate main.asm with appropriate mapper header"""
        if self.use_mmc1:
            # MMC1 main.asm with 128KB PRG-ROM
            return """.segment "HEADER"
    .byte "NES", $1A      ; NES header identifier
    .byte $08             ; 8 x 16KB PRG ROM (128KB total)
    .byte $00             ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $10             ; Mapper 1 (MMC1), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding (8 bytes)

.segment "ZEROPAGE"
    ptr1:           .res 2  ; General purpose pointer
    temp1:          .res 1  ; Temporary variable 1
    temp2:          .res 1  ; Temporary variable 2
    frame_counter:  .res 2  ; Current frame counter
    mmc1_ctrl:      .res 1  ; MMC1 control register cache

.exportzp ptr1, temp1, temp2, frame_counter, mmc1_ctrl

.segment "CODE"
; Import music functions as absolute addresses
.global init_music
.global update_music

reset:
    sei                   ; Disable interrupts
    cld                   ; Clear decimal mode
    ldx #$FF
    txs                   ; Set up stack

    ; Initialize MMC1
    lda #$0C              ; 16KB PRG banks, CHR-RAM, horizontal mirroring
    sta mmc1_ctrl
    jsr _mmc1_write_control
    
    lda #$00              ; Select first PRG bank
    jsr _mmc1_write_prg_bank

    ; Initialize variables
    lda #0
    sta frame_counter
    sta frame_counter+1
    sta temp1
    sta temp2
    sta ptr1
    sta ptr1+1

    ; Initialize APU
    jsr init_music

mainloop:
    jsr update_music
    jmp mainloop

nmi:
    rti

irq:
    rti

; MMC1 bank switching routines
_mmc1_write_control:
    sta $8000             ; Write to control register
    lsr
    sta $8000
    lsr 
    sta $8000
    lsr
    sta $8000
    lsr
    sta $8000
    rts

_mmc1_write_prg_bank:
    sta $E000             ; Write to PRG bank register
    lsr
    sta $E000
    lsr
    sta $E000
    lsr
    sta $E000
    lsr
    sta $E000
    rts

.segment "VECTORS"
    .word nmi            ; NMI vector
    .word reset         ; Reset vector
    .word irq           ; IRQ vector
"""
        else:
            # Use default Mapper 0 configuration
            return self.MAIN_ASM
    
    def _generate_linker_config(self) -> str:
        """Generate linker configuration based on mapper choice"""
        if self.use_mmc1:
            # MMC1 linker config with 128KB PRG-ROM
            return """MEMORY {
    # NES has 2KB of RAM
    ZP:     start = $00,    size = $0100, type = rw, file = "";
    RAM:    start = $0200,  size = $0600, type = rw, file = "";
    
    # NES ROM layout - MMC1 with 128KB PRG-ROM
    HEADER: start = $0000,  size = $0010, type = ro, file = %O, fill = yes;
    PRG:    start = $8000,  size = $20000, type = ro, file = %O, fill = yes; # 128KB total
    
    # 6502 vectors at end of ROM
    VECTORS: start = $FFFA, size = $0006, type = ro, file = %O, fill = yes;
}

SEGMENTS {
    HEADER:   load = HEADER,  type = ro;
    ZEROPAGE: load = ZP,      type = zp;
    BSS:      load = RAM,     type = bss, define = yes;
    RODATA:   load = PRG,     type = ro;    # Music data (let linker place it)
    CODE:     load = PRG,     type = ro;    # Main code (let linker place it)
    VECTORS:  load = VECTORS, type = ro;
}"""
        else:
            # Use default Mapper 0 configuration
            return self.LINKER_CONFIG
