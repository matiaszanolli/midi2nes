#!/bin/bash

echo "Building fixed NES ROM..."

# Check if CA65 is available
if ! command -v ca65 &> /dev/null; then
    echo "Error: CA65 assembler not found. Please install cc65 tools."
    exit 1
fi

# Check if LD65 is available
if ! command -v ld65 &> /dev/null; then
    echo "Error: LD65 linker not found. Please install cc65 tools."
    exit 1
fi

# Assemble the ROM
echo "  Assembling enhanced_midi.s..."
ca65 enhanced_midi.s -o enhanced_midi.o

if [ $? -ne 0 ]; then
    echo "Error: Assembly failed!"
    exit 1
fi

# Link the ROM
echo "  Linking ROM..."
ld65 -C enhanced_nes.cfg enhanced_midi.o -o fixed_input.nes

if [ $? -ne 0 ]; then
    echo "Error: Linking failed!"
    exit 1
fi

# Clean up object files
rm -f enhanced_midi.o

echo "SUCCESS: Fixed ROM created as fixed_input.nes"
echo ""
echo "The ROM now has:"
echo "  - Proper reset vector pointing to working initialization code"
echo "  - Valid NMI and IRQ handlers"  
echo "  - MMC1 mapper configuration"
echo "  - Proper memory layout"
echo ""
echo "You can test this ROM in your favorite NES emulator."
