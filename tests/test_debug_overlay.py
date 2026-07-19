"""Regression coverage for nes/debug_overlay.py's standalone ROM-variant helper.

The live ``--debug`` path (generate_full_debug_system injected via
NESProjectBuilder) is smoke-tested for compile by
tests/test_rom_validation_integration.py. The *standalone*
``create_debug_rom_variant(music_asm_path, output_path)`` helper and its
``__main__`` CLI entry had no dedicated test (#358/REG-24), so a regression in
its file-combination logic — dropping the original music body, or malforming the
concatenation so ca65 chokes — was silent. These tests pin its contract.
"""

import subprocess

import pytest

from nes.debug_overlay import NESDebugOverlay, create_debug_rom_variant


def test_create_debug_rom_variant_preserves_body_and_injects_overlay(
    minimal_music_asm, temp_dir
):
    """The combined .asm keeps the original music.asm verbatim and appends the
    marker plus the full debug system."""
    original = minimal_music_asm.read_text()
    out = temp_dir / "music_debug.asm"

    create_debug_rom_variant(str(minimal_music_asm), str(out))

    assert out.exists()
    combined = out.read_text()

    # (a) original body present verbatim
    assert original in combined
    # (b) injection marker present
    assert "DEBUG OVERLAY INJECTED BELOW" in combined
    # (c) the debug system was actually appended (after the marker)
    debug_system = NESDebugOverlay(enable_overlay=True).generate_full_debug_system()
    assert debug_system in combined
    assert combined.index("DEBUG OVERLAY INJECTED BELOW") < combined.index(debug_system)
    # ordering: original body precedes the injected overlay
    assert combined.index(original) < combined.index("DEBUG OVERLAY INJECTED BELOW")


def test_create_debug_rom_variant_cli_entry(minimal_music_asm, temp_dir):
    """The ``python -m nes.debug_overlay <in> <out>`` CLI entry writes the same
    combined output (exercises the ``__main__`` block)."""
    out = temp_dir / "cli_debug.asm"
    result = subprocess.run(
        ["python", "-m", "nes.debug_overlay", str(minimal_music_asm), str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    combined = out.read_text()
    assert minimal_music_asm.read_text() in combined
    assert "DEBUG OVERLAY INJECTED BELOW" in combined


def test_create_debug_rom_variant_cli_usage_error():
    """Called with too few args, the CLI exits nonzero with a usage message
    rather than tracebacking."""
    result = subprocess.run(
        ["python", "-m", "nes.debug_overlay", "only_one_arg.asm"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Usage" in (result.stdout + result.stderr)


@pytest.mark.requires_cc65
def test_create_debug_rom_variant_output_assembles(minimal_music_asm, temp_dir):
    """The combined debug .asm assembles cleanly under ca65 (surfacing a nonzero
    exit + stderr, not swallowing it) so a malformed concatenation is caught."""
    out = temp_dir / "music_debug.asm"
    create_debug_rom_variant(str(minimal_music_asm), str(out))

    obj = temp_dir / "music_debug.o"
    result = subprocess.run(
        ["ca65", str(out), "-o", str(obj)],
        capture_output=True, text=True, cwd=str(temp_dir),
    )
    assert result.returncode == 0, f"ca65 failed:\n{result.stderr}"
    assert obj.exists()
