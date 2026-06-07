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

        # DPCM Sequence command macro implementation
        music_content += """
.import switch_dpcm_bank

; ------------------------------------------------------------------
; seq_cmd_dpcm_play ($85)
; Triggers a DPCM sample based on the sample_id parameter.
; ------------------------------------------------------------------
.global seq_cmd_dpcm_play
seq_cmd_dpcm_play:
    ; Assuming X contains the Sample_ID from the sequence data
    ; 1. Swap the required MMC3 bank into the $C000-$DFFF window
    lda dpcm_bank_table, x
    jsr switch_dpcm_bank

    ; 2. Setup the APU DMC registers using the lookup tables
    lda dpcm_pitch_table, x
    sta $4010                   ; Set Pitch/Rate index

    lda dpcm_addr_table, x
    sta $4012                   ; Set 64-byte aligned Address

    lda dpcm_len_table, x
    sta $4013                   ; Set 16-byte aligned Length

    ; 3. Trigger the DMC DMA playback
    lda #$0F                    ; Disable DMC
    sta $4015
    lda #$1F                    ; Enable all channels AND DMC
    sta $4015

    rts
"""

        # Instrument and Macro Engine implementation
        music_content += """
.segment "BSS"
; Channel state variables (4 channels: Pulse1, Pulse2, Triangle, Noise)
ch_macro_vol_lo:    .res 4
ch_macro_vol_hi:    .res 4
ch_macro_vol_idx:   .res 4
ch_vol_current:     .res 4

ch_macro_duty_lo:   .res 4
ch_macro_duty_hi:   .res 4
ch_macro_duty_idx:  .res 4
ch_duty_current:    .res 4

ch_macro_pitch_lo:  .res 4
ch_macro_pitch_hi:  .res 4
ch_macro_pitch_idx: .res 4
ch_pitch_offset:    .res 4 ; signed 8-bit offset

ch_base_note:       .res 4 ; The base note for the current sound

apu_shadow_ctrl:    .res 4
apu_shadow_timer_lo: .res 4
apu_shadow_timer_hi: .res 4

.segment "CODE"
; ------------------------------------------------------------------
; seq_cmd_instrument ($80)
; Sets the current instrument for the active channel.
; ------------------------------------------------------------------
.global seq_cmd_instrument
seq_cmd_instrument:
    ; Assuming X is the channel index (0-3)
    ; Assuming A contains the instrument ID from the sequencer stream
    
    ; Multiply instrument ID by 8 (4 pointers * 2 bytes)
    asl a
    asl a
    asl a
    tay
    
    ; Load Volume Macro pointer (Offset 0)
    ; (Assuming instrument_table is exported from CA65Exporter)
    lda instrument_table+0, y
    sta ch_macro_vol_lo, x
    lda instrument_table+1, y
    sta ch_macro_vol_hi, x
    
    ; Load Pitch Macro pointer (Offset 4)
    lda instrument_table+4, y
    sta ch_macro_pitch_lo, x
    lda instrument_table+5, y
    sta ch_macro_pitch_hi, x

    ; Load Duty Macro pointer (Offset 6)
    lda instrument_table+6, y
    sta ch_macro_duty_lo, x
    lda instrument_table+7, y
    sta ch_macro_duty_hi, x
    
    ; Reset macro indices
    lda #$00
    sta ch_macro_vol_idx, x
    sta ch_macro_duty_idx, x
    sta ch_macro_pitch_idx, x
    rts

; ------------------------------------------------------------------
; process_channel_macros
; Evaluates volume and duty macros for channel X
; ------------------------------------------------------------------
.global process_channel_macros
.import ntsc_period_low, ntsc_period_high

process_channel_macros:
    ; --- Process Volume Macro ---
    lda ch_macro_vol_lo, x
    sta ptr1
    lda ch_macro_vol_hi, x
    sta ptr1+1
    
    ldy ch_macro_vol_idx, x
    lda (ptr1), y
    cmp #$FF            ; $FF = Sustain last value
    beq @sustain_vol
    cmp #$FE            ; $FE = Loop
    beq @loop_vol
    
    sta ch_vol_current, x
    inc ch_macro_vol_idx, x
    jmp @process_duty
    
@loop_vol:
    iny
    lda (ptr1), y       ; Get loop target index
    sta ch_macro_vol_idx, x
    tay
    lda (ptr1), y       ; Fetch the value at the loop target
    sta ch_vol_current, x
    inc ch_macro_vol_idx, x
    
@sustain_vol:

    ; --- Process Duty Macro ---
    lda ch_macro_duty_lo, x
    sta ptr1
    lda ch_macro_duty_hi, x
    sta ptr1+1
    
    ldy ch_macro_duty_idx, x
    lda (ptr1), y
    cmp #$FF
    beq @sustain_duty
    cmp #$FE
    beq @loop_duty
    
    ; Shift duty cycle to bits 6-7 (0-3 -> $00-$C0)
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta ch_duty_current, x
    inc ch_macro_duty_idx, x
    jmp @combine
    
@loop_duty:
    iny
    lda (ptr1), y
    sta ch_macro_duty_idx, x
    tay
    lda (ptr1), y
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta ch_duty_current, x
    inc ch_macro_duty_idx, x

@sustain_duty:

    ; --- Process Pitch Macro (Vibrato/Slides) ---
    lda ch_macro_pitch_lo, x
    sta ptr1
    lda ch_macro_pitch_hi, x
    sta ptr1+1

    ldy ch_macro_pitch_idx, x
    lda (ptr1), y
    cmp #$FF
    beq @sustain_pitch
    cmp #$FE
    beq @loop_pitch

    sta ch_pitch_offset, x
    inc ch_macro_pitch_idx, x
    jmp @calc_final_pitch

@loop_pitch:
    iny
    lda (ptr1), y
    sta ch_macro_pitch_idx, x
    tay
    lda (ptr1), y
    sta ch_pitch_offset, x
    inc ch_macro_pitch_idx, x

@sustain_pitch:

@calc_final_pitch:
    ; Sign-extend the pitch offset into temp1
    lda ch_pitch_offset, x
    bpl @positive_pitch
    lda #$FF
    jmp @store_pitch_hi
@positive_pitch:
    lda #$00
@store_pitch_hi:
    sta temp1

    ; Get base note period from lookup table
    ldy ch_base_note, x
    
    ; Calculate final 16-bit period = base_period + pitch_offset
    ; Low byte
    lda ntsc_period_low, y
    clc
    adc ch_pitch_offset, x
    sta apu_shadow_timer_lo, x
    
    ; High byte
    lda ntsc_period_high, y
    adc temp1
    sta apu_shadow_timer_hi, x

@combine:
    ; Combine Duty + Volume + Constant Volume Flag ($30)
    lda ch_duty_current, x
    ora ch_vol_current, x
    ora #$30
    sta apu_shadow_ctrl, x
    
    rts
"""

        # Write music.asm
        (self.project_path / "music.asm").write_text(music_content)
        
        # Audio Engine
        engine_src = Path(__file__).parent / "audio_engine.asm"
        if engine_src.exists():
            (self.project_path / "audio_engine.asm").write_text(engine_src.read_text())
            
        # Linker Configuration
        (self.project_path / "nes.cfg").write_text(self.mapper.generate_linker_config())
            
        # Generate main.asm
        main_content = self._generate_main_asm()
        
        # Add mapper-specific bank switching code and export it
        main_content += "\n.global switch_dpcm_bank\n"
        main_content += self.mapper.generate_bank_switch_code(0)
        
        # Add safe joypad reading logic for DMC DMA conflicts
        main_content += """
.segment "ZEROPAGE"
temp_joypad:  .res 1
joypad_state: .res 1

.segment "CODE"
.global read_joypad_safe

; ------------------------------------------------------------------
; read_joypad_safe
; Safely reads controller 1 at $4016, protecting against the DPCM 
; DMA double-read glitch. Final valid result is stored in 'joypad_state'.
; ------------------------------------------------------------------
read_joypad_safe:
@retry:
    jsr read_joypad_once
    lda temp_joypad
    sta joypad_state      ; Save it temporarily

    jsr read_joypad_once
    lda temp_joypad
    cmp joypad_state      ; Compare second read with the first
    
    bne @retry            ; If they differ, glitch occurred! Retry.
    rts

read_joypad_once:
    lda #$01
    sta $4016
    lda #$00
    sta $4016

    ldx #8
@read_loop:
    lda $4016
    lsr a
    rol temp_joypad
    dex
    bne @read_loop
    rts
"""
        
        # Include the audio engine if available
        if engine_src.exists():
            main_content += '\n.include "audio_engine.asm"\n'
            
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
