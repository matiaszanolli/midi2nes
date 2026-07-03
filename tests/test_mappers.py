"""Dedicated mapper tests (#47 / REG-07).

Mappers were only exercised indirectly through test_ca65_export.py. These pin the
three things a wrong mapper would ship unguarded:
  1. MapperFactory size-based auto-select (NROM -> MMC1 -> MMC3 thresholds).
  2. iNES header <-> mapper-number / PRG-size consistency for every mapper.
  3. Capacity-overrun detection (raise / escalate, never silent truncation).
"""

import unittest

from mappers.factory import MapperFactory, get_mapper
from mappers.nrom import NROMMapper
from mappers.mmc1 import MMC1Mapper
from mappers.mmc3 import MMC3Mapper

ALL_MAPPERS = [NROMMapper, MMC1Mapper, MMC3Mapper]


def parse_ines_header(header_asm: str) -> list:
    """Flatten a mapper's generate_header_asm() into the raw iNES header bytes.

    Handles `.byte "NES", $1A`, `.byte $40`, and decimal `.byte 32`, dropping
    `;` comments. Returns the byte list (>= 16 bytes for a valid header)."""
    out = []
    for raw in header_asm.splitlines():
        line = raw.split(";", 1)[0].strip()  # drop comment
        if not line.lower().startswith(".byte"):
            continue
        payload = line[len(".byte"):].strip()
        for tok in payload.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if tok.startswith('"') and tok.endswith('"'):
                out.extend(ord(c) for c in tok[1:-1])
            elif tok.startswith("$"):
                out.append(int(tok[1:], 16))
            else:
                out.append(int(tok, 10))
    return out


class TestMapperFactoryAutoSelect(unittest.TestCase):
    """auto_select must pick the smallest mapper whose capacity fits the data."""

    def test_small_data_selects_nrom(self):
        # Well under NROM capacity (32KB - 2KB = 30720).
        self.assertIsInstance(MapperFactory.auto_select(1024), NROMMapper)

    def test_just_over_nrom_selects_mmc1(self):
        nrom_cap = NROMMapper().get_data_capacity()
        self.assertIsInstance(MapperFactory.auto_select(nrom_cap + 1), MMC1Mapper)

    def test_just_over_mmc1_selects_mmc3(self):
        mmc1_cap = MMC1Mapper().get_data_capacity()
        self.assertIsInstance(MapperFactory.auto_select(mmc1_cap + 1), MMC3Mapper)

    def test_exact_capacity_boundaries_do_not_escalate(self):
        # Data exactly at a mapper's capacity still fits that mapper.
        self.assertIsInstance(
            MapperFactory.auto_select(NROMMapper().get_data_capacity()), NROMMapper)
        self.assertIsInstance(
            MapperFactory.auto_select(MMC1Mapper().get_data_capacity()), MMC1Mapper)

    def test_ascending_capacity_ordering(self):
        # The factory's smallest-first ordering must actually be ascending.
        caps = [m().get_data_capacity() for m in ALL_MAPPERS]
        self.assertEqual(caps, sorted(caps))

    def test_get_mapper_auto_helper(self):
        self.assertIsInstance(get_mapper("auto", 1024), NROMMapper)
        # No size given -> pipeline default (MMC3).
        self.assertIsInstance(get_mapper("auto", 0), MMC3Mapper)


