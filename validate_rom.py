#!/usr/bin/env python3

import sys
import os

def validate_rom(filename):
    """Validate NES ROM basic structure"""
    print(f"🎮 Validating ROM: {filename}")
    print("=" * 50)
    
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return False
    
    with open(filename, 'rb') as f:
        rom_data = f.read()
    
    rom_size = len(rom_data)
    print(f"📏 ROM size: {rom_size:,} bytes ({rom_size/1024:.1f} KB)")
    
    # Check iNES header
    if len(rom_data) < 16:
        print("❌ ROM too small for iNES header")
        return False
    
    header = rom_data[:16]
    if header[:4] != b'NES\x1a':
        print("❌ Invalid iNES header signature")
        return False
    
    print("✅ Valid iNES header found")
    
    prg_banks = header[4]
    chr_banks = header[5]
    flags6 = header[6]
    flags7 = header[7]
    
    mapper = ((flags7 & 0xF0) | (flags6 >> 4))
    prg_rom_size = prg_banks * 16384  # 16KB per bank
    chr_rom_size = chr_banks * 8192   # 8KB per bank
    
    print(f"🎯 PRG-ROM: {prg_banks} banks ({prg_rom_size/1024:.0f} KB)")
    print(f"🎨 CHR-ROM: {chr_banks} banks ({chr_rom_size/1024:.0f} KB)")
    print(f"🗺️  Mapper: {mapper}")
    
    expected_size = 16 + prg_rom_size + chr_rom_size
    print(f"📐 Expected size: {expected_size:,} bytes")
    
    if rom_size != expected_size:
        print(f"⚠️  Size mismatch! Actual: {rom_size}, Expected: {expected_size}")
    else:
        print("✅ ROM size matches header specification")
    
    # Check reset vector (last 6 bytes of PRG-ROM)
    if rom_size >= 22:  # Header + at least 6 bytes
        vectors_offset = 16 + prg_rom_size - 6
        if vectors_offset < rom_size:
            vectors = rom_data[vectors_offset:vectors_offset+6]
            nmi_vector = vectors[0] | (vectors[1] << 8)
            reset_vector = vectors[2] | (vectors[3] << 8)
            irq_vector = vectors[4] | (vectors[5] << 8)
            
            print(f"🔗 Reset vector:  ${reset_vector:04X}")
            print(f"🔗 NMI vector:    ${nmi_vector:04X}")
            print(f"🔗 IRQ vector:    ${irq_vector:04X}")
            
            if reset_vector == 0:
                print("❌ Reset vector is 0 - ROM won't boot!")
                return False
            elif reset_vector < 0x8000:
                print(f"⚠️  Reset vector ${reset_vector:04X} is below $8000 - unusual for most mappers")
            else:
                print("✅ Reset vector looks valid")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_rom.py <rom_file>")
        sys.exit(1)
    
    success = validate_rom(sys.argv[1])
    sys.exit(0 if success else 1)
