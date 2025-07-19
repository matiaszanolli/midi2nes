import os
import subprocess
import sys
import json
from pathlib import Path

def create_batch_test_script():
    script_content = '''#!/usr/bin/env python3
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
    print(f"\\n[RUNNING] {description}")
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
        print(f"\\n[PROCESSING] {test_file}")
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
    print("\\n" + "=" * 50)
    print("BATCH PROCESSING SUMMARY")
    print("=" * 50)
    
    for base_name, result in results.items():
        print(f"\\n[FILE] {base_name}:")
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
    
    print(f"\\n[SUMMARY] Successfully processed: {successful_files}/{len(results)} files")
    
    if successful_files == len(results):
        print("[SUCCESS] All test files processed successfully!")
    else:
        print("[WARNING] Some files had processing errors. Check the logs above.")
        
    print("\\n[OUTPUT] Output files located in:")
    print("   - JSON data: output/json/")
    print("   - Pattern data: output/patterns/")
    print("   - NES assembly: output/nes/")

if __name__ == "__main__":
    main()
'''
    
    # Write with explicit UTF-8 encoding to avoid CP1252 issues
    with open('batch_test.py', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print("Created batch_test.py!")

def create_analysis_script():
    """Create a script to analyze the pattern detection results in detail."""
    analysis_script = '''#!/usr/bin/env python3
"""
Analysis script for pattern detection results
Provides detailed analysis of how well the LoopManager performed
"""

import json
import os
from pathlib import Path

def analyze_pattern_file(pattern_file):
    """Analyze a single pattern detection result file."""
    if not os.path.exists(pattern_file):
        return None
    
    with open(pattern_file, 'r') as f:
        data = json.load(f)
    
    analysis = {
        'file': os.path.basename(pattern_file),
        'patterns_found': 0,
        'total_usage': 0,
        'compression_ratio': 0,
        'pattern_details': []
    }
    
    if 'patterns' in data:
        patterns = data['patterns']
        analysis['patterns_found'] = len(patterns)
        
        for i, pattern in enumerate(patterns):
            usage_count = pattern.get('usage_count', 0)
            pattern_length = len(pattern.get('data', []))
            
            analysis['total_usage'] += usage_count
            analysis['pattern_details'].append({
                'id': i,
                'length': pattern_length,
                'usage_count': usage_count,
                'savings': (usage_count - 1) * pattern_length if usage_count > 1 else 0
            })
    
    # Calculate compression ratio (simplified)
    total_savings = sum(p['savings'] for p in analysis['pattern_details'])
    if 'original_length' in data:
        original_length = data['original_length']
        analysis['compression_ratio'] = (total_savings / original_length) * 100 if original_length > 0 else 0
    
    return analysis

def main():
    print("Pattern Detection Analysis")
    print("=" * 50)
    
    pattern_files = list(Path("output/patterns").glob("*.json"))
    
    if not pattern_files:
        print("[ERROR] No pattern files found in output/patterns/")
        return
    
    all_analyses = []
    
    for pattern_file in sorted(pattern_files):
        analysis = analyze_pattern_file(pattern_file)
        if analysis:
            all_analyses.append(analysis)
    
    # Print detailed analysis
    for analysis in all_analyses:
        print(f"\\n[FILE] {analysis['file']}")
        print("-" * 30)
        print(f"   Patterns found: {analysis['patterns_found']}")
        print(f"   Total usage: {analysis['total_usage']}")
        if analysis['compression_ratio'] > 0:
            print(f"   Compression ratio: {analysis['compression_ratio']:.1f}%")
        
        if analysis['pattern_details']:
            print("   Pattern details:")
            for detail in analysis['pattern_details']:
                print(f"     Pattern {detail['id']}: {detail['length']} frames, used {detail['usage_count']} times")
                if detail['savings'] > 0:
                    print(f"       -> Saves {detail['savings']} frames")
    
    # Summary statistics
    total_patterns = sum(a['patterns_found'] for a in all_analyses)
    avg_patterns = total_patterns / len(all_analyses) if all_analyses else 0
    
    print(f"\\n[SUMMARY]")
    print("-" * 20)
    print(f"Files analyzed: {len(all_analyses)}")
    print(f"Total patterns detected: {total_patterns}")
    print(f"Average patterns per file: {avg_patterns:.1f}")
    
    # Best and worst performers
    if all_analyses:
        best = max(all_analyses, key=lambda x: x['patterns_found'])
        worst = min(all_analyses, key=lambda x: x['patterns_found'])
        
        print(f"\\n[BEST] Best pattern detection: {best['file']} ({best['patterns_found']} patterns)")
        print(f"[NEEDS WORK] Needs improvement: {worst['file']} ({worst['patterns_found']} patterns)")

if __name__ == "__main__":
    main()
'''
    
    # Write with explicit UTF-8 encoding
    with open('analyze_patterns.py', 'w', encoding='utf-8') as f:
        f.write(analysis_script)
    
    print("Created analyze_patterns.py!")

if __name__ == "__main__":
    create_batch_test_script()
    create_analysis_script()
    print("\nReady to test! Run the following commands:")
    print("1. python batch_test.py       # Process all test files")
    print("2. python analyze_patterns.py # Analyze pattern detection results")
