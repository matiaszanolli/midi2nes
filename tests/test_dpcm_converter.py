import wave
import numpy as np
import pytest

from dpcm_sampler.dpcm_converter import (
    convert_wav_to_unsigned_pcm,
    delta_encode,
    dpcm_compress,
    convert_wav_to_dmc,
)


def _write_wav(path, samples, channels=1, sampwidth=1, framerate=8000):
    """Write raw PCM samples (a flat, interleaved sequence for multi-channel)
    to a WAV file at `path` using the stdlib `wave` module."""
    dtype = {1: np.uint8, 2: np.int16}[sampwidth]
    data = np.asarray(samples, dtype=dtype)
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(data.tobytes())


class TestConvertWavToUnsignedPcm:
    """#337/REG-18: pin length/dtype/range for the WAV->8-bit-PCM stage."""

    def test_8bit_mono_passthrough(self, tmp_path):
        wav_path = tmp_path / "mono8.wav"
        samples = [0, 64, 128, 200, 255]
        _write_wav(wav_path, samples, channels=1, sampwidth=1, framerate=8000)

        data = convert_wav_to_unsigned_pcm(str(wav_path), sample_rate=8000)

        assert data.dtype == np.uint8
        assert len(data) == len(samples)
        assert data.tolist() == samples
        assert data.min() >= 0 and data.max() <= 255

    def test_16bit_mono_normalizes_to_8bit_unsigned(self, tmp_path):
        wav_path = tmp_path / "mono16.wav"
        # Bottom, mid, top of the int16 range.
        samples = [-32768, 0, 32767]
        _write_wav(wav_path, samples, channels=1, sampwidth=2, framerate=8000)

        data = convert_wav_to_unsigned_pcm(str(wav_path), sample_rate=8000)

        assert data.dtype == np.uint8
        # (sample + 32768) / 256, truncated: -32768->0, 0->128, 32767->255.
        assert data.tolist() == [0, 128, 255]

    def test_stereo_8bit_averages_channels_and_keeps_uint8(self, tmp_path):
        """Regression: multi-channel 8-bit input previously returned float64
        (from .mean()) because only the sampwidth==2 path re-cast to uint8."""
        wav_path = tmp_path / "stereo8.wav"
        # Interleaved L/R: (100,200) -> mean 150; (0,255)? avoid rounding
        # ambiguity by using an exact-average pair.
        interleaved = [100, 200, 0, 255, 60, 60]
        _write_wav(wav_path, interleaved, channels=2, sampwidth=1, framerate=8000)

        data = convert_wav_to_unsigned_pcm(str(wav_path), sample_rate=8000)

        assert data.dtype == np.uint8
        assert data.tolist() == [150, 127, 60]  # (100+200)/2, (0+255)/2 trunc, (60+60)/2

    def test_downsamples_when_rate_differs(self, tmp_path):
        wav_path = tmp_path / "highrate.wav"
        samples = list(range(0, 200, 2))  # 100 samples
        _write_wav(wav_path, samples, channels=1, sampwidth=1, framerate=16000)

        data = convert_wav_to_unsigned_pcm(str(wav_path), sample_rate=8000)

        assert data.dtype == np.uint8
        # Halving the rate should roughly halve the sample count.
        assert len(data) == pytest.approx(50, abs=1)


class TestDeltaEncode:
    """#337/REG-18: pin the ±1-step delta modulator's exact output and its
    [0,127] clamp at both ends."""

    def test_starts_at_midrange_and_steps_toward_target(self):
        # Target (70) is above the 0x40 (64) start on every sample.
        assert delta_encode([70, 70, 70]) == [65, 66, 67]

    def test_steps_down_toward_a_lower_target(self):
        assert delta_encode([0, 0, 0]) == [63, 62, 61]

    def test_zero_delta_holds_steady(self):
        assert delta_encode([64, 64, 64]) == [64, 64, 64]

    def test_clamps_at_upper_bound_127(self):
        # 63 steps needed to go from 64 to 127; hold there afterward.
        encoded = delta_encode([200] * 70)
        assert max(encoded) == 127
        assert encoded[-1] == 127
        assert encoded[-5:] == [127, 127, 127, 127, 127]

    def test_clamps_at_lower_bound_0(self):
        # 64 steps needed to go from 64 to 0; hold there afterward.
        encoded = delta_encode([0] * 70)
        assert min(encoded) == 0
        assert encoded[-1] == 0
        assert encoded[-5:] == [0, 0, 0, 0, 0]

    def test_never_leaves_7bit_range(self):
        # Alternating extremes should still never over/undershoot [0, 127].
        data = [255, 0] * 50
        encoded = delta_encode(data)
        assert all(0 <= v <= 127 for v in encoded)


