#!/usr/bin/env python3
"""
NES ROM Content Analyzer
Deep analysis of the actual generated ROM content to diagnose audio issues
"""

import struct
import sys
from pathlib import Path

class ROMContentAnalyzer:
    def __init__(self, rom_path):
        self.rom_path = Path(rom_path)
        self.rom_data = None
        self.load_rom()
    
    def load_rom(self):
        """Load ROM data"""
        with open(self.rom_path, 'rb') as f:
            self.rom_data = f.read()
    
    def find_actual_code_sections(self):
        """Find sections of ROM that contain actual code (not just zeros)"""
        print("🔍 Analyzing ROM Content Distribution")
        print("=" * 50)
        
        # Analyze in 1KB chunks
        chunk_size = 1024
        non_empty_sections = []
        
        for i in range(0, len(self.rom_data), chunk_size):
            chunk = self.rom_data[i:i+chunk_size]
            zero_count = chunk.count(0)
            ff_count = chunk.count(0xFF)
            
            # Consider a chunk "interesting" if it's less than 90% zeros/0xFF
            if (zero_count + ff_count) < len(chunk) * 0.9:
                non_empty_sections.append((i, chunk))
                print(f"  Active section at 0x{i:04X}-0x{i+len(chunk):04X} ({len(chunk)} bytes)")
                print(f"    Zeros: {zero_count}/{len(chunk)} ({zero_count/len(chunk)*100:.1f}%)")
                print(f"    0xFF: {ff_count}/{len(chunk)} ({ff_count/len(chunk)*100:.1f}%)")
        
        print(f"\nFound {len(non_empty_sections)} active sections out of {len(self.rom_data)//chunk_size} total")
        print()
        
        return non_empty_sections
    
    def analyze_music_data_structures(self):
        """Look for music data structures in the ROM"""
        print("🎼 Music Data Structure Analysis")
        print("=" * 50)
        
        # Look for note tables - sequences of 16-bit values in musical ranges
        potential_note_tables = []
        
        for i in range(16, len(self.rom_data) - 20, 2):  # Start after header, check 16-bit aligned
            # Read 10 consecutive 16-bit values
            values = []
            try:
                for j in range(10):
                    val = struct.unpack('<H', self.rom_data[i + j*2:i + j*2 + 2])[0]
                    values.append(val)
                
                # Check if this looks like a note table
                # NES timer values are typically 20-2000 for audible frequencies
                if all(20 <= v <= 2000 for v in values[:8]):
                    # Check if roughly descending (higher notes = lower timer values)
                    descending_count = sum(1 for k in range(len(values)-1) if values[k] >= values[k+1])
                    if descending_count >= 6:  # At least 6 out of 9 pairs are descending
                        potential_note_tables.append((i, values))
            except:
                continue
        
        if potential_note_tables:
            print("Found potential note tables:")
            for addr, values in potential_note_tables[:3]:  # Show first 3
                print(f"  Address 0x{addr:04X}: {values[:8]}")
                # Calculate frequencies
                freqs = []
                for val in values[:6]:
                    if val > 0:
                        freq = 1789773 / (16 * (val + 1))
                        freqs.append(f"{freq:.1f}Hz")
                print(f"    Frequencies: {freqs}")
        else:
            print("❌ No note tables found!")
        
        print()
    
    def analyze_pattern_data(self):
        """Look for pattern/frame data structures"""
        print("🎪 Pattern Data Analysis")
        print("=" * 50)
        
        # Look for sequences that could be music pattern data
        # Pattern data typically has: volume (0-15), timer_low, timer_high
        potential_patterns = []
        
        for i in range(16, len(self.rom_data) - 20):
            # Look for sequences of 3-byte patterns
            chunk = self.rom_data[i:i+15]  # 5 patterns of 3 bytes each
            
            # Check if this could be pattern data
            valid_pattern = True
            for j in range(0, min(15, len(chunk)), 3):
                if j + 2 < len(chunk):
                    volume = chunk[j]
                    timer_low = chunk[j+1]
                    timer_high = chunk[j+2]
                    
                    # Volume should be 0-15, timer_high should be 0-7 for musical notes
                    if volume > 15 or timer_high > 7:
                        valid_pattern = False
                        break
            
            if valid_pattern and len(chunk) >= 9:
                potential_patterns.append((i, chunk[:15]))
        
        if potential_patterns:
            print("Found potential pattern data:")
            for addr, data in potential_patterns[:3]:  # Show first 3
                print(f"  Address 0x{addr:04X}:")
                for j in range(0, len(data), 3):
                    if j + 2 < len(data):
                        vol = data[j]
                        timer_low = data[j+1] 
                        timer_high = data[j+2]
                        timer_val = timer_low | (timer_high << 8)
                        
                        if timer_val > 0:
                            freq = 1789773 / (16 * (timer_val + 1))
                            print(f"    Pattern {j//3}: Vol={vol}, Timer=${timer_val:04X} ({freq:.1f}Hz)")
                        else:
                            print(f"    Pattern {j//3}: Vol={vol}, Timer=${timer_val:04X} (silence)")
        else:
            print("❌ No pattern data found!")
        
        print()
    
    def analyze_code_quality(self):
        """Analyze the quality and completeness of the generated code"""
        print("⚙️ Code Quality Analysis")
        print("=" * 50)
        
        # Look for specific instruction patterns that indicate working music code
        prg_data = self.rom_data[16:]
        
        # Count different types of instructions
        instruction_counts = {
            'LDA_immediate': 0,    # 0xA9
            'LDA_absolute': 0,     # 0xAD
            'LDX_immediate': 0,    # 0xA2
            'STA_absolute': 0,     # 0x8D
            'JSR': 0,              # 0x20
            'RTS': 0,              # 0x60
            'BNE': 0,              # 0xD0
            'JMP_absolute': 0,     # 0x4C
        }
        
        for i, byte in enumerate(prg_data):
            if byte == 0xA9: instruction_counts['LDA_immediate'] += 1
            elif byte == 0xAD: instruction_counts['LDA_absolute'] += 1
            elif byte == 0xA2: instruction_counts['LDX_immediate'] += 1
            elif byte == 0x8D: instruction_counts['STA_absolute'] += 1
            elif byte == 0x20: instruction_counts['JSR'] += 1
            elif byte == 0x60: instruction_counts['RTS'] += 1
            elif byte == 0xD0: instruction_counts['BNE'] += 1
            elif byte == 0x4C: instruction_counts['JMP_absolute'] += 1
        
        print("Instruction frequency analysis:")
        total_instructions = sum(instruction_counts.values())
        for instr, count in instruction_counts.items():
            if count > 0:
                print(f"  {instr}: {count} ({count/total_instructions*100:.1f}%)")
        
        # Analyze instruction density
        non_zero_bytes = sum(1 for b in prg_data if b != 0)
        print(f"\nCode density: {non_zero_bytes}/{len(prg_data)} bytes ({non_zero_bytes/len(prg_data)*100:.1f}%)")
        
        if total_instructions < 20:
            print("⚠️ WARNING: Very few instructions found - code may not be generated properly")
        elif non_zero_bytes < len(prg_data) * 0.1:
            print("⚠️ WARNING: ROM is mostly empty - code generation may have failed")
        else:
            print("✅ ROM appears to contain substantial code")
        
        print()
    
    def find_string_markers(self):
        """Look for debug strings or markers in the ROM"""
        print("🏷️ String/Marker Analysis")
        print("=" * 50)
        
        # Look for ASCII strings that might be debug info
        potential_strings = []
        current_string = ""
        start_pos = None
        
        for i, byte in enumerate(self.rom_data):
            if 32 <= byte <= 126:  # Printable ASCII
                if start_pos is None:
                    start_pos = i
                current_string += chr(byte)
            else:
                if len(current_string) >= 4:  # Strings of 4+ chars
                    potential_strings.append((start_pos, current_string))
                current_string = ""
                start_pos = None
        
        if potential_strings:
            print("Found strings in ROM:")
            for addr, string in potential_strings:
                if 'music' in string.lower() or 'apu' in string.lower() or 'sound' in string.lower():
                    print(f"  0x{addr:04X}: '{string}' ⭐")
                elif len(string) <= 20:  # Short strings only
                    print(f"  0x{addr:04X}: '{string}'")
        else:
            print("❌ No readable strings found")
        
        print()
    
    def run_complete_analysis(self):
        """Run all analysis functions"""
        print("🔬 NES ROM Complete Content Analysis")
        print("🎯 ROM:", self.rom_path.name)
        print("💾 Size:", f"{len(self.rom_data):,} bytes")
        print("=" * 60)
        print()
        
        self.find_actual_code_sections()
        self.analyze_code_quality()
        self.analyze_music_data_structures()
        self.analyze_pattern_data()
        self.find_string_markers()
        
        print("=" * 60)
        print("🎯 Analysis Complete!")

def main():
    if len(sys.argv) < 2:
        print("Usage: python rom_content_analyzer.py <rom_file.nes>")
        sys.exit(1)
    
    rom_file = sys.argv[1]
    
    try:
        analyzer = ROMContentAnalyzer(rom_file)
        analyzer.run_complete_analysis()
    except Exception as e:
        print(f"❌ Error analyzing ROM: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
