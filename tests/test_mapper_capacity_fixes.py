"""Regression coverage for the 2026-07-19 mapper-audit fixes (#361/#362/#363).

- #361: MapperFactory.auto_select is export-mode-aware, so a direct
  (--no-patterns) auto-selection never picks a mapper its own direct pre-flight
  then rejects.
- #362: a direct-export DPCM music.asm carries an MMC3-only marker, so the split
  prepare/compile flow re-forces MMC3 / rejects a non-MMC3 --mapper up front.
- #363: the capacity pre-flight and mapper-recovery gates fire for library
  consumers (NESProjectBuilder / compile_rom), not only the main.py CLI.
"""

import pytest

from mappers.factory import MapperFactory
from mappers.nrom import NROMMapper
from mappers.mmc1 import MMC1Mapper
from mappers.mmc3 import MMC3Mapper


# ---------------------------------------------------------------------------
# #361: auto_select export-mode awareness
# ---------------------------------------------------------------------------

class TestAutoSelectDirectMode:
    def test_mmc3_direct_capacity_is_fixed_bank_not_full_prg(self):
        m = MMC3Mapper()
        # Direct export can't bank-pack, so the real budget is the fixed bank,
        # far below the 512 KB banked capacity.
        assert m.direct_export_capacity() == m.PRG_FIX_SIZE - m.FIXED_BANK_ENGINE_RESERVE
        assert m.direct_export_capacity() < m.get_data_capacity()

    def test_default_direct_capacity_matches_data_capacity(self):
        # NROM/MMC1 bin-pack (or are flat), so their direct budget == banked.
        for cls in (NROMMapper, MMC1Mapper):
            m = cls()
            assert m.direct_export_capacity() == m.get_data_capacity()

    def test_small_direct_selects_nrom(self):
        assert MapperFactory.auto_select(5 * 1024, direct=True).name == "NROM"

    def test_medium_direct_selects_mmc1_not_mmc3(self):
        # ~60 KB: too big for NROM (30 KB), fits MMC1's 112 KB pool. Old flat
        # ranking picked MMC3 here (522 KB) and the direct pre-flight then
        # rejected it (only ~6 KB fixed-bank budget).
        m = MapperFactory.auto_select(60 * 1024, direct=True)
        assert m.name == "MMC1"

    def test_selected_direct_mapper_respects_its_direct_budget(self):
        # The core #361 invariant: whatever auto_select(direct=True) returns, the
        # data size fits THAT mapper's real direct budget — no "auto picked X,
        # then X's pre-flight rejects it". (The old bug picked MMC3, whose ~6 KB
        # direct budget the 112 KB+ song blew past.)
        for size in (2 * 1024, 40 * 1024, 100 * 1024):
            m = MapperFactory.auto_select(size, direct=True)
            assert size <= m.direct_export_capacity(), (
                f"{m.name} auto-picked for {size} B but its direct budget is "
                f"{m.direct_export_capacity()} B")

    def test_nrom_pick_passes_flat_preflight(self):
        # A NROM direct export is one flat region, so a single RODATA of the
        # selected size must clear its (flat) pre-flight.
        size = 20 * 1024
        m = MapperFactory.auto_select(size, direct=True)
        assert m.name == "NROM"
        assert m.validate_segment_sizes({"RODATA": size}) == []

    def test_oversized_direct_raises_with_pattern_hint(self):
        with pytest.raises(ValueError) as exc:
            MapperFactory.auto_select(200 * 1024, direct=True)
        msg = str(exc.value)
        assert "direct-export" in msg
        assert "pattern compression" in msg

    def test_banked_mode_unchanged(self):
        # Non-direct (bytecode) selection still ranks by flat capacity: MMC3
        # remains the pick for a large song.
        assert MapperFactory.auto_select(200 * 1024).name == "MMC3"


# ---------------------------------------------------------------------------
# #362: direct-export DPCM marker + resolve_mapper enforcement
# ---------------------------------------------------------------------------

def _direct_frames_with_dpcm():
    return {
        "pulse1": {0: {"note": 60, "volume": 8}, 1: {"note": 62, "volume": 8}},
        "dpcm": {0: {"sample_id": 0}},
    }


def _direct_frames_no_dpcm():
    return {
        "pulse1": {0: {"note": 60, "volume": 8}, 1: {"note": 62, "volume": 8}},
    }


