#!/usr/bin/env python3
"""CLI runner for MIDI2NES performance benchmarks."""

import sys
import argparse
from pathlib import Path
import json
from typing import List

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from benchmarks.performance_suite import PerformanceBenchmark
from utils.profiling import log_memory_usage


def find_test_files(directory: str, pattern: str = "*.mid") -> List[str]:
    """
    Find MIDI test files in a directory.
    
    Args:
        directory: Directory to search
        pattern: File pattern to match
        
    Returns:
        List of matching file paths
    """
    search_dir = Path(directory)
    if not search_dir.exists():
        print(f"Warning: Directory {directory} does not exist")
        return []
    
    files = list(search_dir.glob(pattern))
    return [str(f) for f in files if f.is_file()]


def create_synthetic_midi(output_path: str) -> bool:
    """
    Create a simple synthetic MIDI file for testing.
    
    Args:
        output_path: Path to save the synthetic MIDI file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # This would require a MIDI library like mido
        # For now, just create a placeholder
        print(f"Note: Synthetic MIDI generation not implemented yet")
        print(f"      Add real MIDI files to test with instead")
        return False
    except Exception as e:
        print(f"Failed to create synthetic MIDI: {e}")
        return False


def run_baseline_benchmark():
    """Run a baseline benchmark to establish system performance characteristics."""
    print("=== MIDI2NES Baseline Performance Benchmark ===")
    
    # Check system resources
    log_memory_usage("System baseline")
    
    # Create benchmark instance
    benchmark = PerformanceBenchmark(output_dir="benchmark_results")
    
    # Look for test files
    test_dirs = ["test_data", "examples", "samples", "."]
    test_files = []
    
    for test_dir in test_dirs:
        found_files = find_test_files(test_dir, "*.mid")
        test_files.extend(found_files)
        if found_files:
            print(f"Found {len(found_files)} MIDI files in {test_dir}/")
    
    if not test_files:
        print("\nNo MIDI test files found. Trying common locations:")
        for test_dir in test_dirs:
            print(f"  - {test_dir}/*.mid")
        
        # Try to create a synthetic file for basic testing
        print("\nAttempting to create synthetic test file...")
        if create_synthetic_midi("test_synthetic.mid"):
            test_files = ["test_synthetic.mid"]
        else:
            print("Cannot run benchmarks without test files.")
            print("\nTo run benchmarks:")
            print("1. Add MIDI files to test_data/ directory")
            print("2. Or specify files with --files option")
            return
    
    # Limit number of test files for initial run
    if len(test_files) > 5:
        print(f"Limiting benchmark to first 5 files (found {len(test_files)} total)")
        test_files = test_files[:5]
    
    print(f"\nRunning benchmarks on {len(test_files)} files:")
    for i, file in enumerate(test_files, 1):
        print(f"  {i}. {file}")
    
    print("\nStarting benchmark run...")
    log_memory_usage("Pre-benchmark")
    
    # Run benchmarks
    results = benchmark.run_batch_benchmarks(test_files)
    
    log_memory_usage("Post-benchmark")
    
    # Generate report
    report_path = "benchmark_results/performance_report.json"
    report = benchmark.generate_report(report_path)
    
    # Print additional analysis
    if results:
        print(f"\n=== DETAILED ANALYSIS ===")
        
        # Find bottlenecks
        stage_totals = {}
        for result in results:
            for stage in result.stages:
                if stage.stage not in stage_totals:
                    stage_totals[stage.stage] = []
                stage_totals[stage.stage].append(stage.duration_ms)
        
        print("\nStage bottleneck analysis:")
        for stage, durations in sorted(stage_totals.items(), 
                                      key=lambda x: sum(x[1]), reverse=True):
            avg_duration = sum(durations) / len(durations)
            total_duration = sum(durations)
            print(f"  {stage:20} Total: {total_duration:8.1f}ms  "
                  f"Avg: {avg_duration:6.1f}ms  "
                  f"Runs: {len(durations)}")
        
        # Memory analysis
        max_memory = max(r.total_memory_mb for r in results)
        avg_memory = sum(r.total_memory_mb for r in results) / len(results)
        
        print(f"\nMemory usage analysis:")
        print(f"  Peak memory usage: {max_memory:.1f}MB")
        print(f"  Average memory usage: {avg_memory:.1f}MB")
        
        # Performance recommendations
        print(f"\n=== PERFORMANCE RECOMMENDATIONS ===")
        
        # Check for slow stages
        if 'pattern_detection' in stage_totals:
            pattern_avg = sum(stage_totals['pattern_detection']) / len(stage_totals['pattern_detection'])
            if pattern_avg > 1000:  # > 1 second
                print("⚠ Pattern detection is slow - consider optimization")
        
        # Check memory usage
        if max_memory > 256:  # > 256MB
            print("⚠ High memory usage detected - consider memory optimization")
        
        # Check export performance
        if 'export' in stage_totals:
            export_avg = sum(stage_totals['export']) / len(stage_totals['export'])
            if export_avg > 500:  # > 500ms
                print("⚠ Export stage is slow - consider output optimization")
        
        print(f"\nBenchmark completed successfully!")
        print(f"Results saved to: {report_path}")
    
    else:
        print("No successful benchmark results to analyze.")


def run_custom_benchmark(files: List[str], output_dir: str = "benchmark_results"):
    """
    Run benchmark on custom set of files.
    
    Args:
        files: List of MIDI files to benchmark
        output_dir: Directory to save results
    """
    print(f"=== Custom MIDI2NES Benchmark ===")
    print(f"Files to benchmark: {len(files)}")
    
    # Verify files exist
    valid_files = []
    for file in files:
        if Path(file).exists():
            valid_files.append(file)
            print(f"  ✓ {file}")
        else:
            print(f"  ✗ {file} (not found)")
    
    if not valid_files:
        print("No valid files to benchmark")
        return
    
    # Run benchmark
    benchmark = PerformanceBenchmark(output_dir=output_dir)
    log_memory_usage("Pre-benchmark")
    
    results = benchmark.run_batch_benchmarks(valid_files)
    
    log_memory_usage("Post-benchmark")
    
    # Generate report
    report_path = f"{output_dir}/custom_benchmark_report.json"
    benchmark.generate_report(report_path)
    
    print(f"\nCustom benchmark completed!")
    print(f"Results saved to: {report_path}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MIDI2NES Performance Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_benchmarks.py                    # Run baseline benchmark
  python run_benchmarks.py --files song1.mid song2.mid  # Benchmark specific files  
  python run_benchmarks.py --directory test_data/       # Benchmark directory
  python run_benchmarks.py --output results/           # Custom output directory
        """
    )
    
    parser.add_argument(
        "--files", 
        nargs="+", 
        help="Specific MIDI files to benchmark"
    )
    
    parser.add_argument(
        "--directory", 
        help="Directory containing MIDI files to benchmark"
    )
    
    parser.add_argument(
        "--output", 
        default="benchmark_results",
        help="Output directory for results (default: benchmark_results)"
    )
    
    parser.add_argument(
        "--pattern",
        default="*.mid",
        help="File pattern to match (default: *.mid)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to benchmark"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Determine which files to benchmark
    files_to_benchmark = []
    
    if args.files:
        files_to_benchmark = args.files
    elif args.directory:
        files_to_benchmark = find_test_files(args.directory, args.pattern)
    else:
        # Run baseline benchmark
        run_baseline_benchmark()
        return
    
    # Apply limit if specified
    if args.limit and len(files_to_benchmark) > args.limit:
        print(f"Limiting benchmark to {args.limit} files (found {len(files_to_benchmark)})")
        files_to_benchmark = files_to_benchmark[:args.limit]
    
    # Run custom benchmark
    if files_to_benchmark:
        run_custom_benchmark(files_to_benchmark, args.output)
    else:
        print("No files found to benchmark")


if __name__ == "__main__":
    main()
