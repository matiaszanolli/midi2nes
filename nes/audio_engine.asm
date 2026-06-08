; ---------------------------------------------------------------------------
; midi2nes Macro Audio Engine (Sequencer)
; ---------------------------------------------------------------------------
.import pulse1_sequence, pulse2_sequence, triangle_sequence, noise_sequence, dpcm_sequence
.import ntsc_period_low, ntsc_period_high
.import dpcm_bank_table, dpcm_pitch_table, dpcm_addr_table, dpcm_len_table
.import instrument_table
.import fetch_sequence_byte

.segment "ZEROPAGE"
ptr1:           .res 2

.exportzp ptr1, temp1, temp2, frame_counter
temp1:          .res 1
temp2:          .res 1
frame_counter:  .res 2

; 5 channels: 0=Pulse1, 1=Pulse2, 2=Triangle, 3=Noise, 4=DMC
stream_ptr_lo:  .res 5
stream_ptr_hi:  .res 5
stream_bank:    .res 5
frame_wait:     .res 5
current_len:    .res 5
current_note:   .res 5
current_inst:   .res 5
macro_steps:    .res 20 ; 0-4=Vol, 5-9=Arp, 10-14=Pitch, 15-19=Duty

; Locals for macro processing
temp_vol:       .res 1
temp_arp:       .res 1
temp_duty:      .res 1
temp_note:      .res 1
temp_pitch:     .res 1
temp_pitch_hi:  .res 1
temp_inst_off:  .res 1
temp_inst_base: .res 1

.segment "CODE"
.export audio_init, audio_update

audio_init:
    ; Initialize sequence pointers from the exported CA65 labels
    lda #<pulse1_sequence
    sta stream_ptr_lo+0
    lda #>pulse1_sequence
    sta stream_ptr_hi+0
    lda #$00
    sta stream_bank+0
    
    lda #<pulse2_sequence
    sta stream_ptr_lo+1
    lda #>pulse2_sequence
    sta stream_ptr_hi+1
    lda #$00
    sta stream_bank+1
    
    lda #<triangle_sequence
    sta stream_ptr_lo+2
    lda #>triangle_sequence
    sta stream_ptr_hi+2
    lda #$00
    sta stream_bank+2
    
    lda #<noise_sequence
    sta stream_ptr_lo+3
    lda #>noise_sequence
    sta stream_ptr_hi+3
    lda #$00
    sta stream_bank+3
    
    lda #<dpcm_sequence
    sta stream_ptr_lo+4
    lda #>dpcm_sequence
    sta stream_ptr_hi+4
    lda #$00
    sta stream_bank+4
    
    ; Clear macro steps
    ldx #19
@clear_macros:
    lda #0
    sta macro_steps, x
    dex
    bpl @clear_macros
    
    ; Initialize frame counter
    lda #0
    sta frame_counter
    sta frame_counter+1

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
    inc frame_counter
    bne :+
    inc frame_counter+1
:
    ldx #0
@channel_loop:
    lda frame_wait, x
    beq @fetch_byte       ; If wait is 0, fetch a new bytecode instruction
    dec frame_wait, x     ; Otherwise, tick down the timer and process macros
    jmp @process_macros
    
@fetch_byte:
    lda stream_ptr_lo, x
    sta sequence_ptr
    lda stream_ptr_hi, x
    sta sequence_ptr+1
    lda stream_bank, x
    sta sequence_bank
    
@read_next:
    jsr fetch_sequence_byte

    cmp #$FF
    bne :+
    jmp @end_of_stream ; Halt sequence if end marker $FF is hit
:   
    cmp #$60
    bcc @is_note
    cmp #$80
    bcc @is_length
    
@is_command:
    ; Handle commands ($80 - $FE)
    cmp #$FE
    beq @cmd_bank_jump
    cmp #$80
    bne @unknown_command

    ; CMD_INSTRUMENT ($80 followed by 1 parameter byte)
    jsr fetch_sequence_byte
    sta current_inst, x
    jmp @read_next
    
