#!/usr/bin/env python3
"""
Analysis utilities for pattern detection results.
Provides detailed analysis of how well the LoopManager performed.
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


def analyze_patterns(pattern_dir="output/patterns"):
    """Analyze all pattern files in the specified directory."""
    print("Pattern Detection Analysis")
    print("=" * 50)
    
    pattern_files = list(Path(pattern_dir).glob("*.json"))
    
    if not pattern_files:
        print(f"[ERROR] No pattern files found in {pattern_dir}/")
        return
    
    all_analyses = []
    
    for pattern_file in sorted(pattern_files):
        analysis = analyze_pattern_file(pattern_file)
        if analysis:
            all_analyses.append(analysis)
    
    # Print detailed analysis
    for analysis in all_analyses:
        print(f"\n[FILE] {analysis['file']}")
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
    
    print(f"\n[SUMMARY]")
    print("-" * 20)
    print(f"Files analyzed: {len(all_analyses)}")
    print(f"Total patterns detected: {total_patterns}")
    print(f"Average patterns per file: {avg_patterns:.1f}")
    
    # Best and worst performers
    if all_analyses:
        best = max(all_analyses, key=lambda x: x['patterns_found'])
        worst = min(all_analyses, key=lambda x: x['patterns_found'])
        
        print(f"\n[BEST] Best pattern detection: {best['file']} ({best['patterns_found']} patterns)")
        print(f"[NEEDS WORK] Needs improvement: {worst['file']} ({worst['patterns_found']} patterns)")
    
    return all_analyses


def main():
    """CLI entry point for pattern analysis."""
    analyze_patterns()


if __name__ == "__main__":
    main()
