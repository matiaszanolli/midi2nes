import os
import wave
import numpy as np
import argparse
import struct

def convert_wav_to_unsigned_pcm(wav_path, sample_rate=8000):
    with wave.open(wav_path, 'rb') as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

        dtype = {1: np.uint8, 2: np.int16}[sampwidth]
        data = np.frombuffer(frames, dtype=dtype)

        # Convert to mono if needed
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)

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
    encoded = []
    prev = 0x40  # Start at mid-range (64)
    for sample in data:
        delta = sample - prev
        step = 1 if delta > 0 else -1 if delta < 0 else 0
        prev = np.clip(prev + step, 0, 127)
        encoded.append(prev)
    return encoded


def dpcm_compress(encoded):
    """
    Compress 7-bit values into NES 1-bit delta format (8 samples per byte).
    Returns byte array.
    """
    bits = []
    for i in range(1, len(encoded)):
        bit = 1 if encoded[i] > encoded[i - 1] else 0
        bits.append(bit)

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


def convert_wav_to_dmc(input_path, output_path, sample_rate=8000):
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
    args = parser.parse_args()

    size = convert_wav_to_dmc(args.input_wav, args.output_dmc)
    print(f"Exported {args.output_dmc} ({size} bytes)")
