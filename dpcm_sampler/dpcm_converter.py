import wave
import numpy as np
import argparse

from constants import DEFAULT_DMC_PITCH_RATE, DEFAULT_DMC_RATE_HZ

# This module is currently orphaned -- nothing in the pipeline calls it;
# generate_dpcm_index scans pre-made .dmc files directly. Kept for anyone who
# wants to regenerate/extend the .dmc catalog from WAV sources; if you wire
# it back in, keep sample_rate and the packer's pitch_rate (dpcm_packer.
# DpcmPacker.add_sample) in sync -- see convert_wav_to_dmc's docstring below
# (#342/DP-DPCM-03).

def convert_wav_to_unsigned_pcm(wav_path, sample_rate=DEFAULT_DMC_RATE_HZ):
    with wave.open(wav_path, 'rb') as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

        dtype = {1: np.uint8, 2: np.int16}[sampwidth]
        data = np.frombuffer(frames, dtype=dtype)

        # Convert to mono if needed. Cast back to the source dtype
        # immediately: .mean() always promotes to float64, and the 8-bit
        # (sampwidth==1) path has no later re-cast to catch it -- only the
        # sampwidth==2 branch below normalizes back to uint8, so a
        # multi-channel 8-bit WAV previously left this function returning a
        # float64 array where every other path returns uint8 (#337/REG-18).
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1).astype(dtype)

        # Normalize to 8-bit unsigned PCM range
        if sampwidth == 2:
            data = ((data.astype(np.float32) + 32768) / 256).astype(np.uint8)

        # Downsample if needed
        if rate != sample_rate:
            ratio = rate / sample_rate
            indices = np.arange(0, len(data), ratio)
            data = np.interp(indices, np.arange(len(data)), data).astype(np.uint8)

        return data


def delta_encode(data):
    """Model the NES DMC's sigma-delta reconstruction: a 7-bit (0-127)
    counter that steps +-2 per emitted bit (docs/APU_DMC_REFERENCE.md §3).

    ``data`` arrives as 8-bit unsigned PCM (0-255, from
    convert_wav_to_unsigned_pcm) -- halve it onto the counter's own 0-127
    scale before comparing. Left unnormalized, PCM silence (128) sits
    entirely above the tracker's 127 ceiling, permanently pinning every
    delta positive and biasing the whole encode; and a +-1 step models
    half the amplitude hardware actually reconstructs per bit
    (#448/DPCM-2026-08-21-5).
    """
    encoded = []
    # Start at 0, not mid-range: the engine's init routine writes $00 to
    # $4011 before any sample plays (docs/APU_DMC_REFERENCE.md §5, "Silence
    # Initialization"), so the real hardware output level a played-back
    # sample reconstructs from is 0 -- starting the encoder at 0x40 (64)
    # instead produced a startup DC ramp/attack transient on every sample
    # that doesn't exist on the actual hardware playback path (#342/DP-DPCM-03).
    prev = 0x00
    for sample in data:
        target = sample >> 1  # 0-255 PCM -> the counter's 0-127 scale
        delta = target - prev
        step = 2 if delta > 0 else -2 if delta < 0 else 0
        prev = np.clip(prev + step, 0, 127)
        encoded.append(prev)
    return encoded


def dpcm_compress(encoded):
    """
    Compress 7-bit values into NES 1-bit delta format (8 samples per byte).
    Returns byte array.

    Includes a bit for the transition into ``encoded[0]`` itself, not just
    ``encoded[1:]`` -- delta_encode's init level (0, matching the engine's
    silence-initialization, docs/APU_DMC_REFERENCE.md §5) is a real starting
    point the first emitted bit steps away from. Skipping it used to leave
    playback permanently offset by one step from the modeled reconstruction
    (#448/DPCM-2026-08-21-5).
    """
    bits = []
    prev = 0x00  # delta_encode's own init level
    for level in encoded:
        bit = 1 if level > prev else 0
        bits.append(bit)
        prev = level

    # Pad to multiple of 8
    while len(bits) % 8 != 0:
        bits.append(0)

    dmc_bytes = []
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            byte |= (bits[i + j] << j)
        dmc_bytes.append(byte)

    return bytes(dmc_bytes[:4081])  # NES limit


def convert_wav_to_dmc(input_path, output_path, sample_rate=DEFAULT_DMC_RATE_HZ):
    """Convert a WAV file to a raw NES DMC sample.

    ``sample_rate`` must match the Hz the resulting .dmc will actually be
    played back at -- i.e. whatever ``pitch_rate`` (0-15) it's packed with
    via ``dpcm_packer.DpcmPacker.add_sample``. The default here
    (``DEFAULT_DMC_RATE_HZ`` = 33144 Hz) matches the packer's own default
    ``pitch_rate=15``; encoding at a different rate than the sample is
    ultimately played back at mis-pitches it (encoding at a lower rate than
    playback plays the sample back faster/higher-pitched, and vice versa)
    (#342/DP-DPCM-03). This module has no NTSC rate-index table for the
    other 15 ``pitch_rate`` values -- if you pack at a rate other than the
    default, pass the matching Hz here explicitly.
    """
    pcm = convert_wav_to_unsigned_pcm(input_path, sample_rate)
    encoded = delta_encode(pcm)
    dmc_data = dpcm_compress(encoded)

    with open(output_path, 'wb') as f:
        f.write(dmc_data)

    return len(dmc_data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_wav", help="Input WAV file")
    parser.add_argument("output_dmc", help="Output DMC file")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_DMC_RATE_HZ,
                         help="Target playback rate in Hz -- must match the "
                              "pitch_rate the .dmc will be packed with "
                              f"(default: {DEFAULT_DMC_RATE_HZ}, matching "
                              f"pitch_rate={DEFAULT_DMC_PITCH_RATE})")
    args = parser.parse_args()

    size = convert_wav_to_dmc(args.input_wav, args.output_dmc, args.sample_rate)
    print(f"Exported {args.output_dmc} ({size} bytes)")
