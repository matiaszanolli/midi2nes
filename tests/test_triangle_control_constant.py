"""Regression coverage for #364/NH-HW-04 — triangle linear-counter reload.

The direct-export triangle control byte no longer scales a halted linear
counter's reload by loudness (`0x80 | volume*7`, inert but a latent trap). The
triangle has no volume control, so `volume` is only a gate: 0 -> $00 (silent),
any nonzero -> a fixed max reload with the control flag set ($FF, like the
bytecode engine). See docs/APU_TRIANGLE_REFERENCE.md §1/§4.
"""


class TestTriangleLinearCounterConstant:
    def test_constant_is_control_flag_plus_max_reload(self):
        from exporter.exporter_ca65 import (
            TRIANGLE_CONTROL_ON,
            TRIANGLE_LINEAR_COUNTER_CONTROL,
            TRIANGLE_LINEAR_COUNTER_MAX,
        )
        assert TRIANGLE_LINEAR_COUNTER_CONTROL == 0x80
        assert TRIANGLE_LINEAR_COUNTER_MAX == 0x7F
        assert TRIANGLE_CONTROL_ON == 0xFF  # matches the bytecode engine's $FF

    def test_direct_export_triangle_control_bytes(self, tmp_path):
        from exporter.exporter_ca65 import CA65Exporter
        frames = {
            "triangle": {
                0: {"note": 60, "volume": 15},   # active -> 0xFF
                1: {"note": 60, "volume": 3},    # active (any nonzero) -> 0xFF
                2: {"note": 0, "volume": 0},     # silent -> 0x00
            }
        }
        out = tmp_path / "music.asm"
        CA65Exporter().export_direct_frames(frames, str(out), standalone=False)
        text = out.read_text()
        # An active triangle frame's control byte is $FF, never a loudness-scaled
        # value. The old code emitted 0xE9 (0x80|15*7) for volume 15.
        assert "$FF" in text
        assert "$E9" not in text