@cmd_bank_jump:
    ; CMD_BANK_JUMP ($FE followed by bank, addr_low, addr_high)
    jsr fetch_sequence_byte
    sta sequence_bank
    sta stream_bank, x
    
    jsr fetch_sequence_byte
    pha                     ; Save low byte
    
    jsr fetch_sequence_byte
    sta sequence_ptr+1      ; Write high byte
    sta stream_ptr_hi, x
    
    pla
    sta sequence_ptr        ; Write low byte
    sta stream_ptr_lo, x
    
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
    
    ; Reset all macro sequence steps to 0
    lda #0
    sta macro_steps, x       ; Vol step
    sta macro_steps+5, x     ; Arp step
    sta macro_steps+10, x    ; Pitch step
    sta macro_steps+15, x    ; Duty step
    
    lda current_len, x
    sta frame_wait, x
    ; Wait length-1 frames since we process and play immediately on this frame
    dec frame_wait, x 
    
    ; Save the advanced pointer
    lda sequence_ptr
    sta stream_ptr_lo, x
    lda sequence_ptr+1
    sta stream_ptr_hi, x
    
@process_macros:
    ; ---------------------------------------------------------
    ; Synthesizer Phase (Macro Evaluation & Hardware Write)
    ; ---------------------------------------------------------
    lda current_note, x
    bne :+
    jmp @silence
:
    ; 1. Volume Macro
    lda #0                  ; Offset 0 in instrument table (Volume)
    sta temp_inst_off
    txa                     ; macro_steps index (x)
    sta temp1
    lda #15                 ; Default value if null
    sta temp2
    lda temp_inst_off
    jsr read_macro
    sta temp_vol
    
    ; 2. Arpeggio Macro
    lda #2                  ; Offset 2 in instrument table (Arp)
    sta temp_inst_off
    txa
    clc
    adc #5                  ; macro_steps index (x + 5)
    sta temp1
    lda #0                  ; Default value if null
    sta temp2
    lda temp_inst_off
    jsr read_macro
    clc
    adc current_note, x     ; Add arp offset to base note
    sta temp_note
    
    ; 3. Duty Macro
    lda #6                  ; Offset 6 in instrument table (Duty)
    sta temp_inst_off
    txa
    clc
    adc #15                 ; macro_steps index (x + 15)
    sta temp1
    lda #2                  ; Default value if null (50% duty)
    sta temp2
    lda temp_inst_off
    jsr read_macro
    sta temp_duty
    
    ; 4. Pitch Macro
    lda #4                  ; Offset 4 in instrument table (Pitch)
    sta temp_inst_off
    txa
    clc
    adc #10                 ; macro_steps index (x + 10)
    sta temp1
    lda #0                  ; Default value if null
    sta temp2
    lda temp_inst_off
    jsr read_macro
    sta temp_pitch

    ; Sign extend pitch into temp_pitch_hi (for 16-bit signed addition)
    lda temp_pitch
    bpl @positive_pitch
    lda #$FF
    jmp @store_pitch_hi
@positive_pitch:
    lda #0
@store_pitch_hi:
    sta temp_pitch_hi
    
    ; Write to Hardware
    ldy temp_note
    cpx #0
    bne :+
    jmp @write_pulse1
:   cpx #1
    bne :+
    jmp @write_pulse2
:   cpx #2
    bne :+
    jmp @write_triangle
:   cpx #3
    bne :+
    jmp @write_noise
:   cpx #4
    bne :+
    jmp @write_dpcm
:   jmp @next_channel

@write_pulse1:
    lda temp_duty
    asl
    asl
    asl
    asl
    asl
    asl           ; Shift duty bits into D7, D6
    ora #$30      ; Constant volume flag
    ora temp_vol
    sta $4000
    
    lda ntsc_period_low, y
    clc
    adc temp_pitch
    sta $4002
    lda ntsc_period_high, y
    adc temp_pitch_hi
    ora #$08      ; Length counter halt
    sta $4003
    jmp @next_channel
    