class TestDirectExportDpcmMarker:
    def test_exporter_stamps_marker_when_dpcm_present(self, tmp_path):
        from exporter.exporter_ca65 import CA65Exporter
        out = tmp_path / "music.asm"
        CA65Exporter().export_direct_frames(
            _direct_frames_with_dpcm(), str(out), standalone=False, mapper=MMC3Mapper()
        )
        assert "; Direct export DPCM (MMC3-only)" in out.read_text()

    def test_exporter_no_marker_without_dpcm(self, tmp_path):
        from exporter.exporter_ca65 import CA65Exporter
        out = tmp_path / "music.asm"
        CA65Exporter().export_direct_frames(
            _direct_frames_no_dpcm(), str(out), standalone=False, mapper=MMC3Mapper()
        )
        assert "; Direct export DPCM (MMC3-only)" not in out.read_text()

    def test_resolve_mapper_auto_forces_mmc3(self, tmp_path):
        import main
        asm = tmp_path / "music.asm"
        asm.write_text("; Direct export DPCM (MMC3-only)\n.segment \"RODATA\"\n"
                       "pulse1_note:\n    .byte $01,$02\n")
        assert main.resolve_mapper("auto", str(asm)).name == "MMC3"

    @pytest.mark.parametrize("choice", ["nrom", "mmc1"])
    def test_resolve_mapper_rejects_non_mmc3(self, tmp_path, choice):
        import main
        asm = tmp_path / "music.asm"
        asm.write_text("; Direct export DPCM (MMC3-only)\n.segment \"RODATA\"\n"
                       "pulse1_note:\n    .byte $01,$02\n")
        with pytest.raises(ValueError) as exc:
            main.resolve_mapper(choice, str(asm))
        assert "DPCM" in str(exc.value)

    def test_resolve_mapper_marker_absent_allows_nrom(self, tmp_path):
        import main
        asm = tmp_path / "music.asm"
        asm.write_text(".segment \"RODATA\"\npulse1_note:\n    .byte $01,$02\n")
        # No DPCM marker -> a small direct export may honor an explicit NROM.
        assert main.resolve_mapper("nrom", str(asm)).name == "NROM"


# ---------------------------------------------------------------------------
# #363: library-path capacity + mapper-recovery gates
# ---------------------------------------------------------------------------

class TinyMapper(NROMMapper):
    """A deliberately tiny capacity to trip the pre-flight without a huge asm."""

    def get_data_capacity(self) -> int:
        return 4


class TestLibraryCapacityGates:
    def test_prepare_project_runs_capacity_preflight(self, tmp_path):
        from nes.project_builder import NESProjectBuilder
        asm = tmp_path / "music.asm"
        asm.write_text('.segment "RODATA"\nbig:\n    .byte ' +
                       ",".join(["$00"] * 64) + "\n")
        builder = NESProjectBuilder(str(tmp_path / "proj"), mapper=TinyMapper())
        with pytest.raises(ValueError) as exc:
            builder.prepare_project(str(asm))
        assert "does not fit" in str(exc.value)

    def test_prepare_project_passes_when_within_capacity(self, tmp_path):
        from nes.project_builder import NESProjectBuilder
        asm = tmp_path / "music.asm"
        asm.write_text('.segment "RODATA"\nsmall:\n    .byte $00,$01\n')
        builder = NESProjectBuilder(str(tmp_path / "proj"), mapper=NROMMapper())
        assert builder.prepare_project(str(asm)) is True

    def test_compiler_recovers_mapper_from_cfg(self, tmp_path):
        from compiler.compiler import _recover_mapper_from_cfg
        from nes.project_builder import NES_CFG_MAPPER_MARKER
        cfg = tmp_path / "nes.cfg"
        cfg.write_text(f"{NES_CFG_MAPPER_MARKER}mmc1\nMEMORY {{}}\n")
        m = _recover_mapper_from_cfg(cfg)
        assert m is not None and m.name == "MMC1"

    def test_compiler_recover_returns_none_without_marker(self, tmp_path):
        from compiler.compiler import _recover_mapper_from_cfg
        cfg = tmp_path / "nes.cfg"
        cfg.write_text("MEMORY {}\n")
        assert _recover_mapper_from_cfg(cfg) is None
        assert _recover_mapper_from_cfg(tmp_path / "missing.cfg") is None

    def test_prepared_project_cfg_roundtrips_to_recovered_mapper(self, tmp_path):
        """End-to-end (no CC65): a project prepared with MMC1 stamps a cfg the
        compiler recovers back to MMC1, so its exact size check would fire."""
        from nes.project_builder import NESProjectBuilder
        from compiler.compiler import _recover_mapper_from_cfg
        asm = tmp_path / "music.asm"
        asm.write_text('.segment "RODATA"\nsmall:\n    .byte $00,$01\n')
        proj = tmp_path / "proj"
        NESProjectBuilder(str(proj), mapper=MMC1Mapper()).prepare_project(str(asm))
        recovered = _recover_mapper_from_cfg(proj / "nes.cfg")
        assert recovered is not None and recovered.name == "MMC1"
