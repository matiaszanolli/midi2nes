"""Integration tests for debug/rom_smoke_test.py (#517/PIPE-2026-08-24-1).

The most important test in this file is `test_smoke_test_catches_the_actual_
vblank_wait_bug_this_session_fixed` -- it builds a ROM with a hand-crafted
`reset` routine that reproduces the exact defect this session found and
fixed (NMI enabled before the PPU warm-up window closes, no `bit $2002`
wait), and asserts the smoke test correctly reports `nmi_fired=False`. This
is the regression guard: without it, nothing stops that exact class of bug
from silently reappearing.
"""

import subprocess
from pathlib import Path

import pytest

from debug.rom_smoke_test import run_smoke_test, PPU_WARMUP_CYCLES


def _assemble(asm_text: str, cfg_text: str, tmp_path: Path) -> Path:
    """Assemble+link a small ca65 program via the real cc65 toolchain (the
    same one the pipeline itself requires -- see CLAUDE.md). Skips the
    test if ca65/ld65 aren't on PATH rather than failing, matching how the
    rest of this suite treats the toolchain as an optional local dep."""
    asm_path = tmp_path / "test.asm"
    cfg_path = tmp_path / "test.cfg"
    obj_path = tmp_path / "test.o"
    nes_path = tmp_path / "test.nes"
    asm_path.write_text(asm_text)
    cfg_path.write_text(cfg_text)

    try:
        subprocess.run(["ca65", str(asm_path), "-o", str(obj_path)],
                        check=True, capture_output=True, text=True)
        subprocess.run(["ld65", "-C", str(cfg_path), "-o", str(nes_path), str(obj_path)],
                        check=True, capture_output=True, text=True)
    except FileNotFoundError:
        pytest.skip("cc65 toolchain (ca65/ld65) not available")
    except subprocess.CalledProcessError as e:
        pytest.fail(f"cc65 assembly/link failed: {e.stderr}")
    return nes_path


NROM_CFG = """MEMORY {
    ZP:      start = $0000, size = $0100, type = rw;
    HEADER:  start = $0000, size = $0010, type = ro, file = %O, fill = yes;
    PRG:     start = $8000, size = $7FFA, type = ro, file = %O, fill = yes, fillval = $EA;
    VECTORS: start = $FFFA, size = $0006, type = ro, file = %O, fill = yes;
    CHR:     start = $0000, size = $2000, type = ro, file = %O, fill = yes;
}
SEGMENTS {
    HEADER:   load = HEADER, type = ro;
    ZEROPAGE: load = ZP, type = zp;
    CODE:     load = PRG, type = ro;
    VECTORS:  load = VECTORS, type = ro;
    CHARS:    load = CHR, type = ro;
}
"""

NROM_HEADER = """.segment "HEADER"
    .byte "NES", $1A
    .byte 2
    .byte 1
    .byte $00
    .byte $00
    .byte $00,$00,$00,$00,$00,$00,$00,$00
"""

BROKEN_RESET_ASM = NROM_HEADER + """
.segment "CODE"
reset:
    sei
    cld
    ldx #$FF
    txs
    ; NO vblank wait -- reproduces the exact #517/MAP-2026-08-24-1 defect:
    ; enabling NMI immediately after reset, before the PPU warm-up window
    ; closes. Real hardware/an accurate emulator drops this write.
    lda #$80
    sta $2000
mainloop:
    jmp mainloop

nmi:
    pha
    lda #$0F
    sta $4015
    pla
    rti

irq:
    rti

.segment "VECTORS"
    .word nmi
    .word reset
    .word irq

.segment "CHARS"
    .res 8192
"""

FIXED_RESET_ASM = NROM_HEADER + """
.segment "CODE"
reset:
    sei
    cld
    ldx #$FF
    txs
@vblankwait1:
    bit $2002
    bpl @vblankwait1
@vblankwait2:
    bit $2002
    bpl @vblankwait2
    lda #$80
    sta $2000
mainloop:
    jmp mainloop

nmi:
    pha
    lda #$0F
    sta $4015
    lda #$25
    sta $4000
    pla
    rti

irq:
    rti

.segment "VECTORS"
    .word nmi
    .word reset
    .word irq

.segment "CHARS"
    .res 8192
"""

NO_NMI_ENABLE_ASM = NROM_HEADER + """
.segment "CODE"
reset:
    sei
    cld
    ldx #$FF
    txs
@vblankwait1:
    bit $2002
    bpl @vblankwait1
@vblankwait2:
    bit $2002
    bpl @vblankwait2
    ; Deliberately never enables NMI at all (distinct failure mode from
    ; the timing bug: this ROM never even tries).
mainloop:
    jmp mainloop

nmi:
    rti

irq:
    rti

.segment "VECTORS"
    .word nmi
    .word reset
    .word irq

.segment "CHARS"
    .res 8192
"""


