"""
NES Project Builder for MIDI2NES.

Prepares complete NES project structures for CC65 compilation,
using the mapper abstraction for flexible ROM configurations.
"""

import os
from pathlib import Path
from typing import Optional

from mappers import BaseMapper, get_mapper
from mappers.capacity import check_mapper_capacity
from core.exceptions import ExportError


# Leading ld65-comment marker written into nes.cfg recording the mapper a
# project was prepared with, so `compile` can recover it authoritatively
# (#297/MAP-2026-07-06-1). '#' is an ld65 config line comment, ignored by the
# linker. The value is the lowercase mapper name ('nrom'/'mmc1'/'mmc3').
NES_CFG_MAPPER_MARKER = "# midi2nes-mapper: "


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

    def prepare_project(self, music_asm_path: str, song_count: Optional[int] = None) -> bool:
        """
        Creates a complete NES project structure ready for CC65 compilation.

        Args:
            music_asm_path: Path to the music.asm file to include
            song_count: Number of songs packed into ``music_asm_path`` by a
                jukebox build (#30/F-13, ``CA65Exporter.export_song_bank_bytecode``,
                which always emits jukebox-format symbols regardless of song
                count -- including a 1-song bank). ``None`` (default) is an
                ordinary single-song project produced by
                ``export_tables_with_patterns`` -- output is unchanged from
                before this parameter existed. Any other value (``>= 1``)
                defines ``JUKEBOX_BUILD`` before including audio_engine.asm
                and adds the Start-button skip-to-next-song polling in
                ``_generate_main_asm``. If omitted, jukebox mode is
                auto-detected from ``music_asm_path``'s own content (the
                exporter's distinguishing marker), so a jukebox music.asm
                handed to `prepare` directly (bypassing `song build`) still
                links instead of failing at ld65 with unresolved externals
                (#453/MAP-2026-08-21-1).

        Returns:
            True on success
        """
        # Create project directory
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Read music.asm content
        music_content = Path(music_asm_path).read_text()
        
        # Remove old includes if they were left over. mmc3_init.asm was deleted
        # as fully dead code (#203/NH-28) -- the live reset/NMI/IRQ/APU-init is
        # the inline template in _generate_main_asm -- so this strip stays purely
        # to neutralize any stale `.include "mmc3_init.asm"` a hand-edited or
        # legacy music.asm might still carry (which would now fail assembly).
        music_content = music_content.replace('.include "mmc3_init.asm"\n', '')
        music_content = music_content.replace('.include "audio_engine.asm"\n', '')

        # The bytecode macro runtime appended below — and audio_engine.asm — only
        # make sense for the pattern/bytecode export. The direct (--no-patterns /
        # empty) export is self-contained, so skip the whole runtime for it;
        # otherwise music.asm references engine-only symbols it never defines
        # (ptr1/temp1/instrument_table/ntsc_period_*) and won't assemble (issue #50).
        is_bytecode = "MMC3 Macro Bytecode" in music_content

        # Auto-detect jukebox mode from music.asm itself when the caller
        # didn't pass song_count. export_song_bank_bytecode always stamps
        # this marker on its first line (exporter/exporter_ca65.py), so a
        # jukebox music.asm handed to the documented `prepare`/`compile`
        # split flow (or any library caller besides run_song_build) used to
        # "succeed" here -- capacity pre-flight passes, all files written --
        # and only fail two steps later at ld65 with unresolved externals,
        # since JUKEBOX_BUILD was never defined (#453/MAP-2026-08-21-1).
        # The exact count doesn't matter below: _generate_main_asm and the
        # JUKEBOX_BUILD injection further down only ever check `is not
        # None`; the ROM's actual runtime song_count comes from music.asm's
        # own exported byte, not this parameter.
        if song_count is None and "multi-song jukebox build" in music_content:
            song_count = 1

        # Bytecode mode has no fallback definition of frame_counter (and other
        # engine zeropage vars): main.asm's reset routine writes to it
        # unconditionally, relying entirely on audio_engine.asm's ZEROPAGE
        # block being pulled in later by .include. Fail loudly here, before
        # any project files are written, rather than let a missing/relocated
        # engine surface as a cryptic "undefined symbol" from ca65 (#37/M-11).
        if is_bytecode and not (Path(__file__).parent / "audio_engine.asm").exists():
            raise ExportError(
                "audio_engine.asm is required for bytecode-mode projects but is missing",
                f"expected at {Path(__file__).parent / 'audio_engine.asm'}"
            )

        # Import the sequence tracking ZP variables (bytecode runtime only)
        if is_bytecode:
            music_content += "\n.importzp sequence_ptr, sequence_bank\n"

        print(f"  Using {self.mapper.name} with {self.mapper.prg_rom_size // 1024}KB PRG-ROM")

        if self.debug_mode:
            print(f"  Debug mode enabled - adding on-screen diagnostics")
            from nes.debug_overlay import NESDebugOverlay
            overlay = NESDebugOverlay(enable_overlay=True)
            music_content += "\n.importzp ptr1, temp1, temp2, frame_counter\n"
            music_content += "\n.global debug_init, debug_update, debug_test_apu\n"
            # Explicit .segment "CODE" (#388/MAP-2026-08-05-1): the overlay
            # text otherwise inherits whatever segment was last active in
            # music.asm (in practice "RODATA", from the DPCM packer's stub
            # tables). On mappers with a switchable direct-export window
            # (MMC1), RODATA shares that switchable bank while CODE loads
            # into the always-mapped fixed bank -- without this, debug_init/
            # debug_update link into the switchable window and the CPU
            # executes stale table bytes as opcodes the moment a different
            # bank is selected when the NMI handler calls debug_update.
            music_content += '\n.segment "CODE"\n'
            music_content += overlay.generate_full_debug_system()

        # fetch_sequence_byte (bytecode runtime only) is .import'ed and called
        # by nes/audio_engine.asm (#314/EXP-12 -- this used to also append a
        # seq_cmd_dpcm_play/seq_cmd_instrument macro-instrument/DPCM-trigger
        # implementation here, but audio_engine.asm implements both of those
        # inline with its own variable names and calling convention, so that
        # second copy was fully dead code + ~85 bytes of unused BSS; removed).
        if is_bytecode:
            music_content += """
.segment "CODE"
; ------------------------------------------------------------------
; fetch_sequence_byte
; Swaps the sequence bank into $A000-$BFFF (R7), reads 1 byte, increments ptr
; ------------------------------------------------------------------
.global fetch_sequence_byte
fetch_sequence_byte:
    ; Select MMC3 PRG Bank Register 7 ($A000-$BFFF), keep P=1
    lda #$47
    sta $8000

    ; Swap in the sequence bank
    lda sequence_bank
    sta $8001

    ; Translate pointer from linker address to the $A000 window
    lda sequence_ptr+1
    pha
    and #$1F          ; Isolate the offset within the 8KB bank
    ora #$A0          ; Shift it into the $A000-$BFFF range
    sta sequence_ptr+1

    ldy #$00
    lda (sequence_ptr), y

    ; Restore original pointer high byte
    pla
    sta sequence_ptr+1

    ; Advance the pointer
    inc sequence_ptr
    bne @no_carry
    inc sequence_ptr+1
@no_carry:
    rts
"""

        # Guarantee the DPCM lookup tables the audio engine imports resolve exactly
        # once (bytecode runtime only). The DPCM packer emits the real tables
        # (appended to music.asm before this runs) when samples exist; otherwise
        # nothing has defined them, so emit harmless single-byte stubs. The packer
        # never exports the symbols, so do it here regardless of which side defined.
        if is_bytecode:
            music_content += "\n.export dpcm_bank_table, dpcm_pitch_table, dpcm_addr_table, dpcm_len_table\n"
            if "dpcm_bank_table:" not in music_content:
                music_content += (
                    '\n.segment "RODATA"\n'
                    "; Stub DPCM lookup tables (no samples packed)\n"
                    "dpcm_bank_table:\n    .byte $00\n"
                    "dpcm_pitch_table:\n    .byte $00\n"
                    "dpcm_addr_table:\n    .byte $00\n"
                    "dpcm_len_table:\n    .byte $00\n"
                )

        # Write music.asm
        music_asm_out = self.project_path / "music.asm"
        music_asm_out.write_text(music_content)

        # Capacity pre-flight (#363/MAP-2026-07-19-3, #389/MAP-2026-08-05-2):
        # the CLI runs check_mapper_capacity before calling us too, but a
        # library consumer that builds NESProjectBuilder(...).prepare_project(...)
        # directly would otherwise get no clean overflow message and rely
        # entirely on ld65 erroring at link time. Gate here so both entry
        # points fail the same way, with the region-naming budget message.
        # Runs on the *final* written music.asm -- after the --debug overlay,
        # fetch_sequence_byte, and DPCM-stub content above are all folded in
        # -- rather than the pre-transform source file, so a song that only
        # overflows once that ~800+ bytes of extra content is added is still
        # caught here instead of surfacing as a raw ld65 region overflow (or,
        # on a mapper with a switchable direct-export bank, not failing
        # cleanly at all). ld65 stays the exact backstop.
        check_mapper_capacity(str(music_asm_out), self.mapper)
        
        # Audio Engine
        engine_src = Path(__file__).parent / "audio_engine.asm"
        if engine_src.exists():
            (self.project_path / "audio_engine.asm").write_text(engine_src.read_text())
            
        # Linker Configuration. Stamp the mapper name as a leading ld65 comment
        # so `compile` can recover the exact mapper this project was prepared
        # with -- a NROM/MMC1 direct-export music.asm carries no engine marker,
        # so without this the compile step defaults to MMC3 and rejects a valid
        # NROM ROM with a misleading size mismatch (#297/MAP-2026-07-06-1, #269).
        nes_cfg = (f"{NES_CFG_MAPPER_MARKER}{self.mapper.name.lower()}\n"
                   + self.mapper.generate_linker_config())
        (self.project_path / "nes.cfg").write_text(nes_cfg)
            
        # Generate main.asm
        main_content = self._generate_main_asm(is_bytecode, song_count=song_count)
        
        # Add mapper-specific bank switching code and export it.
        # The main.asm template ends inside the VECTORS segment, so switch back
        # to CODE first — otherwise this routine is assembled into VECTORS and
        # overflows the 6-byte reset/NMI/IRQ area.
        main_content += '\n.segment "CODE"\n.global switch_dpcm_bank\n'
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
        
        # Include the audio engine only for the bytecode export. The direct export
        # is self-contained and the engine imports symbols it never defines (#50).
        if is_bytecode and engine_src.exists():
            if song_count is not None:
                # song_count is only ever passed by a jukebox build
                # (CA65Exporter.export_song_bank_bytecode) -- that exporter
                # ALWAYS emits jukebox-format symbols (song{i}_-prefixed,
                # a song_table) regardless of song count, including a
                # 1-song bank, so this must trigger on song_count being
                # given at all, not just `> 1` (#30/F-13,
                # MAP-2026-08-07-2/NH-HW-2026-08-07-1/PL-2026-08-07-1 --
                # a 1-song bank used to reference audio_init_song and the
                # fixed sequence labels with JUKEBOX_BUILD never defined,
                # failing to link with unresolved externals).
                #
                # ca65's .ifdef only recognizes real symbol/constant
                # definitions, not .define'd macros -- this must be a plain
                # assignment, and it must precede the .include below so
                # audio_engine.asm's own `.ifdef JUKEBOX_BUILD` sees it.
                main_content += '\nJUKEBOX_BUILD = 1\n'
            main_content += '\n.include "audio_engine.asm"\n'
            
        (self.project_path / "main.asm").write_text(main_content)
        self._create_build_script()

        return True

    def _generate_main_asm(self, is_bytecode: bool = True, song_count: Optional[int] = None) -> str:
        """Generate main.asm with mapper-specific code.

        In bytecode mode the included audio_engine.asm defines/exports
        frame_counter; the self-contained direct export does not include the
        engine, so main.asm must own frame_counter itself (issue #50).

        ``song_count`` is the number of songs a jukebox build (#30/F-13)
        packed into this ROM via ``CA65Exporter.export_song_bank_bytecode``,
        which ALWAYS emits jukebox-format symbols regardless of song count
        -- including a 1-song bank. ``None`` (the default -- an ordinary
        single-song build produced by ``export_tables_with_patterns``)
        leaves this method's output unchanged from before this feature
        existed; any non-``None`` value (``>= 1``) defines ``JUKEBOX_BUILD``
        and adds the Start-button skip-to-next-song polling below (a no-op
        wrap-to-self for a 1-song bank, but still required so
        ``audio_init_song``/``audio_advance_song`` exist to resolve the
        jukebox music.asm's symbol references).
        """
        jukebox_mode = song_count is not None

        frame_counter_def = "" if is_bytecode else (
            "    frame_counter: .res 2  ; 60Hz tick (direct export owns this)\n"
            ".exportzp frame_counter\n"
        )
        # Debug mode imports and calls
        debug_imports = ""
        debug_init_call = ""
        debug_update_call = ""

        # Jukebox-only (#30/F-13): edge-detect the Start button in the NMI
        # handler and skip to the next song on a fresh press. Reuses
        # read_joypad_safe/joypad_state (appended by prepare_project after
        # this method returns -- same module, forward reference is fine in
        # ca65) rather than a second joypad-read routine. `prev_start_state`
        # is what makes this edge-triggered instead of re-firing every frame
        # the button stays held.
        jukebox_zp = ""
        jukebox_skip_call = ""
        if jukebox_mode:
            jukebox_zp = "    prev_start_state: .res 1\n"
            jukebox_skip_call = """
    ; Start button: skip to the next song (edge-triggered -- only on a
    ; fresh press, not every frame it's held).
    jsr read_joypad_safe
    lda joypad_state
    and #$10            ; isolate the Start bit
    tax                 ; save this frame's Start state (0 or nonzero)
    beq @start_not_pressed
    lda prev_start_state
    bne @start_not_pressed  ; still held from last frame -- not a new press
    jsr audio_advance_song
@start_not_pressed:
    txa
    sta prev_start_state
"""

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
            # Defense in depth for #388/MAP-2026-08-05-1: debug_init/
            # debug_update now live in the always-mapped CODE segment (see
            # the .segment "CODE" fix above), so which switchable bank is
            # selected no longer affects whether `jsr debug_update` reaches
            # the right code. But update_music's per-table bank-switching
            # (MMC1 direct export) leaves an arbitrary bank active on
            # return, and RODATA (the plain, non-banked segment the DPCM
            # packer/stub still emit) physically shares bank 0 -- so
            # reselecting bank 0 here means that even if a future change
            # reintroduces debug code into an inherited RODATA segment, the
            # bank left active is the one that content actually lives in.
            bank_restore = ""
            if self.mapper.direct_export_bank_size() is not None:
                bank_restore = "\n" + self.mapper.generate_bank_switch_code(0) + "\n"
            debug_update_call = f"""
{bank_restore}    ; Update debug overlay
    jsr debug_update
"""

        return f""".segment "HEADER"
{self.mapper.generate_header_asm()}

.segment "ZEROPAGE"
    ; Export zeropage variables for music.asm
    temp_ptr:      .res 2  ; Temporary pointer for table lookups
    sequence_ptr:  .res 2  ; 16-bit pointer to current sequence byte
    sequence_bank: .res 1  ; 8-bit bank number where this sequence lives
.exportzp temp_ptr, sequence_ptr, sequence_bank
{frame_counter_def}
{jukebox_zp}
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
{jukebox_skip_call}
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
            
    # Legacy methods for backwards compatibility
    @property
    def use_mmc1(self) -> bool:
        """Legacy compatibility: check if using MMC1."""
        return self.mapper.mapper_number == 1

