#!/usr/bin/env python3

import struct

def check_rom(filename):
    with open(filename, 'rb') as f:
        # Read iNES header
        header = f.read(16)
        prg_size = header[4] * 16384  # PRG banks * 16KB each
        chr_size = header[5] * 8192   # CHR banks * 8KB each
        mapper = ((header[6] >> 4) | (header[7] & 0xF0))
        
        print(f'PRG-ROM Size: {prg_size} bytes ({prg_size//1024}KB)')
        print(f'CHR-ROM Size: {chr_size} bytes')
        print(f'Mapper: {mapper}')
        print(f'Mirroring: {"Vertical" if header[6] & 1 else "Horizontal"}')
        
        # Read first few bytes of PRG-ROM
        f.seek(16)  # Skip header
        prg_start = f.read(32)
        print(f'PRG-ROM start: {prg_start.hex()}')
        
        # Read reset vectors
        f.seek(-6, 2)  # Last 6 bytes
        vectors = f.read(6)
        nmi_vec = struct.unpack('<H', vectors[0:2])[0]
        rst_vec = struct.unpack('<H', vectors[2:4])[0] 
        irq_vec = struct.unpack('<H', vectors[4:6])[0]
        print(f'NMI Vector: ${nmi_vec:04X}')
        print(f'Reset Vector: ${rst_vec:04X}')  
        print(f'IRQ Vector: ${irq_vec:04X}')

if __name__ == "__main__":
    check_rom('input.nes')
