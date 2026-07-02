#!/usr/bin/env python3
"""Thin CLI wrapper around debug.rom_diagnostics.ROMDiagnostics (#130).

This used to be a second, independently hand-rolled iNES header/reset-vector
checker with its own divergent validity rules from the pipeline's real gate
(main.py:validate_rom -> ROMDiagnostics). It now delegates every check to the
same ROMDiagnostics the pipeline uses, so a validation rule fixed there is
automatically reflected here instead of needing a matching fix in two places.
"""

import sys
import os

from debug.rom_diagnostics import ROMDiagnostics


def validate_rom(filename):
    """Validate NES ROM basic structure"""
    print(f"🎮 Validating ROM: {filename}")
    print("=" * 50)

    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return False

    file_size = os.path.getsize(filename)
    print(f"📏 ROM size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")

    result = ROMDiagnostics(verbose=False).diagnose_rom(filename)

    if not result.is_valid_nes:
        print("❌ Invalid iNES header signature")
        return False

    print("✅ Valid iNES header found")

    prg_rom_size = result.prg_banks * 16384  # 16KB per bank
    chr_rom_size = result.chr_banks * 8192   # 8KB per bank

    print(f"🎯 PRG-ROM: {result.prg_banks} banks ({prg_rom_size / 1024:.0f} KB)")
    print(f"🎨 CHR-ROM: {result.chr_banks} banks ({chr_rom_size / 1024:.0f} KB)")

    # Mapper number is presentation-only (not a validity rule ROMDiagnostics
    # needs), so it is read directly from the header here rather than
    # duplicating any check.
    with open(filename, 'rb') as f:
        header = f.read(16)
    mapper = (header[7] & 0xF0) | (header[6] >> 4)
    print(f"🗺️  Mapper: {mapper}")

    print(f"📐 Expected size: {result.expected_size:,} bytes")
    if result.size_mismatch != 0:
        print(f"⚠️  Size mismatch! Actual: {file_size}, Expected: {result.expected_size}")
    else:
        print("✅ ROM size matches header specification")

    if result.reset_vectors:
        nmi_vector = result.reset_vectors.get('NMI', 0)
        reset_vector = result.reset_vectors.get('RESET', 0)
        irq_vector = result.reset_vectors.get('IRQ', 0)

        print(f"🔗 Reset vector:  ${reset_vector:04X}")
        print(f"🔗 NMI vector:    ${nmi_vector:04X}")
        print(f"🔗 IRQ vector:    ${irq_vector:04X}")

        if reset_vector == 0:
            print("❌ Reset vector is 0 - ROM won't boot!")
            return False
        elif not result.reset_vectors_valid:
            print(f"⚠️  Reset vector ${reset_vector:04X} is outside $8000-$FFFF - unusual for most mappers")
        else:
            print("✅ Reset vector looks valid")

    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_rom.py <rom_file>")
        sys.exit(1)

    success = validate_rom(sys.argv[1])
    sys.exit(0 if success else 1)
