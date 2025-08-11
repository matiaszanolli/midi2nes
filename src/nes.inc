; nes.inc - NES hardware definitions
; Standard NES memory map and hardware registers

; PPU Registers
PPU_CTRL   = $2000
PPU_MASK   = $2001  
PPU_STATUS = $2002
PPU_OAM_ADDR = $2003
PPU_OAM_DATA = $2004
PPU_SCROLL = $2005
PPU_ADDR   = $2006
PPU_DATA   = $2007

; APU Registers (Audio Processing Unit)
APU_PULSE1_CTRL  = $4000   ; Pulse 1 duty/volume/envelope
APU_PULSE1_SWEEP = $4001   ; Pulse 1 sweep
APU_PULSE1_TIMER_LO = $4002 ; Pulse 1 timer low byte
APU_PULSE1_TIMER_HI = $4003 ; Pulse 1 timer high byte + length

APU_PULSE2_CTRL  = $4004   ; Pulse 2 duty/volume/envelope  
APU_PULSE2_SWEEP = $4005   ; Pulse 2 sweep
APU_PULSE2_TIMER_LO = $4006 ; Pulse 2 timer low byte
APU_PULSE2_TIMER_HI = $4007 ; Pulse 2 timer high byte + length

APU_TRIANGLE_CTRL = $4008  ; Triangle linear counter
APU_TRIANGLE_TIMER_LO = $400A ; Triangle timer low byte
APU_TRIANGLE_TIMER_HI = $400B ; Triangle timer high byte + length

APU_NOISE_CTRL   = $400C   ; Noise volume/envelope
APU_NOISE_PERIOD = $400E   ; Noise period
APU_NOISE_LENGTH = $400F   ; Noise length

APU_DMC_CTRL     = $4010   ; DMC rate/IRQ/loop
APU_DMC_LOAD     = $4011   ; DMC direct load
APU_DMC_ADDR     = $4012   ; DMC sample address
APU_DMC_LENGTH   = $4013   ; DMC sample length

APU_STATUS       = $4015   ; APU channel enable/status

; Controller Ports
CONTROLLER1      = $4016
CONTROLLER2      = $4017

; Common Memory Regions
ZERO_PAGE        = $0000   ; $0000-$00FF
STACK            = $0100   ; $0100-$01FF
RAM              = $0200   ; $0200-$07FF
PPU_REGISTERS    = $2000   ; $2000-$2007 (mirrored to $3FFF)
APU_REGISTERS    = $4000   ; $4000-$4017
EXPANSION_ROM    = $4020   ; $4020-$5FFF
SRAM             = $6000   ; $6000-$7FFF
PRG_ROM          = $8000   ; $8000-$FFFF

; Common Constants
NTSC_CPU_CLOCK   = 1789773 ; NTSC CPU clock rate in Hz

; APU Bit Masks
APU_ENABLE_PULSE1   = %00000001
APU_ENABLE_PULSE2   = %00000010  
APU_ENABLE_TRIANGLE = %00000100
APU_ENABLE_NOISE    = %00001000
APU_ENABLE_DMC      = %00010000

; Pulse Channel Duty Cycles
DUTY_12_5   = %00000000  ; 12.5% duty cycle
DUTY_25     = %01000000  ; 25% duty cycle  
DUTY_50     = %10000000  ; 50% duty cycle
DUTY_75     = %11000000  ; 75% duty cycle (25% inverted)

; Volume/Envelope Control
VOLUME_0    = %00000000
VOLUME_MAX  = %00001111
CONSTANT_VOLUME = %00010000
ENVELOPE_LOOP   = %00100000

; Length Counter Control  
LENGTH_COUNTER_DISABLE = %00100000

; Triangle Linear Counter Control
TRIANGLE_CONTROL_FLAG = %10000000
