; simple_test_engine.s - Minimal working NES music engine for debugging
; This engine plays a simple C major scale to test the APU

.segment "HEADER"
    .byte "NES", $1A        ; NES header signature  
    .byte $02               ; 32KB PRG-ROM (2 x 16KB)
    .byte $00               ; No CHR-ROM
    .byte $00               ; Mapper 0, horizontal mirroring
    .res 8, $00             ; Padding

.segment "ZEROPAGE"
    frame_counter: .res 2   ; Global frame counter
    note_index:    .res 1   ; Current note in scale

.segment "CODE"

; Reset vector entry point
reset:
    sei                     ; Disable interrupts
    cld                     ; Clear decimal mode
    ldx #$FF
    txs                     ; Set up stack
    
    ; Initialize variables
    lda #$00
    sta frame_counter
    sta frame_counter+1
    sta note_index
    
    ; Initialize APU
    jsr init_music
    
    ; Main loop
main_loop:
    jsr update_music
    jmp main_loop

; Initialize the APU for audio output
init_music:
    ; Enable all audio channels
    lda #$0F
    sta $4015
    
    ; Set up Pulse 1: 50% duty cycle, constant volume, volume=15
    lda #$BF                ; %10111111 = 50% duty + constant vol + vol=15
    sta $4000
    
    ; No sweep
    lda #$00
    sta $4001
    
    ; Set up Pulse 2 similarly
    lda #$BF
    sta $4004
    lda #$00
    sta $4005
    
    ; Set up Triangle: linear counter enabled
    lda #$81                ; Linear counter = 1
    sta $4008
    
    ; Set up Noise: constant volume=8
    lda #$38                ; %00111000 = constant vol + vol=8
    sta $400C
    
    rts

; Update music - called every frame
update_music:
    ; Increment frame counter
    inc frame_counter
    bne :+
    inc frame_counter+1
:
    
    ; Play a new note every 30 frames (0.5 seconds at 60 FPS)
    lda frame_counter
    and #%00011111          ; Check if frame_counter % 32 == 0
    bne skip_note_change
    
    ; Time to change notes
    ldx note_index
    
    ; Play note on Pulse 1
    lda scale_notes_low,x
    sta $4002               ; Timer low
    lda scale_notes_high,x
    ora #$08                ; Reset length counter
    sta $4003               ; Timer high + length reset
    
    ; Advance to next note
    inc note_index
    lda note_index
    cmp #8                  ; 8 notes in scale
    bcc skip_note_change
    lda #0                  ; Reset to first note
    sta note_index
    
skip_note_change:
    rts

; NES Interrupt handlers
nmi:
    rti

irq:
    rti

.segment "RODATA"

; C Major Scale - NES Timer Values
; Formula: timer = (CPU_CLOCK / (16 * frequency)) - 1
; C4=261.6Hz, D4=293.7Hz, E4=329.6Hz, F4=349.2Hz, G4=392.0Hz, A4=440.0Hz, B4=493.9Hz, C5=523.3Hz
scale_notes_low:
    .byte $AB, $5F, $FE, $DC, $6B, $FE, $31, $FE  ; Low bytes
scale_notes_high:  
    .byte $01, $01, $00, $00, $01, $00, $01, $00   ; High bytes

.segment "VECTORS"
    .word nmi               ; NMI vector
    .word reset             ; Reset vector  
    .word irq               ; IRQ vector