class TestDpcmCompress:
    """#337/REG-18: pin the 1-bit-delta LSB-first bit-packing and padding,
    and the 4081-byte NES DMC size cap."""

    def test_packs_8_bits_lsb_first_no_padding_needed(self):
        # 9 values -> 8 consecutive-comparison bits -> exactly 1 byte, no pad.
        encoded = [64, 65, 66, 65, 64, 63, 64, 65, 64]
        # bits (encoded[i] > encoded[i-1]): 1,1,0,0,0,1,1,0
        result = dpcm_compress(encoded)
        assert result == bytes([0b01100011])  # bit0..bit7 = 1,1,0,0,0,1,1,0 -> 99

    def test_pads_short_tail_with_zero_bits(self):
        # 5 values -> 4 bits -> padded with four 0 bits to fill the byte.
        encoded = [64, 65, 66, 65, 64]
        # bits: 1,1,0,0 -> padded [1,1,0,0,0,0,0,0] -> LSB-first = 0b00000011
        result = dpcm_compress(encoded)
        assert result == bytes([0b00000011])  # 3

    def test_strictly_increasing_input_packs_all_ones(self):
        encoded = list(range(100))
        result = dpcm_compress(encoded)
        assert len(result) == (99 + 7) // 8  # 99 bits padded to 13 bytes
        assert all(b == 0xFF for b in result[:-1])  # last byte may be partly padded
        # Last byte: 99 bits = 12*8 + 3 real bits, all 1, rest padded 0.
        assert result[-1] == 0b00000111

    def test_never_exceeds_4081_byte_nes_dmc_limit(self):
        # Strictly increasing -> every bit is 1 -> far more than 4081 bytes
        # of real data before the cap.
        encoded = list(range(40_000))
        result = dpcm_compress(encoded)
        assert len(result) == 4081
        assert result == bytes([0xFF] * 4081)


class TestConvertWavToDmc:
    """#337/REG-18: end-to-end WAV->DMC conversion never exceeds the NES
    sample-length limit and reports the length it actually wrote."""

    def test_writes_dmc_file_and_returns_matching_length(self, tmp_path):
        wav_path = tmp_path / "in.wav"
        dmc_path = tmp_path / "out.dmc"
        samples = [int(127 + 100 * np.sin(i / 4)) for i in range(500)]
        _write_wav(wav_path, samples, channels=1, sampwidth=1, framerate=8000)

        written = convert_wav_to_dmc(str(wav_path), str(dmc_path), sample_rate=8000)

        assert dmc_path.exists()
        on_disk = dmc_path.read_bytes()
        assert written == len(on_disk)
        assert len(on_disk) <= 4081

    def test_never_exceeds_4081_bytes_for_a_long_input(self, tmp_path):
        wav_path = tmp_path / "long.wav"
        dmc_path = tmp_path / "long.dmc"
        # A long, steadily-varying signal so dpcm_compress has plenty of
        # source bits to potentially exceed the cap.
        samples = [int(127 + 120 * np.sin(i / 3)) for i in range(50_000)]
        _write_wav(wav_path, samples, channels=1, sampwidth=1, framerate=8000)

        written = convert_wav_to_dmc(str(wav_path), str(dmc_path), sample_rate=8000)

        assert written <= 4081
        assert dmc_path.read_bytes() == dmc_path.read_bytes()  # written once, stable