@write_pulse2:
    lda temp_duty
    asl
    asl
    asl
    asl
    asl
    asl           ; Shift duty bits into D7, D6
    ora #$30      ; Constant volume flag
    ora temp_vol
    sta $4004
    
    lda ntsc_period_low, y
    clc
    adc temp_pitch
    sta $4006
    lda ntsc_period_high, y
    adc temp_pitch_hi
    ora #$08
    sta $4007
    jmp @next_channel
    
@write_triangle:
    lda temp_vol
    beq @silence_tri
    
    lda #$FF      ; Halt length/linear counter, max volume
    sta $4008
    lda ntsc_period_low, y
    clc
    adc temp_pitch
    sta $400A
    lda ntsc_period_high, y
    adc temp_pitch_hi
    ora #$08
    sta $400B
    jmp @next_channel
    
@silence_tri:
    lda #$80      ; Linear Counter Halt (Safely Silences Triangle)
    sta $4008
    jmp @next_channel

@write_noise:
    lda #$30      ; Constant volume flag & Length counter halt
    ora temp_vol
    sta $400C
    
    lda temp_duty
    lsr           ; Shift lowest bit of duty macro (Noise Mode) into carry
    lda temp_note
    and #$0F      ; Mask pitch down to 4-bit Period Index
    bcc :+
    ora #$80      ; Set Mode flag if duty bit was 1
:   sta $400E
    
    lda #$08      ; Length counter load (resets envelope phase safely)
    sta $400F
    jmp @next_channel

@write_dpcm:
    ; current_note, x represents sample_id + 1
    lda current_note, x
    sec
    sbc #1
    tay

    ; Stop any playing DPCM first to reset the byte counter
    lda #$0F
    sta $4015

    ; --- Hot-Swap DPCM Bank into $C000 ---
    lda #$46                ; MMC3 PRG Bank Mode 1, Register 6
    sta $8000
    lda dpcm_bank_table, y  ; Fetch the bank number for this sample
    sta $8001

    ; Load sample parameters
    lda dpcm_pitch_table, y
    sta $4010
    lda dpcm_addr_table, y
    sta $4012
    lda dpcm_len_table, y
    sta $4013
    
    ; Trigger playback
    lda #$1F
    sta $4015
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
    jmp @next_channel
:   cpx #3
    bne :+
    lda #$30      ; Silence Noise
    sta $400C
    jmp @next_channel
:   cpx #4
    bne :+
    ; We don't force stop DPCM for note-offs, we let the sample ring out naturally.
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

; ---------------------------------------------------------------------------
; read_macro subroutine
; ---------------------------------------------------------------------------
; Inputs:
; A = Offset in instrument table (0=Vol, 2=Arp, 4=Pitch, 6=Duty)
; temp1 = Index into macro_steps array
; temp2 = Default value to return if the macro is null ($FF on step 0)
; Returns: Evaluated macro value in A
; ---------------------------------------------------------------------------
read_macro:
    sta temp_inst_off
    
    ; inst_base = current_inst[x] * 8
    lda current_inst, x
    asl
    asl
    asl
    sta temp_inst_base
    
    ; Y = inst_base + offset
    lda temp_inst_base
    clc
    adc temp_inst_off
    tay
    
    ; ptr1 = address of the actual macro array
    lda instrument_table, y
    sta ptr1
    lda instrument_table+1, y
    sta ptr1+1
    
    ; Save channel index
    txa
    pha
    
    ; Get current step for this macro
    ldx temp1
    lda macro_steps, x
    tay
    
    ; Read the macro byte
    lda (ptr1), y
    cmp #$FF
    bne @not_end
    
    ; Macro ended or is null
    cpy #0
    beq @is_null
    
    ; Not step 0, sustain previous value
    dey
    lda (ptr1), y
    rts
    
@is_null:
    lda temp2
    jmp @done_macro
    
@not_end:
    ; Increment step counter
    inc macro_steps, x
    
    lda (ptr1), y
    
@done_macro:
    ; Save result, restore channel index, and return
    sta temp2
    pla
    tax
    lda temp2
    rts