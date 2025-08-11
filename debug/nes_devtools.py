#!/usr/bin/env python3
"""
NES Development Tools for MIDI2NES
Comprehensive ROM validation, MMC1 analysis, and debugging utilities
"""

import struct
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class NESDevTools:
    """Comprehensive NES ROM development and debugging tools"""
    
    def __init__(self, rom_path: str):
        self.rom_path = Path(rom_path)
        self.rom_data = self._load_rom()
        self.header = self._parse_header()
    
    def _load_rom(self) -> bytes:
        """Load ROM data"""
        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM not found: {self.rom_path}")
        return self.rom_path.read_bytes()
    
    def _parse_header(self) -> Dict:
        """Parse iNES header"""
        if len(self.rom_data) < 16:
            raise ValueError("ROM too small for iNES header")
        
        header = self.rom_data[:16]
        if header[:4] != b'NES\x1a':
            raise ValueError("Invalid iNES header")
        
        prg_banks = header[4]
        chr_banks = header[5]
        flags6 = header[6]
        flags7 = header[7]
        
        mapper = ((flags7 & 0xF0) | (flags6 >> 4))
        mirroring = "Horizontal" if (flags6 & 1) == 0 else "Vertical"
        battery = bool(flags6 & 2)
        trainer = bool(flags6 & 4)
        four_screen = bool(flags6 & 8)
        
        return {
            'prg_banks': prg_banks,
            'chr_banks': chr_banks,
            'mapper': mapper,
            'mirroring': mirroring,
            'battery': battery,
            'trainer': trainer,
            'four_screen': four_screen,
            'prg_size': prg_banks * 16384,
            'chr_size': chr_banks * 8192,
            'total_expected': 16 + (prg_banks * 16384) + (chr_banks * 8192)
        }
    
    def analyze_mmc1_config(self) -> Dict:
        """Analyze MMC1 mapper configuration from ROM code"""
        if self.header['mapper'] != 1:
            return {'error': f"Not MMC1 (mapper {self.header['mapper']})"}
        
        # Look for MMC1 initialization sequence in PRG ROM
        prg_start = 16
        prg_data = self.rom_data[prg_start:prg_start + self.header['prg_size']]
        
        # Find the MMC1 control register writes
        # Pattern: LDA #value, STA $8000 (A9 XX 8D 00 80)
        mmc1_writes = []
        for i in range(len(prg_data) - 4):
            if (prg_data[i] == 0xA9 and  # LDA immediate
                prg_data[i+2] == 0x8D and  # STA absolute
                prg_data[i+3] == 0x00 and  # $8000 low byte
                prg_data[i+4] == 0x80):    # $8000 high byte
                value = prg_data[i+1]
                mmc1_writes.append((i + prg_start, value))
        
        analysis = {'mmc1_writes': mmc1_writes}
        
        # Analyze MMC1 writes - first is usually reset ($80), second is config
        if mmc1_writes:
            # Use the configuration write (usually second) if available, otherwise first
            config_write = mmc1_writes[1] if len(mmc1_writes) > 1 and mmc1_writes[0][1] == 0x80 else mmc1_writes[0]
            control_value = config_write[1]
            
            analysis.update({
                'reset_value': f"${mmc1_writes[0][1]:02X}" if mmc1_writes[0][1] == 0x80 else None,
                'control_register': f"${control_value:02X}",
                'binary': f"{control_value:05b}",
                'mirroring': ['One-screen A', 'One-screen B', 'Vertical', 'Horizontal'][(control_value & 3)],
                'prg_mode': ['32KB switch', '32KB switch', '16KB fix first', '16KB fix last'][(control_value >> 2) & 3],
                'chr_mode': '4KB' if (control_value & 16) else '8KB',
                'is_32kb_mode': ((control_value >> 2) & 3) < 2,
                'write_sequence': [f"${w[1]:02X}" for w in mmc1_writes[:3]]  # Show first 3 writes
            })
        
        return analysis
    
    def validate_vectors(self) -> Dict:
        """Validate reset vectors"""
        if len(self.rom_data) < 6:
            return {'error': 'ROM too small for vectors'}
        
        # Vectors are at the end of the ROM
        vector_offset = len(self.rom_data) - 6
        vectors = struct.unpack('<HHH', self.rom_data[vector_offset:vector_offset + 6])
        
        return {
            'nmi': f"${vectors[0]:04X}",
            'reset': f"${vectors[1]:04X}",
            'irq': f"${vectors[2]:04X}",
            'offset': f"${vector_offset:04X}",
            'valid_range': all(0x8000 <= v <= 0xFFFF for v in vectors)
        }
    
    def analyze_prg_content(self) -> Dict:
        """Analyze PRG ROM content for common patterns"""
        prg_start = 16
        prg_data = self.rom_data[prg_start:prg_start + self.header['prg_size']]
        
        # Count instruction patterns
        instruction_counts = {}
        apu_writes = 0
        
        for i in range(len(prg_data) - 2):
            # Count STA instructions to APU registers ($4000-$4017)
            if (prg_data[i] == 0x8D and  # STA absolute
                prg_data[i+1] <= 0x17 and
                prg_data[i+2] == 0x40):
                apu_writes += 1
            
            # Count common instructions
            opcode = prg_data[i]
            if opcode in instruction_counts:
                instruction_counts[opcode] += 1
            else:
                instruction_counts[opcode] = 1
        
        # Identify most common instructions
        top_instructions = sorted(instruction_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            'apu_writes': apu_writes,
            'total_bytes': len(prg_data),
            'non_zero_bytes': sum(1 for b in prg_data if b != 0),
            'fill_percentage': (prg_data.count(0xFF) / len(prg_data)) * 100,
            'top_instructions': [(f"${op:02X}", count) for op, count in top_instructions],
            'density': (len([b for b in prg_data if b != 0]) / len(prg_data)) * 100
        }
    
    def check_audio_code(self) -> Dict:
        """Check for audio-related code patterns"""
        prg_start = 16
        prg_data = self.rom_data[prg_start:prg_start + self.header['prg_size']]
        
        # APU register addresses we should see writes to
        apu_registers = {
            0x4000: 'SQ1_VOL',  0x4001: 'SQ1_SWEEP', 0x4002: 'SQ1_LO',   0x4003: 'SQ1_HI',
            0x4004: 'SQ2_VOL',  0x4005: 'SQ2_SWEEP', 0x4006: 'SQ2_LO',   0x4007: 'SQ2_HI',
            0x4008: 'TRI_LINEAR', 0x400A: 'TRI_LO',   0x400B: 'TRI_HI',
            0x400C: 'NOISE_VOL', 0x400E: 'NOISE_LO', 0x400F: 'NOISE_HI',
            0x4015: 'APU_STATUS', 0x4017: 'APU_FRAME'
        }
        
        register_writes = {name: 0 for name in apu_registers.values()}
        
        for i in range(len(prg_data) - 2):
            if prg_data[i] == 0x8D:  # STA absolute
                addr = prg_data[i+1] | (prg_data[i+2] << 8)
                if addr in apu_registers:
                    register_writes[apu_registers[addr]] += 1
        
        # Check for NMI-based timing
        nmi_references = 0
        for i in range(len(prg_data) - 1):
            if prg_data[i] == 0x40:  # RTI instruction (end of NMI)
                nmi_references += 1
        
        return {
            'apu_register_writes': register_writes,
            'total_apu_writes': sum(register_writes.values()),
            'nmi_handlers': nmi_references,
            'has_frame_timing': register_writes['APU_FRAME'] > 0,
            'has_audio_channels': any(register_writes[ch] > 0 for ch in 
                                    ['SQ1_VOL', 'SQ2_VOL', 'TRI_LINEAR', 'NOISE_VOL'])
        }
    
    def generate_report(self) -> str:
        """Generate comprehensive development report"""
        report = []
        report.append("=" * 80)
        report.append("🛠️  NES DEVELOPMENT TOOLS - COMPREHENSIVE ROM ANALYSIS")
        report.append("=" * 80)
        report.append(f"📁 ROM: {self.rom_path}")
        report.append(f"📊 Size: {len(self.rom_data):,} bytes")
        report.append("")
        
        # Header analysis
        report.append("📋 iNES HEADER ANALYSIS")
        report.append("-" * 40)
        header = self.header
        report.append(f"   Mapper: {header['mapper']} {'(MMC1)' if header['mapper'] == 1 else ''}")
        report.append(f"   PRG ROM: {header['prg_banks']} banks ({header['prg_size']:,} bytes)")
        report.append(f"   CHR ROM: {header['chr_banks']} banks ({header['chr_size']:,} bytes)")
        report.append(f"   Mirroring: {header['mirroring']}")
        report.append(f"   Battery: {'Yes' if header['battery'] else 'No'}")
        report.append(f"   Expected size: {header['total_expected']:,} bytes")
        report.append(f"   Actual size: {len(self.rom_data):,} bytes")
        report.append(f"   Size match: {'✅' if len(self.rom_data) == header['total_expected'] else '❌'}")
        report.append("")
        
        # MMC1 analysis
        if header['mapper'] == 1:
            report.append("🔧 MMC1 MAPPER ANALYSIS")
            report.append("-" * 40)
            mmc1 = self.analyze_mmc1_config()
            if 'error' not in mmc1:
                report.append(f"   Control register: {mmc1['control_register']} (binary: {mmc1['binary']})")
                report.append(f"   Mirroring mode: {mmc1['mirroring']}")
                report.append(f"   PRG banking: {mmc1['prg_mode']}")
                report.append(f"   CHR banking: {mmc1['chr_mode']}")
                report.append(f"   32KB PRG mode: {'✅' if mmc1['is_32kb_mode'] else '❌'}")
                report.append(f"   MMC1 writes found: {len(mmc1['mmc1_writes'])}")
            else:
                report.append(f"   ❌ {mmc1['error']}")
            report.append("")
        
        # Vector analysis
        report.append("🎯 RESET VECTORS")
        report.append("-" * 40)
        vectors = self.validate_vectors()
        if 'error' not in vectors:
            report.append(f"   NMI: {vectors['nmi']}")
            report.append(f"   RESET: {vectors['reset']}")
            report.append(f"   IRQ: {vectors['irq']}")
            report.append(f"   Valid range: {'✅' if vectors['valid_range'] else '❌'}")
        else:
            report.append(f"   ❌ {vectors['error']}")
        report.append("")
        
        # Content analysis
        report.append("📊 PRG ROM CONTENT ANALYSIS")
        report.append("-" * 40)
        content = self.analyze_prg_content()
        report.append(f"   Total bytes: {content['total_bytes']:,}")
        report.append(f"   Non-zero bytes: {content['non_zero_bytes']:,}")
        report.append(f"   Code density: {content['density']:.1f}%")
        report.append(f"   Fill bytes (0xFF): {content['fill_percentage']:.1f}%")
        report.append(f"   APU writes: {content['apu_writes']}")
        report.append("")
        
        # Audio analysis
        report.append("🎵 AUDIO CODE ANALYSIS")
        report.append("-" * 40)
        audio = self.check_audio_code()
        report.append(f"   Total APU writes: {audio['total_apu_writes']}")
        report.append(f"   NMI handlers: {audio['nmi_handlers']}")
        report.append(f"   Frame timing: {'✅' if audio['has_frame_timing'] else '❌'}")
        report.append(f"   Audio channels: {'✅' if audio['has_audio_channels'] else '❌'}")
        report.append("   APU Register Usage:")
        for reg, count in audio['apu_register_writes'].items():
            if count > 0:
                report.append(f"     {reg}: {count} writes")
        report.append("")
        
        # Overall health
        health_score = 0
        max_score = 6
        
        if len(self.rom_data) == header['total_expected']:
            health_score += 1
        if header['mapper'] == 1:
            mmc1 = self.analyze_mmc1_config()
            if 'is_32kb_mode' in mmc1 and mmc1['is_32kb_mode']:
                health_score += 1
        if vectors['valid_range']:
            health_score += 1
        if content['apu_writes'] > 0:
            health_score += 1
        if audio['has_audio_channels']:
            health_score += 1
        if audio['nmi_handlers'] > 0:
            health_score += 1
            
        health_status = "🟢 EXCELLENT" if health_score >= 5 else "🟡 GOOD" if health_score >= 3 else "🔴 NEEDS WORK"
        
        report.append("🏥 OVERALL ROM HEALTH")
        report.append("-" * 40)
        report.append(f"   Health Score: {health_score}/{max_score}")
        report.append(f"   Status: {health_status}")
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)

def main():
    """Command-line interface"""
    if len(sys.argv) != 2:
        print("Usage: python nes_devtools.py <rom_file>")
        sys.exit(1)
    
    try:
        tools = NESDevTools(sys.argv[1])
        print(tools.generate_report())
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
