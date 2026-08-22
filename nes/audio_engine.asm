; ---------------------------------------------------------------------------
; midi2nes Macro Audio Engine (Sequencer)
; ---------------------------------------------------------------------------
.import pulse1_sequence, pulse2_sequence, triangle_sequence, noise_sequence, dpcm_sequence
.import ntsc_period_low, ntsc_period_high
; Triangle has its own /32 period table; the pulse table would play it an
; octave low (#12).
.import triangle_period_low, triangle_period_high
.import dpcm_bank_table, dpcm_pitch_table, dpcm_addr_table, dpcm_len_table
.import instrument_table
.import channel_start_banks
.import fetch_sequence_byte

; Multi-song "jukebox" builds only (nes/project_builder.py assigns
; `JUKEBOX_BUILD = 1` before `.include`ing this file when a music.asm was
; produced by exporter.export_song_bank_bytecode -- #30/F-13; ca65's .ifdef
; only recognizes real symbol/constant definitions, not `.define`d macros).
; A single-song build never defines JUKEBOX_BUILD and its music.asm never
; exports these symbols, so everything below gated by this stays out of the
; assembly entirely and single-song ROMs are byte-identical to before this
; feature existed.
.ifdef JUKEBOX_BUILD
.import song_table_ptr_lo, song_table_ptr_hi, song_table_bank, song_count
.import song_instrument_ptr_lo, song_instrument_ptr_hi
.endif

.segment "ZEROPAGE"
ptr1:           .res 2

.exportzp ptr1, temp1, temp2, frame_counter
temp1:          .res 1
temp2:          .res 1
frame_counter:  .res 2
; Jukebox-only (see EVAL_MACRO): points at the active song's instrument_table
; since there's no single fixed label to address directly when N songs each
; have their own. Harmless, unused reservation in a single-song build.
instrument_table_ptr: .res 2

.segment "BSS"

; 5 channels: 0=Pulse1, 1=Pulse2, 2=Triangle, 3=Noise, 4=DMC
stream_ptr_lo:  .res 5
stream_ptr_hi:  .res 5
stream_bank:    .res 5
frame_wait:     .res 5
current_len:    .res 5
current_note:   .res 5
current_inst:   .res 5
; Jukebox-only state (RAM reservations cost nothing in a single-song ROM's
; PRG-ROM budget, so these stay unconditional rather than ifdef-gated too --
; only the CODE that reads/writes them is gated).
current_song:   .res 1
channel_ended:  .res 5
macro_steps_vol:    .res 5
macro_steps_arp:    .res 5
macro_steps_pitch:  .res 5
macro_steps_duty:   .res 5
; Last hardware value written to $4003/$4007 (pulse1/pulse2 only; slots 2-4
; unused). Writing $4003/$4007 always restarts the pulse phase regardless of
; whether the value changes, so we gate the write on value equality and force
; a rewrite ($FF sentinel) whenever a new note is triggered (#161/NH-18).
last_written_hi:    .res 5

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
.ifdef JUKEBOX_BUILD
    ; A jukebox build has one instrument_table per song (song0_instrument_table,
    ; song1_instrument_table, ...), not the single fixed `instrument_table`
    ; label the .else branch addresses directly -- there's no compile-time
    ; constant to reference, so go through instrument_table_ptr (set by
    ; load_song_streams_indexed whenever the active song changes) instead.
    ; This costs a few extra cycles per macro eval versus the direct
    ; absolute,Y read below; single-song builds never assemble this branch,
    ; so they pay none of it (#30/F-13).
    tya
    clc
    adc #inst_offset
    tay
    lda (instrument_table_ptr), y
    sta ptr1
    iny
    lda (instrument_table_ptr), y
    sta ptr1+1
.else
    lda instrument_table+inst_offset, y
    sta ptr1
    lda instrument_table+inst_offset+1, y
    sta ptr1+1
.endif

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
.ifdef JUKEBOX_BUILD
    ; A jukebox music.asm never defines the fixed single-song labels the
    ; .else branch below references (pulse1_sequence, channel_start_banks,
    ; ...) -- ld65 links whole modules, not per-routine, so leaving that
    ; branch's instructions assembled here would fail the link with
    ; unresolved externals even though nothing calls audio_init in a
    ; jukebox build. Redirect to the real jukebox entry point instead;
    ; audio_init stays exported/callable as a harmless alias so nothing
    ; downstream needs conditional call-site logic (#30/F-13).
    jmp audio_init_song
.else
    ; Initialize sequence pointers from the exported CA65 labels. Each channel's
    ; starting bank comes from the exporter's channel_start_banks table, NOT a
    ; hardcoded 0 -- a later channel's sequence label can spill past BANK_00 once
    ; earlier channels fill a bank, and reading it from bank 0 plays garbage
    ; (#328/EXP-13). The within-stream CMD_BANK_JUMP path already updates
    ; stream_bank,x; this fixes only the initial per-channel bank.
    lda #<pulse1_sequence
    sta stream_ptr_lo+0
    lda #>pulse1_sequence
    sta stream_ptr_hi+0
    lda channel_start_banks+0
    sta stream_bank+0

    lda #<pulse2_sequence
    sta stream_ptr_lo+1
    lda #>pulse2_sequence
    sta stream_ptr_hi+1
    lda channel_start_banks+1
    sta stream_bank+1

    lda #<triangle_sequence
    sta stream_ptr_lo+2
    lda #>triangle_sequence
    sta stream_ptr_hi+2
    lda channel_start_banks+2
    sta stream_bank+2

    lda #<noise_sequence
    sta stream_ptr_lo+3
    lda #>noise_sequence
    sta stream_ptr_hi+3
    lda channel_start_banks+3
    sta stream_bank+3

    lda #<dpcm_sequence
    sta stream_ptr_lo+4
    lda #>dpcm_sequence
    sta stream_ptr_hi+4
    lda channel_start_banks+4
    sta stream_bank+4
.endif

; Shared APU/frame-counter/channel-state init tail, reached by both a
; single-song audio_init (falls straight through, unchanged) and a jukebox
; audio_init_song (jumps in after loading its own song's stream pointers via
; load_song_streams_indexed instead of the fixed labels above). A pure label
; insertion -- no instruction here is reordered or modified, so audio_init's
; own bytes are unaffected when JUKEBOX_BUILD is undefined (#30/F-13).
audio_init_hw_and_state:
    ; Initialize DMC output level to 0 to prevent muffling Triangle/Noise.
    ; (A no longer holds 0 after the bank loads above, so reload it.)
    lda #$00
    sta $4011

    ; Initialize the APU so the NMI-driven engine owns the channels.
    ; $4017 = $40: frame counter 4-step mode (mode 0), disable frame IRQ so it
    ; cannot clock length/envelope units against us (docs/NES_APU_REFERENCE.md §3.2).
    lda #$40
    sta $4017
    ; $4015 = $0F: enable Pulse1/Pulse2/Triangle/Noise. DMC (bit 4) is enabled
    ; on demand by the sample playback handlers (docs/NES_APU_REFERENCE.md §3.1).
    lda #$0F
    sta $4015

    ; Disable both sweep units. A sweep left enabled by power-on garbage
    ; continuously bends the pulse pitch and can silence the channel on overflow
    ; (docs/APU_PULSE_REFERENCE.md §1, §5 cond. 2). $08 = enable clear, shift 0.
    lda #$08
    sta $4001
    sta $4005

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
    lda #$FF
    sta last_written_hi, x
    dex
    bpl @clear_loop
    rts

.ifdef JUKEBOX_BUILD
; ---------------------------------------------------------------------------
; Jukebox routines (multi-song builds only -- #30/F-13)
; ---------------------------------------------------------------------------
.export audio_init_song, audio_advance_song

; load_song_streams_indexed
; Loads channel 0-4's stream_ptr_lo/hi + stream_bank from the song_table_*
; arrays at index current_song*5 + channel (instead of audio_init's fixed
; per-channel labels), and instrument_table_ptr from song_instrument_ptr_*
; at index current_song (see EVAL_MACRO). 6502 has no multiply --
; current_song*5 is computed as (current_song*4) + current_song rather than
; a loop.
load_song_streams_indexed:
    lda current_song
    tax
    lda song_instrument_ptr_lo, x
    sta instrument_table_ptr
    lda song_instrument_ptr_hi, x
    sta instrument_table_ptr+1

    lda current_song
    asl a
    asl a               ; A = current_song * 4
    clc
    adc current_song    ; A = current_song * 5
    tay

    ldx #0
@copy_loop:
    lda song_table_ptr_lo, y
    sta stream_ptr_lo, x
    lda song_table_ptr_hi, y
    sta stream_ptr_hi, x
    lda song_table_bank, y
    sta stream_bank, x
    iny
    inx
    cpx #5
    bne @copy_loop
    rts

; audio_init_song
; Jukebox entry point: init_music jumps here instead of audio_init. Always
; cold-boots on song 0, then shares audio_init's APU/state-init tail.
audio_init_song:
    lda #0
    sta current_song
    ldx #4
@clear_ended:
    lda #0
    sta channel_ended, x
    dex
    bpl @clear_ended
    jsr load_song_streams_indexed
    jmp audio_init_hw_and_state

; audio_advance_song
; Advances to the next song (wrapping past the last back to song 0), reloads
; its stream pointers, and clears per-channel playback state so the new song
; starts clean rather than inheriting timing state left over from the last
; note of the previous song. Called both from @end_of_stream (all 5 channels
; of the current song finished) and from main.asm's Start-button edge
; detector (immediate skip).
audio_advance_song:
    inc current_song
    lda current_song
    cmp song_count
    bcc @no_wrap
    lda #0
    sta current_song
@no_wrap:
    jsr load_song_streams_indexed

    ldx #4
@clear_loop:
    lda #1
    sta current_len, x
    lda #0
    sta frame_wait, x
    sta current_note, x
    sta channel_ended, x
    lda #$FF
    sta last_written_hi, x
    dex
    bpl @clear_loop
    rts
.endif

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
    ; Dispatch by byte range. @is_note/@is_length live far past the command
    ; handlers below, so branch to a local trampoline and jmp to the far target
    ; (a direct bcc would exceed the 6502 +/-127 relative-branch range).
    cmp #$60
    bcs @chk_length
    jmp @is_note      ; < $60 -> note
@chk_length:
    cmp #$80
    bcs @is_command   ; >= $80 -> command (falls through below)
    jmp @is_length    ; $60-$7F -> length

@is_command:
    ; Handle commands ($80 - $FE)
    cmp #$FE
    beq @cmd_bank_jump
    cmp #$85
    beq @cmd_dpcm_play
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
    ; A holds the just-fetched note byte. An event whose duration exceeds
    ; the 32-frame Length cap gets chunked by the exporter into several
    ; ($6X, note) pairs that repeat the SAME note byte
    ; (exporter/exporter_ca65.py's `_build_song_bytecode` dur>32 split) --
    ; by construction, the frame-by-frame source loop only ever starts a new
    ; event when the note value actually changes, so two note bytes this
    ; same on this channel are always one held event's own chunk boundary,
    ; never two independent onsets that happen to share a pitch. Treat that
    ; case as a tie/continuation: skip the macro reset and the phase-reset
    ; sentinel below so a held pulse note doesn't audibly re-click every 32
    ; frames and a live macro producer doesn't replay its first steps
    ; (#439/EXP-2026-08-21-1). A genuinely new note (including the first
    ; note after init/song-advance, whose current_note starts at 0 and a
    ; real note is never 0) always differs and still gets the full reset.
    cmp current_note, x
    beq @is_note_tie

    sta current_note, x

    ; Reset all macro sequence steps to 0
    lda #0
    sta macro_steps_vol, x
    sta macro_steps_arp, x
    sta macro_steps_pitch, x
    sta macro_steps_duty, x

    ; Force this note's first frame to (re)write $4003/$4007 even if the
    ; period happens to match the previous note -- a genuine new note must
    ; still retrigger (#161/NH-18 only suppresses same-value writes during
    ; sustain, not at note onset).
    lda #$FF
    sta last_written_hi, x

@is_note_tie:
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
    bne @write_noise_dispatch
    jmp @write_triangle   ; @write_triangle is now out of BEQ's +/-127 range
@write_noise_dispatch:
    jmp @write_noise

@write_pulse1:
    lda temp_duty
    lsr
    ror
    ror           ; Fast shift duty bits 0-1 into D6-D7
    ora #$30      ; Constant volume flag
    sta temp1     ; Save duty+constant flags
    lda temp_vol
    and #$0F      ; Clamps volume to 0-15 to prevent register corruption
    ora temp1
    sta $4000
    
    lda temp_pitch
    bne @p1_pitch_mod
    ; Fast path: No pitch bend, avoid 16-bit math
    lda ntsc_period_low, y
    sta $4002
    lda ntsc_period_high, y
    ora #$08
    jmp @p1_write_hi
@p1_pitch_mod:
    lda ntsc_period_low, y
    clc
    adc temp_pitch
    sta $4002
    lda ntsc_period_high, y
    adc temp_pitch_hi
    ora #$08      ; Set length reload for new notes (harmless: halted via
                  ; $4000/#$30 control byte, not this $4003 length-load field)
@p1_write_hi:
    ; $4003 always restarts the pulse sequencer phase, so only write it when
    ; the value actually changed -- otherwise a held note re-clicks every
    ; frame (#161/NH-18). $4002 (low byte) never resets phase and is always
    ; written above. (@next_channel is out of BEQ's +/-127 range, so branch
    ; around the write instead of branching directly to it.)
    cmp last_written_hi+0
    beq @p1_skip_hi
    sta $4003
    sta last_written_hi+0
@p1_skip_hi:
    jmp @next_channel

@write_pulse2:
    lda temp_duty
    lsr
    ror
    ror           ; Fast shift duty bits 0-1 into D6-D7
    ora #$30      ; Constant volume flag
    sta temp1     ; Save duty+constant flags
    lda temp_vol
    and #$0F      ; Clamps volume to 0-15 to prevent register corruption
    ora temp1
    sta $4004
    
    lda temp_pitch
    bne @p2_pitch_mod
    ; Fast path: No pitch bend, avoid 16-bit math
    lda ntsc_period_low, y
    sta $4006
    lda ntsc_period_high, y
    ora #$08
    jmp @p2_write_hi
@p2_pitch_mod:
    lda ntsc_period_low, y
    clc
    adc temp_pitch
    sta $4006
    lda ntsc_period_high, y
    adc temp_pitch_hi
    ora #$08
@p2_write_hi:
    ; Same phase-reset guard as pulse1 (#161/NH-18).
    cmp last_written_hi+1
    beq @p2_skip_hi
    sta $4007
    sta last_written_hi+1
@p2_skip_hi:
    jmp @next_channel
    
@write_triangle:
    lda temp_vol
    beq @silence_tri
    
    lda #$FF      ; Halt length/linear counter, max volume
    sta $4008
    
    lda temp_pitch
    bne @tri_pitch_mod
    ; Fast path: No pitch bend, avoid 16-bit math
    lda triangle_period_low, y
    sta $400A
    lda triangle_period_high, y
    ora #$08
    sta $400B
    jmp @next_channel
@tri_pitch_mod:
    lda triangle_period_low, y
    clc
    adc temp_pitch
    sta $400A
    lda triangle_period_high, y
    adc temp_pitch_hi
    ora #$08
    sta $400B
    jmp @next_channel
    
@silence_tri:
    lda #$80      ; Linear Counter Halt (Safely Silences Triangle)
    sta $4008
    jmp @next_channel

@write_noise:
    lda temp_vol
    and #$0F      ; Clamps volume to 0-15
    ora #$30      ; Constant volume flag & Length counter halt
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

    ; A $00 length_reg means this dense id was never packed (its .dmc file
    ; was missing at pack time, docs/APU_DMC_REFERENCE.md, #367/DP-DPCM-05)
    ; -- skip the trigger entirely so we don't read a stray 1-byte fragment
    ; of bank 0 / $C000 (a click/garbage sample) in place of the drum the
    ; song intended, and don't disturb whatever else is currently playing.
    ; @next_channel is out of `beq`'s +-127-byte range from here, so branch
    ; over an absolute `jmp` instead (same idiom as exporter_ca65.py's
    ; _emit_safe_beq for the equivalent direct-export trigger).
    lda dpcm_len_table, y
    bne @sample_ready
    jmp @next_channel
@sample_ready:

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
    ; Sequence finished. Every subsequent frame re-fetches this same $FF, so
    ; without an explicit silence write the channel's last note keeps its
    ; hardware-halted, nonzero-volume state forever (#159). Re-arm silence
    ; each frame instead (idempotent, and cheap next to a 5-channel budget).
    lda #0
    sta current_note, x
.ifdef JUKEBOX_BUILD
    ; Auto-advance (#30/F-13): mark this channel ended (idempotent -- this
    ; re-fires every frame per the comment above) and, once all 5 channels
    ; of the current song have ended simultaneously, jump to the next song.
    ; X is the outer channel_loop index (audio_update); save/restore it
    ; around this check since it's reused as the inner scan index below.
    lda #1
    sta channel_ended, x
    txa
    pha
    ldx #0
@jukebox_scan_ended:
    lda channel_ended, x
    beq @jukebox_not_all_ended
    inx
    cpx #5
    bne @jukebox_scan_ended
    jsr audio_advance_song      ; clears channel_ended itself on the way out
    ; audio_advance_song just reloaded every channel's stream pointers, but
    ; falling through to @silence below would silence THIS channel (the one
    ; that triggered the scan, X still on the stack) instead of reading the
    ; new song's first byte, and channels with index < X already ran their
    ; @fetch_byte this frame against the OLD (pre-advance) streams -- both
    ; groups would start the new song one 60Hz frame late (#433/
    ; NH-HW-2026-08-21-6). Discard the saved X (it's about to be reset to 0
    ; anyway) and restart the whole channel loop for this frame instead of
    ; falling through: every channel gets exactly one correct pass over the
    ; new song's streams. A channel with index < X gets re-visited a second
    ; time this frame, but harmlessly -- its first (pre-advance) pass never
    ; touched frame_wait (it only re-fetched the trailing $FF sentinel), so
    ; the restarted pass's @fetch_byte is the only one that does real work.
    pla
    ldx #0
    jmp @channel_loop
@jukebox_not_all_ended:
    pla
    tax
.endif
    jmp @silence

@next_channel:
    inx
    cpx #5
    beq @done
    jmp @channel_loop
    
@done:
    rts