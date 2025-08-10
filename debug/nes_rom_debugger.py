#!/usr/bin/env python3
"""
NES ROM Debugger and Analyzer
Analyzes generated NES ROMs for common issues and provides debugging information.
"""

import struct
import sys
import os
from pathlib import Path

class NESROMDebugger:
    def __init__(self, rom_path):
        self.rom_path = Path(rom_path)
        self.data = None
        self.header = {}
        self.load_rom()
    
    def load_rom(self):
        """Load and validate ROM file"""
        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM file not found: {self.rom_path}")
        
        with open(self.rom_path, 'rb') as f:
            self.data = f.read()
        
        if len(self.data) < 16:
            raise ValueError("ROM file too small - invalid NES ROM")
        
        # Parse iNES header
        signature = self.data[:4]
        if signature != b'NES\x1a':
            raise ValueError(f"Invalid NES signature: {signature}")
        
        self.header = {
            'signature': signature,
            'prg_rom_size': self.data[4] * 16 * 1024,  # 16KB units
            'chr_rom_size': self.data[5] * 8 * 1024,   # 8KB units
            'flags_6': self.data[6],
            'flags_7': self.data[7],
            'mapper': ((self.data[7] & 0xF0) | (self.data[6] >> 4)),
            'mirroring': 'vertical' if (self.data[6] & 0x01) else 'horizontal',
            'battery': bool(self.data[6] & 0x02),
            'trainer': bool(self.data[6] & 0x04),
            'four_screen': bool(self.data[6] & 0x08),
        }
    
    def print_header_info(self):
        """Print detailed header information"""
        print("=" * 60)
        print("🔍 NES ROM Header Analysis")
        print("=" * 60)
        print(f"📁 File: {self.rom_path.name}")
        print(f"💾 File Size: {len(self.data):,} bytes ({len(self.data)/1024:.1f} KB)")
        print(f"🎮 Signature: {self.header['signature']}")
        print(f"📦 PRG-ROM Size: {self.header['prg_rom_size']:,} bytes ({self.header['prg_rom_size']//1024} KB)")
        print(f"🎨 CHR-ROM Size: {self.header['chr_rom_size']:,} bytes ({self.header['chr_rom_size']//1024} KB)")
        print(f"🗺️  Mapper: {self.header['mapper']} ({self.get_mapper_name()})")
        print(f"🔄 Mirroring: {self.header['mirroring']}")
        print(f"🔋 Battery: {self.header['battery']}")
        print(f"🏃 Trainer: {self.header['trainer']}")
        print(f"📺 Four Screen: {self.header['four_screen']}")
        print()
    
    def get_mapper_name(self):
        """Get human-readable mapper name"""
        mapper_names = {
            0: "NROM",
            1: "MMC1",
            2: "UxROM", 
            3: "CNROM",
            4: "MMC3",
            7: "AxROM",
            9: "MMC2",
            10: "MMC4",
            11: "Color Dreams",
        }
        return mapper_names.get(self.header['mapper'], f"Unknown Mapper {self.header['mapper']}")
    
    def analyze_prg_rom(self):
        """Analyze PRG-ROM for common patterns and issues"""
        print("🔧 PRG-ROM Analysis")
        print("-" * 40)
        
        header_size = 16 + (512 if self.header['trainer'] else 0)
        prg_start = header_size
        prg_end = prg_start + self.header['prg_rom_size']
        prg_data = self.data[prg_start:prg_end]
        
        print(f"📍 PRG-ROM Location: 0x{prg_start:04X} - 0x{prg_end-1:04X}")
        print(f"📏 PRG-ROM Size: {len(prg_data):,} bytes")
        
        # Check reset vector - different approaches for different mappers
        if self.header['mapper'] == 1:  # MMC1
            # For MMC1, vectors are at the very end of the ROM file (standard NES vector positions)
            if len(self.data) >= 16 + 6:  # Header + at least 6 bytes for vectors
                # Read vectors from standard NES positions (last 6 bytes of ROM)
                # NMI at -6, Reset at -4, IRQ at -2 (from end)
                nmi_vector = struct.unpack('<H', self.data[-6:-4])[0]
                reset_vector = struct.unpack('<H', self.data[-4:-2])[0] 
                irq_vector = struct.unpack('<H', self.data[-2:])[0]
                print(f"🔄 Reset Vector: 0x{reset_vector:04X}")
                print(f"🔄 NMI Vector: 0x{nmi_vector:04X}")
                print(f"🔄 IRQ Vector: 0x{irq_vector:04X}")
                
                if reset_vector < 0x8000:
                    print("⚠️  WARNING: Reset vector points to RAM/unused area")
        elif len(prg_data) >= 32768:  # Standard 32KB ROM (NROM, etc.)
            reset_vector_offset = len(prg_data) - 4
            reset_vector = struct.unpack('<H', prg_data[reset_vector_offset:reset_vector_offset+2])[0]
            print(f"🔄 Reset Vector: 0x{reset_vector:04X}")
            
            if reset_vector < 0x8000:
                print("⚠️  WARNING: Reset vector points to RAM/unused area")
        
        # Check for common patterns
        zero_count = prg_data.count(0)
        ff_count = prg_data.count(0xFF)
        
        print(f"🟦 Zero bytes: {zero_count:,} ({zero_count/len(prg_data)*100:.1f}%)")
        print(f"🟨 0xFF bytes: {ff_count:,} ({ff_count/len(prg_data)*100:.1f}%)")
        
        if zero_count > len(prg_data) * 0.8:
            print("⚠️  WARNING: ROM appears mostly empty (80%+ zeros)")
        
        # Look for our music data markers
        music_markers = [
            b'MUSIC_DATA_START',
            b'PATTERNS_START',
            b'music_init',
            b'music_update'
        ]
        
        found_markers = []
        for marker in music_markers:
            if marker in prg_data:
                offset = prg_data.find(marker)
                found_markers.append((marker.decode('ascii'), offset))
                print(f"🎵 Found {marker.decode('ascii')} at offset 0x{offset:04X}")
        
        if not found_markers:
            print("❌ No music data markers found - ROM may not contain our generated code")
        
        print()
    
    def analyze_potential_issues(self):
        """Look for common ROM generation issues"""
        print("🚨 Potential Issues Analysis")
        print("-" * 40)
        
        issues_found = 0
        
        # Check file size alignment
        expected_size = 16 + self.header['prg_rom_size'] + self.header['chr_rom_size']
        if self.header['trainer']:
            expected_size += 512
        
        if len(self.data) != expected_size:
            print(f"❌ File size mismatch: Expected {expected_size}, got {len(self.data)}")
            issues_found += 1
        
        # Check mapper compatibility
        if self.header['mapper'] == 1 and self.header['prg_rom_size'] < 32768:
            print("❌ MMC1 mapper with less than 32KB PRG-ROM is unusual")
            issues_found += 1
        
        # Check reset vectors for MMC1
        if self.header['mapper'] == 1:
            print("🔍 MMC1 specific checks:")
            print("  - MMC1 uses bank switching")
            print("  - Reset vector should be in fixed bank (last 16KB)")
            print("  - Make sure music routines are in correct banks")
        
        # Check for obvious corruption
        header_size = 16 + (512 if self.header['trainer'] else 0)
        prg_start = header_size
        prg_end = prg_start + self.header['prg_rom_size']
        prg_data = self.data[prg_start:prg_end]
        
        # Check for repeated patterns that might indicate generation errors
        chunk_size = 256
        chunks = [prg_data[i:i+chunk_size] for i in range(0, len(prg_data), chunk_size)]
        unique_chunks = len(set(chunks))
        
        if unique_chunks < len(chunks) * 0.5:
            print(f"⚠️  WARNING: High repetition in PRG-ROM ({unique_chunks}/{len(chunks)} unique chunks)")
            issues_found += 1
        
        if issues_found == 0:
            print("✅ No obvious issues detected")
        else:
            print(f"❌ Found {issues_found} potential issues")
        
        print()
    
    def create_memory_map(self):
        """Create a visual memory map"""
        print("🗺️  Memory Map")
        print("-" * 40)
        
        header_size = 16 + (512 if self.header['trainer'] else 0)
        
        print(f"0x0000-0x000F: iNES Header (16 bytes)")
        if self.header['trainer']:
            print(f"0x0010-0x020F: Trainer (512 bytes)")
        
        prg_start = header_size
        prg_end = prg_start + self.header['prg_rom_size']
        print(f"0x{prg_start:04X}-0x{prg_end-1:04X}: PRG-ROM ({self.header['prg_rom_size']:,} bytes)")
        
        if self.header['chr_rom_size'] > 0:
            chr_start = prg_end
            chr_end = chr_start + self.header['chr_rom_size']
            print(f"0x{chr_start:04X}-0x{chr_end-1:04X}: CHR-ROM ({self.header['chr_rom_size']:,} bytes)")
        
        print()
        
        # CPU memory map
        print("CPU Memory Map (Runtime):")
        print("0x0000-0x07FF: RAM")
        print("0x2000-0x2007: PPU Registers")
        print("0x4000-0x4017: APU Registers")
        print("0x6000-0x7FFF: SRAM (if present)")
        if self.header['mapper'] == 0:
            print("0x8000-0xFFFF: PRG-ROM (fixed)")
        elif self.header['mapper'] == 1:
            print("0x8000-0xBFFF: PRG-ROM (switchable)")
            print("0xC000-0xFFFF: PRG-ROM (fixed, last 16KB)")
        print()
    
    def generate_debug_info(self):
        """Generate comprehensive debug information"""
        self.print_header_info()
        self.analyze_prg_rom()
        self.analyze_potential_issues()
        self.create_memory_map()
        
        # Save debug info to file
        debug_file = self.rom_path.with_suffix('.debug.txt')
        with open(debug_file, 'w') as f:
            # Redirect stdout to file temporarily
            import contextlib
            with contextlib.redirect_stdout(f):
                self.print_header_info()
                self.analyze_prg_rom()
                self.analyze_potential_issues()
                self.create_memory_map()
        
        print(f"💾 Debug information saved to: {debug_file}")
    
    def hex_dump(self, start_offset=0, length=256):
        """Generate hex dump of ROM data"""
        print(f"📋 Hex Dump (offset 0x{start_offset:04X}, {length} bytes)")
        print("-" * 60)
        
        for i in range(0, length, 16):
            offset = start_offset + i
            if offset >= len(self.data):
                break
            
            line_data = self.data[offset:offset+16]
            hex_part = ' '.join(f'{b:02x}' for b in line_data)
            ascii_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in line_data)
            
            print(f"{offset:04X}: {hex_part:<48} |{ascii_part}|")
        print()

def main():
    if len(sys.argv) < 2:
        print("Usage: python nes_rom_debugger.py <rom_file.nes> [options]")
        print("Options:")
        print("  --hex-dump [offset] [length]  : Show hex dump")
        print("  --quick                       : Quick analysis only")
        sys.exit(1)
    
    rom_file = sys.argv[1]
    
    try:
        debugger = NESROMDebugger(rom_file)
        
        if '--quick' in sys.argv:
            debugger.print_header_info()
        elif '--hex-dump' in sys.argv:
            hex_idx = sys.argv.index('--hex-dump')
            offset = int(sys.argv[hex_idx + 1], 0) if len(sys.argv) > hex_idx + 1 else 0
            length = int(sys.argv[hex_idx + 2], 0) if len(sys.argv) > hex_idx + 2 else 256
            debugger.hex_dump(offset, length)
        else:
            debugger.generate_debug_info()
    
    except Exception as e:
        print(f"❌ Error analyzing ROM: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
