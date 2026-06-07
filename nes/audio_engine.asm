; ---------------------------------------------------------------------------
; midi2nes Macro Audio Engine (Sequencer)
; ---------------------------------------------------------------------------
.segment "ZEROPAGE"
ptr1:           .res 2

; 5 channels: 0=Pulse1, 1=Pulse2, 2=Triangle, 3=Noise, 4=DMC
stream_ptr_lo:  .res 5
stream_ptr_hi:  .res 5
frame_wait:     .res 5
current_len:    .res 5
current_note:   .res 5
current_inst:   .res 5

.segment "CODE"
.export audio_init, audio_update

audio_init:
    ; Initialize sequence pointers from the exported CA65 labels
    lda #<pulse1_sequence
    sta stream_ptr_lo+0
    lda #>pulse1_sequence
    sta stream_ptr_hi+0
    
    lda #<pulse2_sequence
    sta stream_ptr_lo+1
    lda #>pulse2_sequence
    sta stream_ptr_hi+1
    
    lda #<triangle_sequence
    sta stream_ptr_lo+2
    lda #>triangle_sequence
    sta stream_ptr_hi+2
    
    lda #<noise_sequence
    sta stream_ptr_lo+3
    lda #>noise_sequence
    sta stream_ptr_hi+3
    
    lda #<dpcm_sequence
    sta stream_ptr_lo+4
    lda #>dpcm_sequence
    sta stream_ptr_hi+4
    
    ; Clear internal channel state
    ldx #4
@clear_loop:
    lda #1
    sta current_len, x
    lda #0
    sta frame_wait, x
    sta current_note, x
    dex
    bpl @clear_loop
    rts
    
audio_update:
    ldx #0
@channel_loop:
    lda frame_wait, x
    beq @fetch_byte       ; If wait is 0, fetch a new bytecode instruction
    dec frame_wait, x     ; Otherwise, tick down the timer and process macros
    jmp @process_macros
    
@fetch_byte:
    lda stream_ptr_lo, x
    sta ptr1
    lda stream_ptr_hi, x
    sta ptr1+1
    
    ldy #0
@read_next:
    lda (ptr1), y
    inc ptr1
    bne :+
    inc ptr1+1
:   
    cmp #$FF
    beq @end_of_stream ; Halt sequence if end marker $FF is hit
    
    cmp #$60
    bcc @is_note
    cmp #$80
    bcc @is_length
    
@is_command:
    ; Handle commands ($80 - $FE)
    cmp #$80
    bne @unknown_command
    ; CMD_INSTRUMENT ($80 followed by 1 parameter byte)
    lda (ptr1), y
    sta current_inst, x
    inc ptr1
    bne @read_next
    inc ptr1+1
    jmp @read_next
    
@unknown_command:
    jmp @end_of_stream ; Safely skip to end if command is unknown to avoid crashing
    
@is_length:
    sec
    sbc #$60
    clc
    adc #1
    sta current_len, x
    jmp @read_next
    
@is_note:
    sta current_note, x
    lda current_len, x
    sta frame_wait, x
    ; Wait length-1 frames since we process and play the note immediately on this frame
    dec frame_wait, x 
    
    ; Save the advanced pointer
    lda ptr1
    sta stream_ptr_lo, x
    lda ptr1+1
    sta stream_ptr_hi, x
    
@process_macros:
    ; ---------------------------------------------------------
    ; Synthesizer Phase (Hardware Write)
    ; (Volume, Arpeggio, Duty, and Pitch macros will be added here in Step 2)
    ; ---------------------------------------------------------
    lda current_note, x
    beq @silence
    
    tay
    
    cpx #0
    beq @write_pulse1
    cpx #1
    beq @write_pulse2
    cpx #2
    beq @write_triangle
    jmp @next_channel ; Noise/DMC handled later
    
@write_pulse1:
    lda #$BF      ; Duty 50%, Constant Vol 15
    sta $4000
    lda ntsc_period_low, y
    sta $4002
    lda ntsc_period_high, y
    ora #$08      ; Length counter halt
    sta $4003
    jmp @next_channel
    
@write_pulse2:
    lda #$BF      ; Duty 50%, Constant Vol 15
    sta $4004
    lda ntsc_period_low, y
    sta $4006
    lda ntsc_period_high, y
    ora #$08
    sta $4007
    jmp @next_channel
    
@write_triangle:
    lda #$FF      ; Halt length/linear counter, max volume
    sta $4008
    lda ntsc_period_low, y
    sta $400A
    lda ntsc_period_high, y
    ora #$08
    sta $400B
    jmp @next_channel
    
@silence:
    cpx #0
    bne :+
    lda #$30
    sta $4000
    jmp @next_channel
:   cpx #1
    bne :+
    lda #$30
    sta $4004
    jmp @next_channel
:   cpx #2
    bne :+
    lda #$80      ; Linear Counter Halt (Safely Silences Triangle)
    sta $4008
:   
    jmp @next_channel
    
@end_of_stream:
    ; Sequence finished, leave wait counter at 0
    
@next_channel:
    inx
    cpx #5
    beq @done
    jmp @channel_loop
    
@done:
    rts