#!/usr/bin/env python3
"""
Comprehensive ROM generation test suite and validation utilities for MIDI2NES.
Tests the complete pipeline and validates NES ROMs for corruption.
"""

import subprocess
import tempfile
import json
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from main import (
    run_parse, run_map, run_frames, run_export, run_prepare,
    run_full_pipeline, compile_rom
)
from nes.project_builder import NESProjectBuilder


class ROMValidator:
    """Validates NES ROM files for corruption and correctness."""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.errors = []
    
    def validate_ines_header(self, rom_path: Path) -> bool:
        """Validate iNES header format."""
        try:
            with open(rom_path, 'rb') as f:
                header = f.read(16)
            
            if len(header) != 16:
                self.errors.append(f"Header too short: {len(header)} bytes")
                return False
            
            # Check iNES signature
            if header[:4] != b'NES\x1a':
                self.errors.append(f"Invalid iNES signature: {header[:4]}")
                return False
            
            # Check PRG ROM size (should be > 0)
            prg_size = header[4]
            if prg_size == 0:
                self.errors.append("PRG ROM size is 0")
                return False
            
            # Check CHR ROM size (can be 0)
            chr_size = header[5]
            
            # Check mapper and mirroring bits
            mapper_lo = (header[6] & 0xF0) >> 4
            mapper_hi = (header[7] & 0xF0) >> 4
            mapper = mapper_hi << 4 | mapper_lo
            
            mirroring = header[6] & 1
            
            print(f"  iNES Header: PRG={prg_size}x16KB, CHR={chr_size}x8KB, Mapper={mapper}, Mirror={mirroring}")
            
            return True
            
        except Exception as e:
            self.errors.append(f"Header validation error: {str(e)}")
            return False
    
    def validate_rom_size(self, rom_path: Path) -> bool:
        """Validate ROM file size matches header."""
        try:
            with open(rom_path, 'rb') as f:
                header = f.read(16)
                prg_size = header[4]  # 16KB units
                chr_size = header[5]  # 8KB units
            
            expected_size = 16 + (prg_size * 16384) + (chr_size * 8192)
            actual_size = rom_path.stat().st_size
            
            if actual_size != expected_size:
                self.errors.append(f"Size mismatch: expected {expected_size}, got {actual_size}")
                return False
            
            print(f"  ROM Size: {actual_size:,} bytes (correct)")
            return True
            
        except Exception as e:
            self.errors.append(f"Size validation error: {str(e)}")
            return False
    
    def validate_code_section(self, rom_path: Path) -> bool:
        """Basic validation of 6502 code section."""
        try:
            with open(rom_path, 'rb') as f:
                data = f.read()
            
            # Get mapper info from header
            header = data[:16]
            mapper_lo = (header[6] & 0xF0) >> 4
            mapper_hi = (header[7] & 0xF0) >> 4
            mapper = mapper_hi << 4 | mapper_lo
            
            # For NES ROMs, vectors are at the very end of the file
            if len(data) >= 6:
                # Read NES vectors from the last 6 bytes
                nmi_vector = int.from_bytes(data[-6:-4], byteorder='little')
                reset_vector_addr = int.from_bytes(data[-4:-2], byteorder='little')
                irq_vector = int.from_bytes(data[-2:], byteorder='little')
                
                # MMC1 and other mappers can have vectors anywhere in the valid 6502 address space
                # but they should be non-zero for a functional ROM
                if reset_vector_addr == 0:
                    self.errors.append("Reset vector is 0 (ROM may not boot)")
                    return False
                
                # For MMC1 (mapper 1), vectors are typically in the 0x2000-0xBFFF range
                # For NROM (mapper 0), vectors should be in 0x8000-0xFFFF range
                if mapper == 0:  # NROM
                    if reset_vector_addr < 0x8000:
                        self.errors.append(f"NROM reset vector too low: 0x{reset_vector_addr:04X} (should be >= 0x8000)")
                        return False
                else:  # MMC1 and other mappers
                    if reset_vector_addr > 0xFFFF:
                        self.errors.append(f"Invalid reset vector: 0x{reset_vector_addr:04X} (exceeds 6502 address space)")
                        return False
                
                print(f"  Reset Vector: 0x{reset_vector_addr:04X} (Mapper {mapper})")
                print(f"  NMI Vector: 0x{nmi_vector:04X}, IRQ Vector: 0x{irq_vector:04X}")
            else:
                self.errors.append("ROM too small to contain vectors")
                return False
            
            return True
            
        except Exception as e:
            self.errors.append(f"Code validation error: {str(e)}")
            return False
    
    def test_rom(self, rom_path: Path, test_name: str) -> bool:
        """Run full ROM validation."""
        print(f"\n🔍 Testing ROM: {test_name}")
        print(f"   File: {rom_path}")
        
        success = True
        
        if not self.validate_ines_header(rom_path):
            success = False
        
        if not self.validate_rom_size(rom_path):
            success = False
        
        if not self.validate_code_section(rom_path):
            success = False
        
        if success:
            print(f"  ✅ {test_name}: ROM validation passed")
            self.tests_passed += 1
        else:
            print(f"  ❌ {test_name}: ROM validation failed")
            for error in self.errors:
                print(f"     - {error}")
            self.tests_failed += 1
            self.errors.clear()
        
        return success


