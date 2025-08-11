; Enhanced NES Music ROM - Full MIDI support
; Fixed ROM structure with proper memory mapping

.segment "HEADER"
    .byte "NES", $1A   ; iNES header
    .byte $08          ; 8 x 16KB PRG ROM banks (128KB total)
    .byte $00          ; 0 x 8KB CHR ROM (CHR-RAM)
    .byte $10          ; Mapper 1 (MMC1), horizontal mirroring
    .byte $00, $00, $00, $00, $00, $00, $00, $00  ; Padding

.segment "ZEROPAGE"
frame_counter: .res 2  ; 16-bit counter for longer songs
song_loop_count: .res 1

.segment "CODE"

reset:
    ; Standard NES initialization
    sei                   ; Disable interrupts
    cld                   ; Clear decimal mode
    ldx #$FF
    txs                   ; Set up stack
    
    ; MMC1 initialization
    lda #$80
    sta $8000             ; Reset MMC1
    
    ; Configure MMC1 - 32KB PRG mode, CHR-RAM
    lda #$0E              ; 32KB PRG mode, horizontal mirroring
    sta $8000             ; Write bit 0
    lsr
    sta $8000             ; Write bit 1
    lsr
    sta $8000             ; Write bit 2
    lsr
    sta $8000             ; Write bit 3
    lsr
    sta $8000             ; Write bit 4
    
    ; PPU warmup - wait for two vblanks
    bit $2002
wait_vbl1:
    bit $2002
    bpl wait_vbl1
wait_vbl2:
    bit $2002
    bpl wait_vbl2
    
    ; APU initialization
    lda #$00
    sta $4015             ; Disable all channels
    lda #$40
    sta $4017             ; Disable frame IRQ
    lda #$0F
    sta $4015             ; Enable pulse1, pulse2, triangle, noise
    
    ; Initialize variables
    lda #$00
    sta frame_counter
    sta frame_counter+1
    sta song_loop_count
    
    ; Enable NMI for timing
    lda #$80
    sta $2000
    
main_loop:
    jmp main_loop         ; Wait for NMI

nmi:
    ; Save registers
    pha
    txa
    pha
    tya
    pha
    
    ; Play current frame
    jsr play_all_channels
    
    ; Increment frame counter
    inc frame_counter
    bne no_carry
    inc frame_counter+1
no_carry:
    
    ; Check for song end and loop
    lda frame_counter+1
    bne check_loop        ; High byte non-zero
    lda frame_counter
    cmp #23
    bcc nmi_done
check_loop:
    ; Reset song
    lda #$00
    sta frame_counter
    sta frame_counter+1
    inc song_loop_count
nmi_done:
    ; Restore registers
    pla
    tay
    pla
    tax
    pla
    rti

play_all_channels:
    jsr play_pulse1
    jsr play_pulse2
    jsr play_triangle
    rts

play_pulse1:
    ; Frame 2 - Pulse1 Note 60
    lda frame_counter
    cmp #2
    bne @skip_p1_0
    lda frame_counter+1
    cmp #0
    bne @skip_p1_0
    
    lda #152
    sta $4000
    lda #170
    sta $4002
    lda #9
    sta $4003
@skip_p1_0:
    ; Frame 3 - Pulse1 Note 60
    lda frame_counter
    cmp #3
    bne @skip_p1_1
    lda frame_counter+1
    cmp #0
    bne @skip_p1_1
    
    lda #152
    sta $4000
    lda #170
    sta $4002
    lda #9
    sta $4003
@skip_p1_1:
    ; Frame 4 - Pulse1 Note 60
    lda frame_counter
    cmp #4
    bne @skip_p1_2
    lda frame_counter+1
    cmp #0
    bne @skip_p1_2
    
    lda #152
    sta $4000
    lda #170
    sta $4002
    lda #9
    sta $4003
@skip_p1_2:
    ; Frame 5 - Pulse1 Note 60
    lda frame_counter
    cmp #5
    bne @skip_p1_3
    lda frame_counter+1
    cmp #0
    bne @skip_p1_3
    
    lda #152
    sta $4000
    lda #170
    sta $4002
    lda #9
    sta $4003
@skip_p1_3:
    ; Frame 6 - Pulse1 Note 62
    lda frame_counter
    cmp #6
    bne @skip_p1_4
    lda frame_counter+1
    cmp #0
    bne @skip_p1_4
    
    lda #152
    sta $4000
    lda #123
    sta $4002
    lda #9
    sta $4003
@skip_p1_4:
    ; Frame 7 - Pulse1 Note 62
    lda frame_counter
    cmp #7
    bne @skip_p1_5
    lda frame_counter+1
    cmp #0
    bne @skip_p1_5
    
    lda #152
    sta $4000
    lda #123
    sta $4002
    lda #9
    sta $4003
@skip_p1_5:
    ; Frame 8 - Pulse1 Note 62
    lda frame_counter
    cmp #8
    bne @skip_p1_6
    lda frame_counter+1
    cmp #0
    bne @skip_p1_6
    
    lda #152
    sta $4000
    lda #123
    sta $4002
    lda #9
    sta $4003
@skip_p1_6:
    ; Frame 9 - Pulse1 Note 62
    lda frame_counter
    cmp #9
    bne @skip_p1_7
    lda frame_counter+1
    cmp #0
    bne @skip_p1_7
    
    lda #152
    sta $4000
    lda #123
    sta $4002
    lda #9
    sta $4003
@skip_p1_7:
    ; Frame 10 - Pulse1 Note 64
    lda frame_counter
    cmp #10
    bne @skip_p1_8
    lda frame_counter+1
    cmp #0
    bne @skip_p1_8
    
    lda #152
    sta $4000
    lda #82
    sta $4002
    lda #9
    sta $4003
@skip_p1_8:
    ; Frame 11 - Pulse1 Note 64
    lda frame_counter
    cmp #11
    bne @skip_p1_9
    lda frame_counter+1
    cmp #0
    bne @skip_p1_9
    
    lda #152
    sta $4000
    lda #82
    sta $4002
    lda #9
    sta $4003
@skip_p1_9:
    ; Frame 12 - Pulse1 Note 64
    lda frame_counter
    cmp #12
    bne @skip_p1_10
    lda frame_counter+1
    cmp #0
    bne @skip_p1_10
    
    lda #152
    sta $4000
    lda #82
    sta $4002
    lda #9
    sta $4003
@skip_p1_10:
    ; Frame 13 - Pulse1 Note 64
    lda frame_counter
    cmp #13
    bne @skip_p1_11
    lda frame_counter+1
    cmp #0
    bne @skip_p1_11
    
    lda #152
    sta $4000
    lda #82
    sta $4002
    lda #9
    sta $4003
@skip_p1_11:
    rts

play_pulse2:
    ; No pulse2 data
    rts

play_triangle:
    ; No triangle data
    rts

irq:
    rti

; Interrupt vectors
.segment "VECTORS"
    .word nmi            ; NMI vector ($FFFA)
    .word reset          ; Reset vector ($FFFC)
    .word irq            ; IRQ/BRK vector ($FFFE)
