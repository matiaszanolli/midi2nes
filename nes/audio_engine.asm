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

.segment "BSS"

; 5 channels: 0=Pulse1, 1=Pulse2, 2=Triangle, 3=Noise, 4=DMC
stream_ptr_lo:  .res 5
stream_ptr_hi:  .res 5
stream_bank:    .res 5
frame_wait:     .res 5
current_len:    .res 5
current_note:   .res 5
current_inst:   .res 5
macro_steps_vol:    .res 5
macro_steps_arp:    .res 5
macro_steps_pitch:  .res 5
macro_steps_duty:   .res 5

.segment "ZEROPAGE"

; Locals for macro processing
temp_vol:       .res 1
temp_arp:       .res 1
temp_duty:      .res 1
temp_note:      .res 1
temp_pitch:     .res 1
temp_pitch_hi:  .res 1
temp_inst_base: .res 1

.segment "CODE"
.export audio_init, audio_update

; ---------------------------------------------------------------------------
; Inline Macro Evaluator (Replaces the slow read_macro subroutine)
; ---------------------------------------------------------------------------
.macro EVAL_MACRO inst_offset, step_array, default_val, out_var
    .local @not_end
    .local @is_null
    .local @done
    
    ldy temp_inst_base
    lda instrument_table+inst_offset, y
    sta ptr1
    lda instrument_table+inst_offset+1, y
    sta ptr1+1
    
    lda step_array, x
    tay
    lda (ptr1), y
    cmp #$FF
    bne @not_end
    
    cpy #0
    beq @is_null
    dey
    lda (ptr1), y
    jmp @done
@is_null:
    lda #default_val
    jmp @done
@not_end:
    inc step_array, x
    lda (ptr1), y
@done:
    sta out_var
.endmacro

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
    
    ; Initialize DMC output level to 0 to prevent muffling Triangle/Noise
    sta $4011
    
    ; Clear macro steps
    ldx #4
@clear_macros:
    lda #0
    sta macro_steps_vol, x
    sta macro_steps_arp, x
    sta macro_steps_pitch, x
    sta macro_steps_duty, x
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
    cmp #$85
    beq @cmd_dpcm_play
    cmp #$87
    beq @cmd_dmc_level
    cmp #$80
    bne @unknown_command

    ; CMD_INSTRUMENT ($80 followed by 1 parameter byte)
    jsr fetch_sequence_byte
    sta current_inst, x
    jmp @read_next
    
@cmd_dpcm_play:
    ; CMD_DPCM_PLAY ($85 followed by 1 parameter byte: sample_id)
    jsr fetch_sequence_byte
    tay                     ; Move sample_id into Y for table lookups
    
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
    jmp @read_next

@cmd_dmc_level:
    ; CMD_DMC_LEVEL ($87 followed by 1 parameter byte: 7-bit level)
    jsr fetch_sequence_byte
    and #$7F                ; Clamp to 7 bits (0-127) for safety
    sta $4011
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
    sta macro_steps_vol, x
    sta macro_steps_arp, x
    sta macro_steps_pitch, x
    sta macro_steps_duty, x
    
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
    ; Skip all macros for DPCM (Channel 4)
    cpx #4
    bne :+
    jmp @write_dpcm
:
    ; Precalculate the instrument pointer offset for this channel
    lda current_inst, x
    asl
    asl
    asl
    sta temp_inst_base
    
    ; All remaining channels (0,1,2,3) use Volume and Arpeggio
    EVAL_MACRO 0, macro_steps_vol, 15, temp_vol
    EVAL_MACRO 2, macro_steps_arp, 0, temp_arp
    
    clc
    lda current_note, x
    adc temp_arp     ; Add arp offset to base note
    sta temp_note
    
    ; Triangle (2) ignores Duty. Pulse 1/2 (0,1) and Noise (3) use Duty.
    cpx #2
    beq @skip_duty
    EVAL_MACRO 6, macro_steps_duty, 2, temp_duty
@skip_duty:

    ; Noise (3) ignores Pitch. Pulse 1/2 (0,1) and Triangle (2) use Pitch.
    cpx #3
    beq @skip_pitch
    EVAL_MACRO 4, macro_steps_pitch, 0, temp_pitch
    
    lda temp_pitch
    beq @skip_pitch    ; Skip 16-bit sign extension if pitch offset is 0
    bpl :+
    lda #$FF           ; Sign extend negative pitch
    .byte $2C          ; BIT absolute (Skip next 2 bytes / lda #0)
:   lda #0             ; Sign extend positive pitch
    sta temp_pitch_hi
@skip_pitch:
    
    ; Write to Hardware
    ldy temp_note
    cpx #0
    beq @write_pulse1
    cpx #1
    beq @write_pulse2
    cpx #2
    beq @write_triangle
    jmp @write_noise

@write_pulse1:
    lda temp_duty
    lsr
    ror
    ror           ; Fast shift duty bits 0-1 into D6-D7
    ora #$30      ; Constant volume flag
    ora temp_vol
    sta $4000
    
    lda temp_pitch
    bne @p1_pitch_mod
    ; Fast path: No pitch bend, avoid 16-bit math
    lda ntsc_period_low, y
    sta $4002
    lda ntsc_period_high, y
    ora #$08
    sta $4003
    jmp @next_channel
@p1_pitch_mod:
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
    lsr
    ror
    ror           ; Fast shift duty bits 0-1 into D6-D7
    ora #$30      ; Constant volume flag
    ora temp_vol
    sta $4004
    
    lda temp_pitch
    bne @p2_pitch_mod
    ; Fast path: No pitch bend, avoid 16-bit math
    lda ntsc_period_low, y
    sta $4006
    lda ntsc_period_high, y
    ora #$08
    sta $4007
    jmp @next_channel
@p2_pitch_mod:
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
    
    lda temp_pitch
    bne @tri_pitch_mod
    ; Fast path: No pitch bend, avoid 16-bit math
    lda ntsc_period_low, y
    sta $400A
    lda ntsc_period_high, y
    ora #$08
    sta $400B
    jmp @next_channel
@tri_pitch_mod:
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