#!/usr/bin/env python3
"""
NES Audio Subsystem Debugger
Analyzes NES ROMs for audio-related issues and provides detailed debugging information.
"""

import struct
import sys
from pathlib import Path

class NESAudioDebugger:
    def __init__(self, rom_path):
        self.rom_path = Path(rom_path)
        self.rom_data = None
        self.load_rom()
    
    def load_rom(self):
        """Load ROM data"""
        with open(self.rom_path, 'rb') as f:
            self.rom_data = f.read()
    
    def analyze_apu_register_usage(self):
        """Analyze how APU registers are being used in the code"""
        print("🎵 APU Register Usage Analysis")
        print("=" * 50)
        
        # APU register addresses and their purposes
        apu_registers = {
            0x4000: "Pulse 1 Duty/Length/Envelope/Volume",
            0x4001: "Pulse 1 Sweep",
            0x4002: "Pulse 1 Timer Low",
            0x4003: "Pulse 1 Timer High/Length",
            0x4004: "Pulse 2 Duty/Length/Envelope/Volume", 
            0x4005: "Pulse 2 Sweep",
            0x4006: "Pulse 2 Timer Low",
            0x4007: "Pulse 2 Timer High/Length",
            0x4008: "Triangle Linear Counter",
            0x400A: "Triangle Timer Low",
            0x400B: "Triangle Timer High/Length",
            0x400C: "Noise Volume/Envelope",
            0x400E: "Noise Period",
            0x400F: "Noise Length",
            0x4010: "DMC Rate/IRQ/Loop",
            0x4011: "DMC Direct Load",
            0x4012: "DMC Sample Address",
            0x4013: "DMC Sample Length",
            0x4015: "APU Status (Channel Enable)"
        }
        
        # Look for STA instructions to APU registers
        prg_start = 16
        prg_data = self.rom_data[prg_start:]
        
        found_registers = {}
        
        for i in range(len(prg_data) - 2):
            # Look for STA absolute addressing (0x8D)
            if prg_data[i] == 0x8D:
                addr = struct.unpack('<H', prg_data[i+1:i+3])[0]
                if addr in apu_registers:
                    if addr not in found_registers:
                        found_registers[addr] = 0
                    found_registers[addr] += 1
        
        if found_registers:
            print("Found APU register writes:")
            for addr in sorted(found_registers.keys()):
                print(f"  ${addr:04X}: {apu_registers[addr]} ({found_registers[addr]} occurrences)")
        else:
            print("❌ No APU register writes found!")
        
        print()
    
    def analyze_frequency_data(self):
        """Analyze frequency/timer data in the ROM"""
        print("🎼 Frequency/Timer Data Analysis")  
        print("=" * 50)
        
        # Look for timer tables with typical NES frequency values
        prg_start = 16
        prg_data = self.rom_data[prg_start:]
        
        # Search for sequences that look like timer values
        potential_tables = []
        
        for i in range(len(prg_data) - 10):
            # Look for descending sequences (common in note tables)
            sequence = prg_data[i:i+8]
            if len(sequence) >= 4:
                # Check if values are in typical NES timer range
                values = list(sequence)
                if all(0 < v <= 0x07FF for v in values[:4]):
                    # Check if it's roughly descending (higher notes = lower timer values)
                    if values[0] > values[1] > values[2] > values[3]:
                        potential_tables.append((i + prg_start, values))
        
        if potential_tables:
            print("Potential frequency/timer tables found:")
            for addr, values in potential_tables[:5]:  # Show first 5
                print(f"  Address 0x{addr:04X}: {[f'${v:02X}' for v in values[:8]]}")
                
                # Calculate approximate frequencies
                freqs = []
                for v in values[:4]:
                    if v > 0:
                        # NES APU formula: freq = CPU_CLOCK / (16 * (timer + 1))
                        freq = 1789773 / (16 * (v + 1))
                        freqs.append(freq)
                
                if freqs:
                    print(f"    Approximate frequencies: {[f'{f:.1f}Hz' for f in freqs[:4]]}")
        else:
            print("❌ No frequency tables found!")
        
        print()
    
    def analyze_music_engine(self):
        """Analyze the music engine code structure"""
        print("🎮 Music Engine Analysis")
        print("=" * 50)
        
        # Look for common music engine patterns
        prg_data = self.rom_data[16:]
        
        # Pattern 1: Timer loading sequence
        timer_patterns = [
            # LDA timer_low_table,x : STA $4002 : LDA timer_high_table,x : STA $4003
            b'\xBD\x00\x00\x8D\x02\x40\xBD\x00\x00\x8D\x03\x40',
            # Similar for pulse 2
            b'\xBD\x00\x00\x8D\x06\x40\xBD\x00\x00\x8D\x07\x40'
        ]
        
        pattern_found = False
        for pattern in timer_patterns:
            for i in range(len(prg_data) - len(pattern)):
                # Compare with wildcards for table addresses
                match = True
                for j, byte in enumerate(pattern):
                    if byte != 0x00 and prg_data[i+j] != byte:
                        match = False
                        break
                if match:
                    print(f"✅ Found timer loading pattern at 0x{i+16:04X}")
                    pattern_found = True
                    break
        
        if not pattern_found:
            print("❌ No standard timer loading patterns found")
        
        # Pattern 2: Look for JSR to music routines
        jsr_addresses = []
        for i in range(len(prg_data) - 2):
            if prg_data[i] == 0x20:  # JSR instruction
                addr = struct.unpack('<H', prg_data[i+1:i+3])[0]
                if 0x8000 <= addr <= 0xFFFF:  # Valid ROM address
                    jsr_addresses.append(addr)
        
        # Count most frequent JSR targets (likely music routines)
        jsr_counts = {}
        for addr in jsr_addresses:
            jsr_counts[addr] = jsr_counts.get(addr, 0) + 1
        
        if jsr_counts:
            frequent_jsrs = sorted(jsr_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            print("Most frequently called routines:")
            for addr, count in frequent_jsrs:
                print(f"  ${addr:04X}: {count} calls")
        
        print()
    
    def check_apu_initialization(self):
        """Check if APU is being properly initialized"""
        print("🔧 APU Initialization Check")
        print("=" * 50)
        
        prg_data = self.rom_data[16:]
        
        # Look for writes to $4015 (channel enable)
        enable_found = False
        for i in range(len(prg_data) - 2):
            if prg_data[i] == 0x8D and prg_data[i+1] == 0x15 and prg_data[i+2] == 0x40:
                # Found STA $4015
                # Look backwards for the LDA instruction
                for j in range(max(0, i-5), i):
                    if prg_data[j] == 0xA9:  # LDA immediate
                        value = prg_data[j+1]
                        print(f"✅ Found APU enable at 0x{j+16:04X}: LDA #${value:02X} : STA $4015")
                        print(f"   Enabled channels: {self.decode_4015(value)}")
                        enable_found = True
                        break
        
        if not enable_found:
            print("❌ No APU channel enable ($4015) found!")
        
        # Look for duty cycle initialization
        duty_found = False
        for i in range(len(prg_data) - 2):
            if (prg_data[i] == 0x8D and prg_data[i+1] == 0x00 and prg_data[i+2] == 0x40) or \
               (prg_data[i] == 0x8D and prg_data[i+1] == 0x04 and prg_data[i+2] == 0x40):
                # Found STA $4000 or STA $4004 (pulse duty/volume)
                for j in range(max(0, i-5), i):
                    if prg_data[j] == 0xA9:  # LDA immediate
                        value = prg_data[j+1]
                        channel = "1" if prg_data[i+1] == 0x00 else "2"
                        print(f"✅ Found Pulse {channel} setup at 0x{j+16:04X}: LDA #${value:02X} : STA ${prg_data[i+1]:02X}{prg_data[i+2]:02X}")
                        print(f"   Duty: {(value>>6)*25}%, Volume: {value&0x0F}, Envelope: {'Enabled' if (value&0x10)==0 else 'Disabled'}")
                        duty_found = True
                        break
        
        if not duty_found:
            print("❌ No pulse channel duty/volume setup found!")
            
        print()
    
    def decode_4015(self, value):
        """Decode $4015 APU status register value"""
        channels = []
        if value & 0x01: channels.append("Pulse1")
        if value & 0x02: channels.append("Pulse2") 
        if value & 0x04: channels.append("Triangle")
        if value & 0x08: channels.append("Noise")
        if value & 0x10: channels.append("DMC")
        return ", ".join(channels) if channels else "None"
    
    def suggest_fixes(self):
        """Suggest potential fixes for identified issues"""
        print("🔧 Suggested Audio Fixes")
        print("=" * 50)
        
        print("1. APU INITIALIZATION:")
        print("   Add proper APU initialization sequence:")
        print("   ```")
        print("   lda #$0F        ; Enable Pulse1, Pulse2, Triangle, Noise")
        print("   sta $4015")
        print("   lda #$B0        ; 50% duty, constant volume, vol=0")
        print("   sta $4000       ; Pulse 1")
        print("   sta $4004       ; Pulse 2")
        print("   lda #$80        ; Triangle enabled, linear counter disabled")
        print("   sta $4008")
        print("   ```")
        print()
        
        print("2. FREQUENCY TABLES:")
        print("   Use proper NES frequency tables. Example for middle C (261.63 Hz):")
        print("   Timer = CPU_CLOCK / (16 * frequency) - 1")
        print("   Timer = 1789773 / (16 * 261.63) - 1 = 427")
        print("   Low byte: 427 & 0xFF = $AB")
        print("   High byte: (427 >> 8) & 0x07 = $01")
        print()
        
        print("3. PROPER NOTE PLAYBACK:")
        print("   ```")
        print("   play_note:")
        print("       lda note_low_table,x")
        print("       sta $4002           ; Timer low")
        print("       lda note_high_table,x")
        print("       ora #$08            ; Reset length counter")
        print("       sta $4003           ; Timer high + length")
        print("       rts")
        print("   ```")
        print()
        
        print("4. VOLUME CONTROL:")
        print("   Include volume in the duty register:")
        print("   ```")
        print("   lda #$BF        ; 50% duty, constant vol, vol=15 (max)")
        print("   sta $4000")
        print("   ```")
        print()
    
    def run_full_analysis(self):
        """Run complete audio analysis"""
        print("🎵 NES Audio System Debugging")
        print("🔍 ROM:", self.rom_path.name)
        print("=" * 60)
        print()
        
        self.analyze_apu_register_usage()
        self.check_apu_initialization()
        self.analyze_frequency_data()
        self.analyze_music_engine()
        self.suggest_fixes()

def main():
    if len(sys.argv) < 2:
        print("Usage: python audio_debugger.py <rom_file.nes>")
        sys.exit(1)
    
    rom_file = sys.argv[1]
    
    try:
        debugger = NESAudioDebugger(rom_file)
        debugger.run_full_analysis()
    except Exception as e:
        print(f"❌ Error analyzing ROM: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