class PipelineTestSuite:
    """Test suite for the complete MIDI2NES pipeline."""
    
    def __init__(self):
        self.validator = ROMValidator()
        self.temp_dir = None
    
    def setup_temp_dir(self):
        """Create temporary directory for test files."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="midi2nes_test_"))
        print(f"📁 Test directory: {self.temp_dir}")
        return self.temp_dir
    
    def cleanup_temp_dir(self):
        """Clean up temporary directory."""
        if self.temp_dir and self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def find_test_midi_files(self) -> list:
        """Find MIDI files for testing."""
        project_root = Path(__file__).parent.parent
        midi_files = []
        
        # Look for test MIDI files
        test_files = [
            "test_simple.mid",
            "test_midi/simple_loop.mid", 
            "test_midi/complex_patterns.mid",
            "test_midi/multiple_tracks.mid",
            "test_midi/short_loops.mid"
        ]
        
        for test_file in test_files:
            file_path = project_root / test_file
            if file_path.exists():
                midi_files.append(file_path)
        
        return midi_files
    
    def test_individual_stages(self, midi_file: Path) -> bool:
        """Test individual pipeline stages."""
        print(f"\n🔧 Testing individual stages with: {midi_file.name}")
        
        try:
            # Create temporary namespace for arguments
            class Args:
                def __init__(self, **kwargs):
                    for key, value in kwargs.items():
                        setattr(self, key, value)
            
            # Stage 1: Parse
            parsed_file = self.temp_dir / f"{midi_file.stem}_parsed.json"
            args = Args(input=str(midi_file), output=str(parsed_file))
            run_parse(args)
            
            if not parsed_file.exists():
                print("  ❌ Parse stage failed - no output file")
                return False
            print("  ✅ Parse stage completed")
            
            # Stage 2: Map
            mapped_file = self.temp_dir / f"{midi_file.stem}_mapped.json"
            args = Args(input=str(parsed_file), output=str(mapped_file))
            run_map(args)
            
            if not mapped_file.exists():
                print("  ❌ Map stage failed - no output file")
                return False
            print("  ✅ Map stage completed")
            
            # Stage 3: Frames
            frames_file = self.temp_dir / f"{midi_file.stem}_frames.json"
            args = Args(input=str(mapped_file), output=str(frames_file))
            run_frames(args)
            
            if not frames_file.exists():
                print("  ❌ Frames stage failed - no output file")
                return False
            print("  ✅ Frames stage completed")
            
            # Stage 4: Export
            music_asm_file = self.temp_dir / f"{midi_file.stem}_music.s"
            args = Args(input=str(frames_file), output=str(music_asm_file), 
                       format='ca65', patterns=None)
            run_export(args)
            
            if not music_asm_file.exists():
                print("  ❌ Export stage failed - no output file")
                return False
            print("  ✅ Export stage completed")
            
            # Stage 5: Prepare project
            project_dir = self.temp_dir / f"{midi_file.stem}_project"
            args = Args(input=str(music_asm_file), output=str(project_dir))
            run_prepare(args)
            
            if not project_dir.exists():
                print("  ❌ Prepare stage failed - no project directory")
                return False
            print("  ✅ Prepare stage completed")
            
            # Stage 6: Compile ROM
            rom_file = self.temp_dir / f"{midi_file.stem}.nes"
            success = compile_rom(project_dir, rom_file)
            
            if not success or not rom_file.exists():
                print("  ❌ Compile stage failed - no ROM file")
                return False
            print("  ✅ Compile stage completed")
            
            # Validate the ROM
            return self.validator.test_rom(rom_file, f"{midi_file.stem} (individual stages)")
            
        except Exception as e:
            print(f"  ❌ Pipeline error: {str(e)}")
            return False
    
    def test_full_pipeline(self, midi_file: Path) -> bool:
        """Test the complete integrated pipeline."""
        print(f"\n⚡ Testing full pipeline with: {midi_file.name}")
        
        try:
            # Create temporary namespace for arguments
            class Args:
                def __init__(self, **kwargs):
                    for key, value in kwargs.items():
                        setattr(self, key, value)
            
            rom_file = self.temp_dir / f"{midi_file.stem}_full.nes"
            args = Args(input=str(midi_file), output=str(rom_file), verbose=False)
            
            # Run the full pipeline
            run_full_pipeline(args)
            
            if not rom_file.exists():
                print("  ❌ Full pipeline failed - no ROM file")
                return False
            
            # Validate the ROM
            return self.validator.test_rom(rom_file, f"{midi_file.stem} (full pipeline)")
            
        except Exception as e:
            print(f"  ❌ Full pipeline error: {str(e)}")
            return False
    
    def run_all_tests(self) -> bool:
        """Run the complete test suite."""
        print("🎵 MIDI2NES ROM Generation Test Suite")
        print("=" * 60)
        
        self.setup_temp_dir()
        
        try:
            # Find test MIDI files
            midi_files = self.find_test_midi_files()
            
            if not midi_files:
                print("❌ No test MIDI files found!")
                return False
            
            print(f"📂 Found {len(midi_files)} test MIDI files")
            
            all_tests_passed = True
            
            # Test each MIDI file
            for midi_file in midi_files:
                # Test individual stages
                if not self.test_individual_stages(midi_file):
                    all_tests_passed = False
                
                # Test full integrated pipeline  
                if not self.test_full_pipeline(midi_file):
                    all_tests_passed = False
            
            # Print summary
            print("\n" + "=" * 60)
            print("🏁 Test Summary:")
            print(f"   ✅ Passed: {self.validator.tests_passed}")
            print(f"   ❌ Failed: {self.validator.tests_failed}")
            if (self.validator.tests_passed + self.validator.tests_failed) > 0:
                print(f"   📊 Success Rate: {(self.validator.tests_passed / (self.validator.tests_passed + self.validator.tests_failed) * 100):.1f}%")
            
            if all_tests_passed:
                print("\n🎉 All tests passed! ROMs are generating correctly.")
                return True
            else:
                print("\n⚠️  Some tests failed. Please check the error messages above.")
                return False
        
        finally:
            self.cleanup_temp_dir()


def test_rom_generation():
    """Run the complete ROM generation test suite."""
    # Check if CA65 tools are available
    try:
        subprocess.run(['ca65', '--version'], capture_output=True, check=True)
        subprocess.run(['ld65', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ CA65/LD65 tools not found. Please install cc65 toolchain.")
        print("   Visit: https://cc65.github.io/")
        return False
    
    # Run the test suite
    test_suite = PipelineTestSuite()
    return test_suite.run_all_tests()


def main():
    """CLI entry point for ROM testing."""
    success = test_rom_generation()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
