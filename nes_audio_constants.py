# NES Pulse Wave Duty Cycle Patterns
# These represent the 8-bit duty cycle values for the pulse channels
# Each value corresponds to a percentage of the waveform being high:
# 0x00: 12.5% (1/8)
# 0x40: 25% (1/4)
# 0x80: 50% (1/2)
# 0xC0: 75% (3/4) - inverted 25%

PULSE_DUTY_CYCLES = {
    1: 0b00000001,  # 12.5%
    2: 0b00000011,  # 25%
    3: 0b00001111,  # 50%
    4: 0b01111100,  # 75% (inverted 25%)
}

# Placeholder for envelope definitions (ADSR, etc.)
# These are conceptual and will be refined as ADSR implementation progresses.

# Example structure for a simple volume envelope (decay rate)
# The NES APU has a fixed-rate envelope generator.
# Volume values range from 0-15.

# For pulse and triangle channels, the volume envelope is controlled by a 4-bit decay rate.
# A value of 0 means no decay (sustain), 1-15 are decay rates.
# The loop flag determines if the envelope loops after decay.

# ENVELOPE_DECAY_RATES = {
#     # Example: rate_id: [decay_value, loop_flag]
# }

# For now, we'll define a simple mapping for common envelope behaviors.
# These will be used to set the volume and loop flag in the APU registers.

# Example: (volume, loop_flag)
NES_ENVELOPES = {
    "sustain": (0xF, True),  # Max volume, loop enabled (for sustained notes)
    "decay_fast": (0x0, False), # Fast decay, no loop
    "decay_medium": (0x4, False),
    "decay_slow": (0x8, False),
    "percussion": (0x0, True), # For noise channel, often loops
}
