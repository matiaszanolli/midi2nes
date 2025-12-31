"""NES Debug Overlay System

Generates assembly code for on-screen debugging information including:
- Error messages and status codes
- APU channel state visualization
- Memory diagnostics
- Frame counter
- Music playback state

This helps debug ROM generation issues by providing visual feedback
directly on the NES screen.
"""

from typing import List, Dict, Optional


class NESDebugOverlay:
    """Generates NES assembly code for on-screen debug overlays."""

    # NES color palette for debug display
    COLORS = {
        'black': 0x0F,
        'white': 0x30,
        'red': 0x16,
        'green': 0x2A,
        'blue': 0x12,
        'yellow': 0x28,
        'cyan': 0x2C,
        'gray': 0x00
    }

    # Error codes
    ERROR_CODES = {
        'OK': 0x00,
        'APU_INIT_FAIL': 0x01,
        'MUSIC_DATA_CORRUPT': 0x02,
        'INVALID_CHANNEL': 0x03,
        'BUFFER_OVERFLOW': 0x04,
        'INVALID_NOTE': 0x05,
        'PATTERN_ERROR': 0x06,
        'MEMORY_ERROR': 0x07
    }

    def __init__(self, enable_overlay: bool = True):
        """Initialize debug overlay generator.

        Args:
            enable_overlay: Whether to enable the overlay (can be disabled for release)
        """
        self.enable_overlay = enable_overlay

    def generate_debug_init(self) -> str:
        """Generate initialization code for debug overlay.

        Returns:
            CA65 assembly code for debug initialization
        """
        if not self.enable_overlay:
            return "; Debug overlay disabled\n"

        return """; ============================================
; Debug Overlay Initialization
; ============================================
debug_init:
    ; Initialize debug variables
    LDA #$00
    STA debug_error_code
    STA debug_frame_counter
    STA debug_music_frame

    ; Clear debug text buffer
    LDX #$00
@clear_loop:
    STA debug_text_buffer, X
    INX
    BNE @clear_loop

    ; Set initial status message
    LDX #$00
@init_msg_loop:
    LDA debug_init_msg, X
    BEQ @init_msg_done
    STA debug_text_buffer, X
    INX
    BNE @init_msg_loop
@init_msg_done:

    RTS

debug_init_msg:
    .byte "MIDI2NES DEBUG v1.0", $00

; Debug variables
debug_error_code:       .res 1
debug_frame_counter:    .res 1
debug_music_frame:      .res 2  ; 16-bit frame counter
debug_apu_status:       .res 4  ; Status for each channel (Pulse1, Pulse2, Triangle, Noise)
debug_text_buffer:      .res 32 ; Text buffer for messages

"""

    def generate_debug_update(self) -> str:
        """Generate NMI update code for debug overlay.

        Returns:
            CA65 assembly code to update debug display each frame
        """
        if not self.enable_overlay:
            return "; Debug overlay disabled\n"

        return """; ============================================
; Debug Overlay Update (called from NMI)
; ============================================
debug_update:
    ; Increment frame counter
    INC debug_frame_counter

    ; Increment music frame counter (16-bit)
    INC debug_music_frame
    BNE @no_carry
    INC debug_music_frame+1
@no_carry:

    ; Update APU status
    JSR debug_check_apu_status

    ; Render debug overlay to screen
    JSR debug_render_overlay

    RTS

; ============================================
; Check APU Status
; ============================================
debug_check_apu_status:
    ; Check Pulse 1 (read $4015 bit 0)
    LDA $4015
    AND #$01
    STA debug_apu_status+0  ; Pulse1 active

    ; Check Pulse 2 (read $4015 bit 1)
    LDA $4015
    AND #$02
    LSR A
    STA debug_apu_status+1  ; Pulse2 active

    ; Check Triangle (read $4015 bit 2)
    LDA $4015
    AND #$04
    LSR A
    LSR A
    STA debug_apu_status+2  ; Triangle active

    ; Check Noise (read $4015 bit 3)
    LDA $4015
    AND #$08
    LSR A
    LSR A
    LSR A
    STA debug_apu_status+3  ; Noise active

    RTS

; ============================================
; Render Debug Overlay to Screen
; ============================================
debug_render_overlay:
    ; Wait for VBLANK
    BIT $2002

    ; Set PPU address to top of screen (nametable $2000)
    LDA $2002  ; Reset PPU address latch
    LDA #$20
    STA $2006
    LDA #$00
    STA $2006

    ; Write debug text
    LDX #$00
@text_loop:
    LDA debug_text_buffer, X
    BEQ @text_done
    STA $2007
    INX
    CPX #$20  ; Max 32 characters
    BNE @text_loop
@text_done:

    ; Render APU status bar (row 2)
    LDA $2002
    LDA #$20
    STA $2006
    LDA #$40  ; Row 2, column 0
    STA $2006

    ; Pulse 1 indicator
    LDA #'P'
    STA $2007
    LDA #'1'
    STA $2007
    LDA #':'
    STA $2007
    LDA debug_apu_status+0
    BEQ @pulse1_off
    LDA #$01  ; Green tile
    JMP @pulse1_write
@pulse1_off:
    LDA #$00  ; Black tile
@pulse1_write:
    STA $2007

    LDA #' '
    STA $2007

    ; Pulse 2 indicator
    LDA #'P'
    STA $2007
    LDA #'2'
    STA $2007
    LDA #':'
    STA $2007
    LDA debug_apu_status+1
    BEQ @pulse2_off
    LDA #$01  ; Green tile
    JMP @pulse2_write
@pulse2_off:
    LDA #$00  ; Black tile
@pulse2_write:
    STA $2007

    LDA #' '
    STA $2007

    ; Triangle indicator
    LDA #'T'
    STA $2007
    LDA #'R'
    STA $2007
    LDA #':'
    STA $2007
    LDA debug_apu_status+2
    BEQ @tri_off
    LDA #$01  ; Green tile
    JMP @tri_write
@tri_off:
    LDA #$00  ; Black tile
@tri_write:
    STA $2007

    LDA #' '
    STA $2007

    ; Noise indicator
    LDA #'N'
    STA $2007
    LDA #'S'
    STA $2007
    LDA #':'
    STA $2007
    LDA debug_apu_status+3
    BEQ @noise_off
    LDA #$01  ; Green tile
    JMP @noise_write
@noise_off:
    LDA #$00  ; Black tile
@noise_write:
    STA $2007

    ; Render frame counter (row 3)
    LDA $2002
    LDA #$20
    STA $2006
    LDA #$80  ; Row 3, column 0
    STA $2006

    ; "FRAME: "
    LDA #'F'
    STA $2007
    LDA #'R'
    STA $2007
    LDA #'A'
    STA $2007
    LDA #'M'
    STA $2007
    LDA #'E'
    STA $2007
    LDA #':'
    STA $2007
    LDA #' '
    STA $2007

    ; Display frame counter (16-bit, hex)
    LDA debug_music_frame+1
    JSR debug_print_hex_byte
    LDA debug_music_frame
    JSR debug_print_hex_byte

    ; Render error code if present (row 4)
    LDA debug_error_code
    BEQ @no_error

    LDA $2002
    LDA #$20
    STA $2006
    LDA #$C0  ; Row 4, column 0
    STA $2006

    ; "ERROR: "
    LDA #'E'
    STA $2007
    LDA #'R'
    STA $2007
    LDA #'R'
    STA $2007
    LDA #'O'
    STA $2007
    LDA #'R'
    STA $2007
    LDA #':'
    STA $2007
    LDA #' '
    STA $2007

    ; Display error code (hex)
    LDA debug_error_code
    JSR debug_print_hex_byte

@no_error:
    RTS

; ============================================
; Print hex byte to PPU
; Input: A = byte to print
; ============================================
debug_print_hex_byte:
    PHA
    ; Print high nibble
    LSR A
    LSR A
    LSR A
    LSR A
    JSR debug_print_hex_nibble

    ; Print low nibble
    PLA
    AND #$0F
    JSR debug_print_hex_nibble

    RTS

; ============================================
; Print hex nibble to PPU
; Input: A = nibble to print (0-15)
; ============================================
debug_print_hex_nibble:
    CMP #$0A
    BCC @is_digit
    ; A-F
    SEC
    SBC #$0A
    CLC
    ADC #'A'
    JMP @write
@is_digit:
    ; 0-9
    CLC
    ADC #'0'
@write:
    STA $2007
    RTS

"""

    def generate_debug_error_handler(self) -> str:
        """Generate error handling code.

        Returns:
            CA65 assembly code for error handling
        """
        if not self.enable_overlay:
            return "; Debug error handling disabled\n"

        return """; ============================================
; Debug Error Handler
; ============================================

; Set error code and display message
; Input: A = error code
debug_set_error:
    STA debug_error_code

    ; Set error message based on code
    CMP #$01
    BNE @check_02
    LDX #<error_msg_01
    LDY #>error_msg_01
    JMP @set_msg

@check_02:
    CMP #$02
    BNE @check_03
    LDX #<error_msg_02
    LDY #>error_msg_02
    JMP @set_msg

@check_03:
    CMP #$03
    BNE @check_04
    LDX #<error_msg_03
    LDY #>error_msg_03
    JMP @set_msg

@check_04:
    CMP #$04
    BNE @unknown_error
    LDX #<error_msg_04
    LDY #>error_msg_04
    JMP @set_msg

@unknown_error:
    LDX #<error_msg_unknown
    LDY #>error_msg_unknown

@set_msg:
    ; Copy error message to debug text buffer
    STX $00  ; Low byte
    STY $01  ; High byte

    LDY #$00
@copy_loop:
    LDA ($00), Y
    BEQ @copy_done
    STA debug_text_buffer, Y
    INY
    CPY #$20  ; Max 32 chars
    BNE @copy_loop
@copy_done:
    RTS

; Error messages
error_msg_01:
    .byte "ERR: APU INIT FAILED", $00
error_msg_02:
    .byte "ERR: MUSIC DATA BAD", $00
error_msg_03:
    .byte "ERR: INVALID CHANNEL", $00
error_msg_04:
    .byte "ERR: BUFFER OVERFLOW", $00
error_msg_unknown:
    .byte "ERR: UNKNOWN ERROR", $00

"""

    def generate_apu_diagnostics(self) -> str:
        """Generate APU diagnostic routines.

        Returns:
            CA65 assembly code for APU diagnostics
        """
        if not self.enable_overlay:
            return "; APU diagnostics disabled\n"

        return """; ============================================
; APU Diagnostics
; ============================================

; Test APU initialization
; Returns: A = 0 if OK, error code otherwise
debug_test_apu:
    ; Write to $4015 to enable all channels
    LDA #$0F
    STA $4015

    ; Read back $4015
    LDA $4015
    AND #$0F
    CMP #$0F
    BEQ @apu_ok

    ; APU test failed
    LDA #$01  ; APU_INIT_FAIL
    JMP debug_set_error

@apu_ok:
    LDA #$00
    RTS

; Display current APU register values (row 5-8)
debug_display_apu_regs:
    ; Row 5: Pulse 1 registers
    LDA $2002
    LDA #$21
    STA $2006
    LDA #$00
    STA $2006

    LDX #$00
@pulse1_msg:
    LDA apu_pulse1_label, X
    BEQ @pulse1_done
    STA $2007
    INX
    JMP @pulse1_msg
@pulse1_done:

    ; Display $4000-$4003 values
    LDA $4000
    JSR debug_print_hex_byte
    LDA #' '
    STA $2007
    LDA $4001
    JSR debug_print_hex_byte
    LDA #' '
    STA $2007
    LDA $4002
    JSR debug_print_hex_byte
    LDA #' '
    STA $2007
    LDA $4003
    JSR debug_print_hex_byte

    ; Similar for other channels...
    RTS

apu_pulse1_label:
    .byte "P1: ", $00

"""

    def generate_memory_viewer(self) -> str:
        """Generate memory viewer for debugging.

        Returns:
            CA65 assembly code for memory viewer
        """
        if not self.enable_overlay:
            return "; Memory viewer disabled\n"

        return """; ============================================
; Memory Viewer
; Shows a window of memory on screen
; ============================================

debug_memory_view_addr: .res 2  ; 16-bit address to view

; Display 8 bytes of memory starting at debug_memory_view_addr
debug_show_memory:
    ; Display address label (row 10)
    LDA $2002
    LDA #$21
    STA $2006
    LDA #$80  ; Row 10
    STA $2006

    ; "MEM: "
    LDA #'M'
    STA $2007
    LDA #'E'
    STA $2007
    LDA #'M'
    STA $2007
    LDA #':'
    STA $2007
    LDA #' '
    STA $2007

    ; Display address
    LDA debug_memory_view_addr+1
    JSR debug_print_hex_byte
    LDA debug_memory_view_addr
    JSR debug_print_hex_byte

    LDA #' '
    STA $2007

    ; Display 8 bytes
    LDY #$00
@mem_loop:
    LDA (debug_memory_view_addr), Y
    JSR debug_print_hex_byte
    LDA #' '
    STA $2007
    INY
    CPY #$08
    BNE @mem_loop

    RTS

"""

    def generate_full_debug_system(self) -> str:
        """Generate complete debug system.

        Returns:
            Complete CA65 assembly code for debug overlay system
        """
        parts = [
            "; ============================================",
            "; MIDI2NES Debug Overlay System",
            "; Generated automatically - provides on-screen debugging",
            "; ============================================",
            "",
            self.generate_debug_init(),
            self.generate_debug_update(),
            self.generate_debug_error_handler(),
            self.generate_apu_diagnostics(),
            self.generate_memory_viewer(),
        ]

        return "\n".join(parts)


def create_debug_rom_variant(music_asm_path: str, output_path: str):
    """Create a debug variant of the ROM with overlay enabled.

    Args:
        music_asm_path: Path to the music.asm file
        output_path: Path to write debug variant
    """
    overlay = NESDebugOverlay(enable_overlay=True)

    # Read original music.asm
    with open(music_asm_path, 'r') as f:
        music_asm = f.read()

    # Generate debug system
    debug_system = overlay.generate_full_debug_system()

    # Combine
    debug_asm = f"""{music_asm}

; ============================================
; DEBUG OVERLAY INJECTED BELOW
; ============================================

{debug_system}
"""

    # Write debug variant
    with open(output_path, 'w') as f:
        f.write(debug_asm)

    print(f"Debug variant created: {output_path}")
    print("This ROM will display:")
    print("  - APU channel status (P1, P2, Triangle, Noise)")
    print("  - Frame counter")
    print("  - Error codes and messages")
    print("  - Memory viewer")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python debug_overlay.py <music.asm> <output_debug.asm>")
        sys.exit(1)

    create_debug_rom_variant(sys.argv[1], sys.argv[2])
