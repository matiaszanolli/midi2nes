; nsf_main_driver.s

.segment "HEADER"

    .byte $4E, $45, $53, $1A   ; ID 'NESM'
    .byte $01                 ; Version
    .byte $01                 ; Total songs
    .byte $01                 ; Starting song
    .word Init                ; INIT address
    .word Play                ; PLAY address
    .byte <_bank0, >_bank0    ; Load address bank 0
    .word _load_address       ; Load address
    .word _init_address       ; Init address
    .word _play_address       ; Play address
    .byte 0                   ; NTSC only
    .res 32, 0                ; Song name
    .res 32, 0                ; Artist
    .res 32, 0                ; Copyright
    .word 0                   ; Play speed NTSC (60Hz)
    .word 0                   ; Play speed PAL (not used)
    .res 4, 0                 ; Expansion chips
    .res 4, 0                 ; Reserved

.segment "CODE"

; Symbols required by NSF header
.export Init, Play

.import music_init, music_play

Init:
    jsr music_init
    rts

Play:
    jsr music_play
    rts
