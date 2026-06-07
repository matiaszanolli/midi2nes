; ---------------------------------------------------------------------------
; midi2nes MMC3 Initialization and Driver Core
; Resides permanently in the fixed $E000-$FFFF bank
; ---------------------------------------------------------------------------

.segment "CODE"

.export reset_handler, nmi_handler, irq_handler

; ---------------------------------------------------------------------------
; reset_handler: Executed on console power-up or reset button press
; ---------------------------------------------------------------------------
.proc reset_handler
    SEI                 ; Disable IRQs
    CLD                 ; Disable decimal mode (NES 6502 quirk)

    ; Initialize Stack Pointer
    LDX #$FF
    TXS

    ; 1. Initialize MMC3 Mapper
    STA $E000           ; Disable MMC3 scanline IRQs and acknowledge
    
    ; Set PRG Bank Mode 1 (P=1) -> $8000 fixed, $C000 swappable
    ; We write %01000110 ($46) to set Mode 1 and select Register 6 ($C000 bank)
    LDA #$46
    STA $8000
    LDA #$00            ; Map Bank 0 into the swappable $C000-$DFFF window
    STA $8001

    ; We write %01000111 ($47) to set Mode 1 and select Register 7 ($A000 bank)
    LDA #$47
    STA $8000
    LDA #$01            ; Map Bank 1 into the swappable $A000-$BFFF window
    STA $8001

    ; 2. Wait for PPU Warmup (Frame 1)
@vblankwait1:
    BIT $2002
    BPL @vblankwait1

    ; 3. Clear Internal RAM ($0000 - $07FF)
    LDA #$00
    TAX
@clear_ram:
    STA $0000, X
    STA $0200, X
    STA $0300, X
    STA $0400, X
    STA $0500, X
    STA $0600, X
    STA $0700, X
    INX
    BNE @clear_ram

    ; 4. Wait for PPU Warmup (Frame 2)
@vblankwait2:
    BIT $2002
    BPL @vblankwait2

    ; 5. APU Safe Initialization
    LDA #$40
    STA $4017           ; Disable APU Frame Counter IRQs (Mode 1)

    LDA #$0F
    STA $4015           ; Enable Pulse 1, Pulse 2, Triangle, and Noise (DMC disabled for now)

    LDA #$00
    STA $4011           ; Reset DMC DAC to 0 (Prevents Triangle/Noise compression bug)
    STA $4010           ; Clear DMC flags / IRQs

    LDA #$08
    STA $4001           ; Disable Pulse 1 Sweep (Prevents low-octave muting bug)
    STA $4005           ; Disable Pulse 2 Sweep

    ; 6. Start the Engine!
    JSR audio_init
    
    LDA #$80
    STA $2000           ; Enable NMI (Triggering our 60Hz audio updates)

@forever:
    JMP @forever        ; Idle loop, all actual processing happens in the NMI
.endproc

; ---------------------------------------------------------------------------
; Standard Interrupt Handlers
; ---------------------------------------------------------------------------
.proc nmi_handler
    PHA                 ; Push A
    TXA
    PHA                 ; Push X
    TYA
    PHA                 ; Push Y

    JSR audio_update

    PLA                 ; Pull Y
    TAY
    PLA                 ; Pull X
    TAX
    PLA                 ; Pull A
    RTI                 ; Return from Interrupt
.endproc

.proc irq_handler
    RTI                 ; We do not use IRQs, just return safely
.endproc

; ---------------------------------------------------------------------------
; Hardware Vectors (Must reside at the very end of the ROM: $FFFA-$FFFF)
; ---------------------------------------------------------------------------
.segment "VECTORS"
    .word nmi_handler   ; $FFFA
    .word reset_handler ; $FFFC
    .word irq_handler   ; $FFFE