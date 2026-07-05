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


class TestNoUnusedOamSegment(unittest.TestCase):
    """Regression (#215/MAP-4): MMC3's linker config used to reserve an OAM
    MEMORY region and declare a matching SEGMENTS entry that nothing ever
    emitted into, producing a harmless-but-noisy ld65 warning on every build."""

    def test_mmc3_linker_config_has_no_oam_entries(self):
        cfg = MMC3Mapper().generate_linker_config()
        self.assertNotIn("OAM", cfg)

    def test_no_mapper_declares_an_oam_segment(self):
        for mapper_cls in ALL_MAPPERS:
            cfg = mapper_cls().generate_linker_config()
            self.assertNotIn("OAM", cfg, f"{mapper_cls.__name__} still declares OAM")


class TestHeaderAsmIsBareBytes(unittest.TestCase):
    """Regression (#216/MAP-5): every mapper's generate_header_asm() must
    return bare `.byte` rows with no `.segment` directive of its own -- the
    CA65 exporter is the sole owner of `.segment "HEADER"` (#22)."""

    def test_no_mapper_embeds_its_own_header_segment(self):
        for mapper_cls in ALL_MAPPERS:
            header_asm = mapper_cls().generate_header_asm()
            self.assertNotIn('.segment "HEADER"', header_asm,
                              f"{mapper_cls.__name__} embeds its own HEADER segment")


class TestMMC1BankedLinkerConfig(unittest.TestCase):
    """Regression (#255/MAP-2026-07-05-1): MMC1's switchable pool must be
    declared as separate per-bank $8000-based MEMORY/SEGMENTS entries (like
    MMC3), not one linear region -- a linear PRGSWAP region let ld65 place
    RODATA past the first 16KB at run addresses >= $C000, aliasing the fixed
    engine bank at runtime with no link error."""

    def test_direct_export_bank_size_is_the_16kb_window(self):
        self.assertEqual(MMC1Mapper().direct_export_bank_size(), 0x4000)

    def test_other_mappers_do_not_need_direct_export_bank_switching(self):
        # NROM is a single flat region; MMC3's direct export uses its
        # always-mapped fixed windows. Neither needs runtime bank-switching.
        self.assertIsNone(NROMMapper().direct_export_bank_size())
        self.assertIsNone(MMC3Mapper().direct_export_bank_size())

    def test_linker_config_declares_one_memory_region_per_switchable_bank(self):
        mmc1 = MMC1Mapper()
        cfg = mmc1.generate_linker_config()
        for i in range(mmc1.SWAP_BANK_COUNT):
            self.assertIn(f'PRG_BANK_{i:02d}: start = $8000', cfg,
                          f"missing MEMORY region for bank {i}")
            self.assertIn(f'RODATA_BANK_{i:02d}: load = PRG_BANK_{i:02d}', cfg,
                          f"missing SEGMENTS entry for bank {i}")
        # No single linear region spanning the whole switchable pool remains.
        self.assertNotIn('$1C000', cfg)

    def test_plain_rodata_segment_still_has_a_home(self):
        """The DPCM packer/project-builder stub still emit a plain
        `.segment "RODATA"` (unrelated to the exporter's per-bank frame-table
        packing) -- it must still resolve to a real MEMORY region, sharing
        bank 0, or ld65 fails with 'Missing memory area assignment'."""
        cfg = MMC1Mapper().generate_linker_config()
        self.assertIn('RODATA:   load = PRG_BANK_00', cfg)

    def test_fixed_bank_unchanged_for_code_and_vectors(self):
        cfg = MMC1Mapper().generate_linker_config()
        self.assertIn('CODE:     load = PRGFIXED', cfg)
        self.assertIn('VECTORS:  load = PRGFIXED', cfg)

    def test_validate_segment_sizes_flags_bank_overflow(self):
        mmc1 = MMC1Mapper()
        errors = mmc1.validate_segment_sizes({'RODATA_BANK_00': mmc1.PRG_WINDOW_SIZE + 1})
        self.assertTrue(errors, "a single bank segment over 16KB must be flagged")

    def test_validate_segment_sizes_sums_plain_rodata_with_bank_00(self):
        """Plain RODATA (DPCM stub/packer) shares bank 0 with
        RODATA_BANK_00's frame tables -- their combined size, not each in
        isolation, must be checked against the 16KB window."""
        mmc1 = MMC1Mapper()
        half = mmc1.PRG_WINDOW_SIZE // 2 + 100
        errors = mmc1.validate_segment_sizes({'RODATA_BANK_00': half, 'RODATA': half})
        self.assertTrue(errors, "combined bank-0 usage over 16KB must be flagged")
        # Individually each fits; only combined they overflow.
        self.assertLess(half, mmc1.PRG_WINDOW_SIZE)

    def test_validate_segment_sizes_flags_bank_index_beyond_swap_count(self):
        mmc1 = MMC1Mapper()
        errors = mmc1.validate_segment_sizes({f'RODATA_BANK_{mmc1.SWAP_BANK_COUNT:02d}': 100})
        self.assertTrue(errors, "a bank index beyond SWAP_BANK_COUNT must be flagged")

    def test_validate_segment_sizes_accepts_well_formed_multi_bank_usage(self):
        mmc1 = MMC1Mapper()
        segment_sizes = {f'RODATA_BANK_{i:02d}': mmc1.PRG_WINDOW_SIZE
                          for i in range(mmc1.SWAP_BANK_COUNT)}
        self.assertEqual(mmc1.validate_segment_sizes(segment_sizes), [])

    def test_get_data_capacity_unchanged_at_112kb(self):
        # Bank-switching now delivers the real 112KB honestly, instead of
        # capping capacity to the addressable window (the alternative,
        # cheaper fix this issue considered but did not take).
        self.assertEqual(MMC1Mapper().get_data_capacity(), 112 * 1024)


if __name__ == "__main__":
    unittest.main()
