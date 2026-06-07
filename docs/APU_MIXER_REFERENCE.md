# NES APU Mixer Reference

This document details the hardware behavior of the NES APU Mixer. The mixer takes the digital outputs from all five APU channels and converts them into an analog audio signal. 

Understanding the mixer is crucial because the NES uses **non-linear mixing**. The channels are not simply added together; instead, they interact with and physically compress each other based on their current output levels.

## 1. Hardware Architecture & Groupings

The channels are combined using two separate Digital-to-Analog Converters (DACs) before being mixed together:
1.  **Pulse Group (`pulse_out`):** Pulse 1 and Pulse 2.
2.  **TND Group (`tnd_out`):** Triangle, Noise, and DMC.

The total audio output (normalized from `0.0` to `1.0`) is the sum of these two groups:
`output = pulse_out + tnd_out`

---

## 2. Non-Linear Mixing Formulas

### The Pulse Group
The pulse channels range from 0 to 15.
```text
                            95.88
pulse_out = ------------------------------------
             (8128 / (pulse1 + pulse2)) + 100
```
*(If both pulse channels are 0, `pulse_out` is 0 to avoid division by zero).*

### The TND Group (Triangle, Noise, DMC)
Triangle ranges from 0-15, Noise from 0-15, and DMC from 0-127.
```text
                                       159.79
tnd_out = -------------------------------------------------------------
                                    1
           ----------------------------------------------------- + 100
            (triangle / 8227) + (noise / 12241) + (dmc / 22638)
```
*(If all three channels are 0, `tnd_out` is 0).*

---

## 3. Hardware Filters

After the non-linear DACs combine the audio, the NES hardware runs the signal through a series of analog filters before it leaves the console:

**NTSC NES Filters:**
*   First-order high-pass filter at **90 Hz**
*   First-order high-pass filter at **440 Hz**
*   First-order low-pass filter at **14 kHz**

*(Note: The Famicom hardware only specifies a single high-pass filter at 37 Hz, meaning Famicom audio natively has much heavier bass than the western NES).*

---

## 4. Emulation & Approximations

While the formulas above are perfectly accurate, many emulators use faster approximations to calculate the mixer output.

### Lookup Tables
```text
pulse_table[n] = 95.52 / (8128.0 / n + 100)
pulse_out = pulse_table[pulse1 + pulse2]

tnd_table[n] = 163.67 / (24329.0 / n + 100)
tnd_out = tnd_table[3 * triangle + 2 * noise + dmc]
```

### Linear Approximation (Less Accurate)
```text
pulse_out = 0.00752 * (pulse1 + pulse2)
tnd_out = 0.00851 * triangle + 0.00494 * noise + 0.00335 * dmc
```

---

## 5. Engine Implementation Notes (midi2nes)

*   **Hardware Side-chain Compression:** Because the Triangle, Noise, and DMC channels share a non-linear DAC, a high DMC output value will physically compress (reduce) the volume of the Triangle and Noise channels. Because `midi2nes` relies heavily on DPCM drum samples, our tracks will naturally exhibit this classic NES "ducking" effect. This is an authentic hardware characteristic and requires no software compensation.
*   **The DMC Volume Trick:** Games like *Super Mario Bros.* exploit this non-linear math. By writing specific high values directly to the DMC load register (`$4011`), developers could intentionally quiet the Triangle channel (which otherwise has no volume control). 
*   **Safe Initialization:** To ensure our Triangle and Noise channels are as loud as possible when a song begins, our 6502 engine initialization routine must write `$00` to `$4011`. This zeros out the DMC DAC and removes any compression on the TND group until a drum sample actually plays.
*   **Bass Response:** Because the real NES hardware cuts off bass frequencies below 90 Hz, our arrangers must be careful when dropping the Triangle channel into extremely low octaves, as the physical console (and accurate emulators) will heavily muffle those notes.