class TestMapperHeaderConsistency(unittest.TestCase):
    """The generated iNES header must agree with the mapper's own metadata —
    a header/number drift is HIGH severity (wrong mapper on every ROM)."""

    def test_header_mapper_number_matches(self):
        for mapper_cls in ALL_MAPPERS:
            mapper = mapper_cls()
            emitted = parse_ines_header(mapper.generate_header_asm())
            # The `.segment "HEADER"` region is a fixed 16 bytes with `fill = yes`
            # in every mapper's linker config, so a header that emits fewer than
            # 16 bytes is zero-filled to 16 (legal only because mappers 0/1 have
            # flags7 == $00). Model that fill before reading the flag bytes.
            self.assertLessEqual(len(emitted), 16,
                                 f"{mapper.name} header overflows the 16-byte region")
            header = emitted + [0] * (16 - len(emitted))
            self.assertEqual(header[0:4], [ord(c) for c in "NES"] + [0x1A],
                             f"{mapper.name} missing NES magic")
            # iNES mapper number: low nibble from flags6 (byte 6),
            # high nibble from flags7 (byte 7).
            header_mapper = (header[6] >> 4) | (header[7] & 0xF0)
            self.assertEqual(header_mapper, mapper.mapper_number,
                             f"{mapper.name} header mapper {header_mapper} != "
                             f"declared {mapper.mapper_number}")

    def test_header_prg_size_matches_prg_rom_size(self):
        for mapper_cls in ALL_MAPPERS:
            mapper = mapper_cls()
            header = parse_ines_header(mapper.generate_header_asm())
            # Byte 4 is the 16KB PRG-bank count.
            self.assertEqual(header[4] * 16384, mapper.prg_rom_size,
                             f"{mapper.name} header PRG size disagrees with prg_rom_size")

    def test_linker_config_nonempty_and_bank_math(self):
        for mapper_cls in ALL_MAPPERS:
            mapper = mapper_cls()
            cfg = mapper.generate_linker_config()
            self.assertTrue(cfg.strip(), f"{mapper.name} linker config is empty")
            # PRG must divide evenly into banks (the linker lays PRG out in banks).
            self.assertEqual(mapper.prg_rom_size % mapper.prg_bank_size, 0)
            self.assertEqual(mapper.prg_bank_count,
                             mapper.prg_rom_size // mapper.prg_bank_size)


class TestMapperCapacityOverrun(unittest.TestCase):
    """Overrun must raise / escalate, never silently truncate."""

    def test_auto_select_raises_when_nothing_fits(self):
        too_big = MMC3Mapper().get_data_capacity() + 1
        with self.assertRaises(ValueError):
            MapperFactory.auto_select(too_big)

    def test_can_fit_data_boundary(self):
        for mapper_cls in ALL_MAPPERS:
            mapper = mapper_cls()
            cap = mapper.get_data_capacity()
            self.assertTrue(mapper.can_fit_data(cap))
            self.assertFalse(mapper.can_fit_data(cap + 1))

    def test_validate_segment_sizes_flags_overflow(self):
        # NROM/MMC1 use the flat base check (sum of all segments vs capacity).
        for mapper_cls in (NROMMapper, MMC1Mapper):
            mapper = mapper_cls()
            over = {"RODATA": mapper.get_data_capacity() + 1}
            self.assertTrue(mapper.validate_segment_sizes(over),
                            f"{mapper.name} did not flag an overflowing segment")
            self.assertEqual(mapper.validate_segment_sizes({"RODATA": 512}), [])

        # MMC3 is region-aware: a RODATA blob larger than the 8 KB fixed bank
        # (the direct-export path packs frame tables there) must be flagged, even
        # though the total is well under the 512 KB PRG (#126).
        mmc3 = MMC3Mapper()
        self.assertTrue(mmc3.validate_segment_sizes({"RODATA": mmc3.PRG_FIX_SIZE}),
                        "MMC3 did not flag a fixed-bank (PRG_FIX) overflow")
        self.assertEqual(mmc3.validate_segment_sizes({"RODATA": 512}), [])

    def test_validate_segment_sizes_sums_shared_bank_nn_and_dpcm_nn(self):
        # Regression (MAP-1 / #212): BANK_NN (sequence bytecode) and DPCM_NN
        # (drum samples) load into the SAME physical PRG_BANK_NN region for a
        # given NN, but the exporter and DPCM packer assign bank indices
        # independently. Two segments that individually fit under the 8 KB
        # window can still overflow their shared bank when combined — this
        # exact byte count (7535 + 1217 = 8752, 560 over budget) reproduces
        # the reported ld65 link failure.
        mmc3 = MMC3Mapper()
        errors = mmc3.validate_segment_sizes({"BANK_00": 7535, "DPCM_00": 1217})
        self.assertTrue(errors, "combined BANK_00+DPCM_00 overflow was not flagged")
        self.assertIn("bank 0", errors[0])

        # Both segments individually pass the old per-segment check, proving
        # the old code would have missed this.
        self.assertLess(7535, mmc3.PRG_WINDOW_SIZE)
        self.assertLess(1217, mmc3.PRG_WINDOW_SIZE)

    def test_validate_segment_sizes_does_not_combine_different_banks(self):
        # Segments in different banks must NOT be summed together.
        mmc3 = MMC3Mapper()
        errors = mmc3.validate_segment_sizes({"BANK_00": 4000, "DPCM_01": 4000})
        self.assertEqual(errors, [])

    def test_validate_segment_sizes_still_flags_single_segment_overflow(self):
        # A single segment that alone exceeds the 8 KB window must still be
        # flagged (the combined check subsumes, not replaces, this case).
        mmc3 = MMC3Mapper()
        errors = mmc3.validate_segment_sizes({"BANK_05": mmc3.PRG_WINDOW_SIZE + 1})
        self.assertTrue(errors)
        self.assertIn("BANK_05", errors[0])


class TestMapperFactoryLookup(unittest.TestCase):
    """Name-based lookup + unknown-mapper handling."""

    def test_get_mapper_by_name(self):
        self.assertIsInstance(MapperFactory.get_mapper("nrom"), NROMMapper)
        self.assertIsInstance(MapperFactory.get_mapper("mmc1"), MMC1Mapper)
        self.assertIsInstance(MapperFactory.get_mapper("mmc3"), MMC3Mapper)

    def test_unknown_mapper_raises(self):
        with self.assertRaises(ValueError):
            MapperFactory.get_mapper("vrc6")

    def test_distinct_mapper_numbers(self):
        numbers = {m().mapper_number for m in ALL_MAPPERS}
        self.assertEqual(numbers, {0, 1, 4})  # NROM=0, MMC1=1, MMC3=4


if __name__ == "__main__":
    unittest.main()
