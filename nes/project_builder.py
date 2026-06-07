"""
NES Project Builder for MIDI2NES.

Prepares complete NES project structures for CC65 compilation,
using the mapper abstraction for flexible ROM configurations.
"""

import os
from pathlib import Path
from typing import Optional

from mappers import BaseMapper, get_mapper


class NESProjectBuilder:
    """
    Prepares a complete NES project structure for CC65 compilation.

    Supports multiple mappers through the mapper abstraction:
    - NROM (32KB) for small projects
    - MMC1 (128KB) for medium projects
    - MMC3 (512KB) for large projects
    """

    def __init__(
        self,
        project_path: str,
        debug_mode: bool = False,
        mapper: Optional[BaseMapper] = None,
        mapper_name: str = "auto",
    ):
        """
        Initialize NES project builder.

        Args:
            project_path: Directory to create project in
            debug_mode: If True, enables on-screen debug overlay
            mapper: Explicit mapper instance (overrides mapper_name)
            mapper_name: Mapper to use ('auto', 'nrom', 'mmc1', 'mmc3')
        """
        self.project_path = Path(project_path)
        self.debug_mode = debug_mode
        self._mapper = mapper
        self._mapper_name = mapper_name

    @property
    def mapper(self) -> BaseMapper:
        """Get the mapper instance, creating it if needed."""
        if self._mapper is None:
            self._mapper = get_mapper(self._mapper_name)
        return self._mapper

    def set_mapper(self, mapper: BaseMapper) -> None:
        """Set a specific mapper instance."""
        self._mapper = mapper

    def set_mapper_by_name(self, name: str) -> None:
        """Set mapper by name."""
        self._mapper = get_mapper(name)

    def auto_select_mapper(self, data_size: int) -> BaseMapper:
        """
        Auto-select the smallest mapper that fits the data.

        Args:
            data_size: Size of music data in bytes

        Returns:
            Selected mapper instance
        """
        self._mapper = get_mapper("auto", data_size=data_size)
        return self._mapper

    def prepare_project(self, music_asm_path: str) -> bool:
        """
        Creates a complete NES project structure ready for CC65 compilation.

        Args:
            music_asm_path: Path to the music.asm file to include

        Returns:
            True on success
        """
        # Create project directory
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Read music.asm content
        music_content = Path(music_asm_path).read_text()
        
        # Remove old includes if they were left over
        music_content = music_content.replace('.include "mmc3_init.asm"\n', '')
        music_content = music_content.replace('.include "audio_engine.asm"\n', '')

        print(f"  Using {self.mapper.name} with {self.mapper.prg_rom_size // 1024}KB PRG-ROM")

        if self.debug_mode:
            print(f"  Debug mode enabled - adding on-screen diagnostics")
            from nes.debug_overlay import NESDebugOverlay
            overlay = NESDebugOverlay(enable_overlay=True)
            music_content += "\n.importzp ptr1, temp1, temp2, frame_counter\n"
            music_content += "\n.global debug_init, debug_update, debug_test_apu\n"
            music_content += "\n" + overlay.generate_full_debug_system()

        # Write music.asm
        (self.project_path / "music.asm").write_text(music_content)
        
        # MMC3 mode overriding
        init_src = Path(__file__).parent / "mmc3_init.asm"
        if init_src.exists():
            init_content = init_src.read_text()
            if self.debug_mode:
                init_content = ".import debug_init, debug_test_apu, debug_update\n" + init_content
                init_content = init_content.replace("JSR audio_init", "JSR debug_init\n    JSR debug_test_apu\n    JSR audio_init")
                init_content = init_content.replace("JSR audio_update", "JSR audio_update\n    JSR debug_update")
            (self.project_path / "mmc3_init.asm").write_text(init_content)
            
        engine_src = Path(__file__).parent / "audio_engine.asm"
        if engine_src.exists():
            (self.project_path / "audio_engine.asm").write_text(engine_src.read_text())
            
        linker_src = Path(__file__).parent / "linker_mmc3.cfg"
        if linker_src.exists():
            (self.project_path / "nes.cfg").write_text(linker_src.read_text())
        else:
            (self.project_path / "nes.cfg").write_text(self.mapper.generate_linker_config())
            
        # Generate main.asm
        main_content = """
.segment "HEADER"
    .byte "NES", $1A
    .byte $08        ; 128KB PRG ROM
    .byte $00        ; 0KB CHR ROM
    .byte $40        ; Mapper 4 (MMC3), Horizontal mirroring
    .byte $00
    .byte $00
    .byte $00
    .res 5, $00

.include "mmc3_init.asm"
.include "audio_engine.asm"
"""
        (self.project_path / "main.asm").write_text(main_content)
        self._create_build_script_mmc3()

        return True

    def _generate_main_asm(self) -> str:
        """Generate main.asm with mapper-specific code."""
        # Debug mode imports and calls
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

        return f""".segment "HEADER"
{self.mapper.generate_header_asm()}

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

{self.mapper.generate_init_code()}

    ; Initialize frame counter
    lda #$00
    sta frame_counter
    sta frame_counter+1
{debug_init_call}
    ; Initialize APU and music
    jsr init_music

    ; CRITICAL: Enable NMI for 60Hz timing
    lda #$80
    sta $2000          ; Enable NMI, this makes music timing work!

mainloop:
    ; Just wait for NMI to handle timing
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

    def _create_build_script(self):
        """Creates a build script based on the OS."""
        is_windows = os.name == 'nt'
        script = self.mapper.generate_build_script(is_windows)

        script_name = "build.bat" if is_windows else "build.sh"
        script_path = self.project_path / script_name
        script_path.write_text(script)

        if not is_windows:
            # Make the script executable on Unix-like systems
            script_path.chmod(script_path.stat().st_mode | 0o755)
            
    def _create_build_script_mmc3(self):
        """Creates a build script specifically for the MMC3 Macro Engine."""
        is_windows = os.name == 'nt'
        script_name = "build.bat" if is_windows else "build.sh"
        script_path = self.project_path / script_name
        
        if is_windows:
            script = "@echo off\necho Compiling MMC3 Audio Engine...\nca65 main.asm -g -o main.o\nca65 music.asm -g -o music.o\nld65 -C nes.cfg -o output.nes main.o music.o\nif %errorlevel% neq 0 exit /b %errorlevel%\necho Done!\n"
        else:
            script = "#!/bin/bash\nset -e\necho \"Compiling MMC3 Audio Engine...\"\nca65 main.asm -g -o main.o\nca65 music.asm -g -o music.o\nld65 -C nes.cfg -o output.nes main.o music.o\necho \"Done!\"\n"
            
        script_path.write_text(script)
        if not is_windows:
            script_path.chmod(script_path.stat().st_mode | 0o755)

    # Legacy methods for backwards compatibility
    @property
    def use_mmc1(self) -> bool:
        """Legacy compatibility: check if using MMC1."""
        return self.mapper.mapper_number == 1

    def prepare_multi_song_project(self, music_asm_path: str, segments_data: dict) -> bool:
        """Legacy: fallback to simple project preparation."""
        return self.prepare_project(music_asm_path)

    def add_song_bank(self, song_bank) -> bool:
        """Legacy compatibility."""
        return True
