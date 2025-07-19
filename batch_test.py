#!/usr/bin/env python3
"""
Batch test script for MIDI to NES conversion pipeline
Processes all test MIDI files through the complete conversion process
"""

import os
import subprocess
import sys
import json
import time
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors gracefully."""
    print(f"\n[RUNNING] {description}")
    print(f"   Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            print(f"   [SUCCESS] {result.stdout.strip()}")
        else:
            print(f"   [SUCCESS] Command completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   [ERROR] {e}")
        if e.stdout:
            print(f"   stdout: {e.stdout}")
        if e.stderr:
            print(f"   stderr: {e.stderr}")
        return False

def ensure_directory(path):
    """Create directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)

def analyze_patterns_file(patterns_file):
    """Analyze the patterns detection results."""
    if not os.path.exists(patterns_file):
        return "[ERROR] Patterns file not found"
    
    try:
        with open(patterns_file, 'r') as f:
            data = json.load(f)
        
        if 'patterns' in data:
            pattern_count = len(data['patterns'])
            total_usage = sum(pattern.get('usage_count', 0) for pattern in data['patterns'])
            return f"[SUCCESS] Found {pattern_count} patterns, total usage: {total_usage}"
        else:
            return "[WARNING] No patterns detected"
    except Exception as e:
        return f"[ERROR] Error reading patterns: {e}"

def main():
    print("MIDI2NES Batch Test Pipeline")
    print("=" * 50)
    
    # Test files to process
    test_files = [
        "simple_loop.mid",
        "tempo_changes.mid", 
        "multiple_tracks.mid",
        "complex_patterns.mid",
        "short_loops.mid",
        "long_composition.mid"
    ]
    
    # Create output directories
    output_dirs = [
        "output/json",
        "output/patterns", 
        "output/nes",
        "output/logs"
    ]
    
    for directory in output_dirs:
        ensure_directory(directory)
    
    results = {}
    
    for test_file in test_files:
        base_name = test_file.replace('.mid', '')
        print(f"\n[PROCESSING] {test_file}")
        print("-" * 40)
        
        # File paths
        midi_path = f"test_midi/{test_file}"
        parsed_json = f"output/json/{base_name}_parsed.json"
        mapped_json = f"output/json/{base_name}_mapped.json"
        frames_json = f"output/json/{base_name}_frames.json"
        patterns_json = f"output/patterns/{base_name}_patterns.json"
        output_asm = f"output/nes/{base_name}.asm"
        
        # Check if input file exists
        if not os.path.exists(midi_path):
            print(f"[ERROR] Input file {midi_path} not found, skipping...")
            continue
        
        results[base_name] = {}
        start_time = time.time()
        
        # Step 1: Parse MIDI
        step1_success = run_command([
            sys.executable, "-m", "main", "parse", 
            midi_path, parsed_json
        ], f"Step 1: Parsing {test_file}")
        results[base_name]['parse'] = step1_success
        
        if not step1_success:
            continue
            
        # Step 2: Map tracks
        step2_success = run_command([
            sys.executable, "-m", "main", "map",
            parsed_json, mapped_json
        ], f"Step 2: Mapping tracks for {base_name}")
        results[base_name]['map'] = step2_success
        
        if not step2_success:
            continue
            
        # Step 3: Generate frames
        step3_success = run_command([
            sys.executable, "-m", "main", "frames",
            mapped_json, frames_json
        ], f"Step 3: Generating frames for {base_name}")
        results[base_name]['frames'] = step3_success
        
        if not step3_success:
            continue
            
        # Step 4: Detect patterns (LoopManager in action!)
        step4_success = run_command([
            sys.executable, "-m", "main", "detect-patterns",
            frames_json, patterns_json
        ], f"Step 4: Detecting patterns for {base_name}")
        results[base_name]['patterns'] = step4_success
        
        # Analyze pattern detection results
        pattern_analysis = analyze_patterns_file(patterns_json)
        print(f"   [ANALYSIS] Pattern Analysis: {pattern_analysis}")
        results[base_name]['pattern_analysis'] = pattern_analysis
        
        # Step 5: Export to NES format
        export_cmd = [
            sys.executable, "-m", "main", "export",
            frames_json, output_asm, "--format", "ca65"
        ]
        if step4_success and os.path.exists(patterns_json):
            export_cmd.extend(["--patterns", patterns_json])
            
        step5_success = run_command(export_cmd, f"Step 5: Exporting {base_name} to NES")
        results[base_name]['export'] = step5_success
        
        # Calculate processing time
        processing_time = time.time() - start_time
        results[base_name]['time'] = processing_time
        print(f"   [TIMING] Total processing time: {processing_time:.2f} seconds")
    
    # Print summary
    print("\n" + "=" * 50)
    print("BATCH PROCESSING SUMMARY")
    print("=" * 50)
    
    for base_name, result in results.items():
        print(f"\n[FILE] {base_name}:")
        steps = ['parse', 'map', 'frames', 'patterns', 'export']
        for step in steps:
            if step in result:
                status = "[OK]" if result[step] else "[FAIL]"
                print(f"   {step.capitalize():12s}: {status}")
        
        if 'pattern_analysis' in result:
            print(f"   {'Patterns':<12s}: {result['pattern_analysis']}")
        
        if 'time' in result:
            print(f"   {'Time':<12s}: {result['time']:.2f}s")
    
    # Check if all files were processed successfully
    successful_files = sum(1 for result in results.values() 
                         if all(result.get(step, False) for step in ['parse', 'map', 'frames', 'patterns', 'export']))
    
    print(f"\n[SUMMARY] Successfully processed: {successful_files}/{len(results)} files")
    
    if successful_files == len(results):
        print("[SUCCESS] All test files processed successfully!")
    else:
        print("[WARNING] Some files had processing errors. Check the logs above.")
        
    print("\n[OUTPUT] Output files located in:")
    print("   - JSON data: output/json/")
    print("   - Pattern data: output/patterns/")
    print("   - NES assembly: output/nes/")

if __name__ == "__main__":
    main()