class TestSmokeTestCatchesRealDefects:
    def test_smoke_test_catches_the_actual_vblank_wait_bug_this_session_fixed(self, tmp_path):
        """The regression guard: a ROM missing the 2-vblank warm-up wait
        before enabling NMI must be reported as nmi_fired=False, exactly
        reproducing why canyon.mid was silent before the fix in
        nes/project_builder.py."""
        rom_path = _assemble(BROKEN_RESET_ASM, NROM_CFG, tmp_path)
        result = run_smoke_test(rom_path, max_frames=10)
        assert result.mapper_supported
        assert not result.nmi_fired, (
            "smoke test should have caught the dropped $2000 write -- "
            "NMI must never actually fire on this ROM")
        assert result.nmi_count == 0
        assert not result.notes_detected

    def test_smoke_test_confirms_the_fixed_reset_routine_actually_works(self, tmp_path):
        """The positive control: the correct 2-vblank-wait pattern (the
        fix this session applied) must result in NMI firing and a real
        per-frame APU write being observed."""
        rom_path = _assemble(FIXED_RESET_ASM, NROM_CFG, tmp_path)
        result = run_smoke_test(rom_path, max_frames=10)
        assert result.mapper_supported
        assert result.nmi_fired
        assert result.nmi_count >= 1
        assert result.notes_detected

    def test_smoke_test_catches_nmi_never_enabled_at_all(self, tmp_path):
        """Distinct failure mode from the timing bug: a ROM that never
        even attempts to enable NMI should also report nmi_fired=False,
        not be confused with the warm-up-timing case."""
        rom_path = _assemble(NO_NMI_ENABLE_ASM, NROM_CFG, tmp_path)
        result = run_smoke_test(rom_path, max_frames=10)
        assert result.mapper_supported
        assert not result.nmi_fired
        assert not result.notes_detected

    def test_unsupported_mapper_reports_not_supported_not_a_defect(self, tmp_path):
        """A mapper this smoke test doesn't implement (e.g. MMC1) must be
        reported as mapper_supported=False, distinct from an actual defect
        -- callers must skip the check, not fail the ROM."""
        # Fabricate a minimal, structurally valid iNES header claiming
        # mapper 1 (MMC1) -- flags6 high nibble = 1.
        header = bytearray(16)
        header[0:4] = b"NES\x1a"
        header[4] = 2   # 2 * 16KB PRG
        header[5] = 1   # 1 * 8KB CHR
        header[6] = 0x10  # mapper 1 low nibble
        header[7] = 0x00
        rom_bytes = bytes(header) + bytes(32768) + bytes(8192)
        rom_path = tmp_path / "mmc1_stub.nes"
        rom_path.write_bytes(rom_bytes)

        result = run_smoke_test(rom_path)
        assert not result.mapper_supported
        assert result.mapper_number == 1

    def test_malformed_rom_reports_unsupported_with_error_not_a_crash(self, tmp_path):
        rom_path = tmp_path / "garbage.nes"
        rom_path.write_bytes(b"not a rom at all")
        result = run_smoke_test(rom_path)
        assert not result.mapper_supported
        assert result.error is not None


class TestEndToEndPipelineBuild:
    """The real pipeline, not hand-crafted asm -- confirms the fix holds
    for an actual generated ROM, not just a synthetic repro."""

    def test_real_pipeline_build_passes_the_smoke_test(self, tmp_path):
        import shutil
        if shutil.which("ca65") is None or shutil.which("ld65") is None:
            pytest.skip("cc65 toolchain not available")

        import sys
        rom_path = tmp_path / "smoke.nes"
        proc = subprocess.run(
            [sys.executable, "main.py", "test_midi/simple_loop.mid", str(rom_path)],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert rom_path.exists()

        result = run_smoke_test(rom_path, max_frames=30)
        assert result.mapper_supported
        assert result.nmi_fired, (
            "a real pipeline-built ROM must actually enable and fire NMI "
            "-- see nes/project_builder.py's reset routine")
        assert result.notes_detected


class TestWarmupConstant:
    def test_warmup_cycles_matches_documented_hardware_value(self):
        """Pin the constant itself -- a silent change here would quietly
        weaken (or over-strengthen) every test above."""
        assert PPU_WARMUP_CYCLES == 29658
