#!/usr/bin/env python3
"""CLI runner for MIDI2NES performance benchmarks."""

import sys
import json
import argparse
from pathlib import Path
from typing import List

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from benchmarks.performance_suite import (
    PerformanceBenchmark,
    compare_to_baseline,
    load_baseline,
    DEFAULT_BASELINE_REGRESSION_MARGIN,
)
from utils.profiling import log_memory_usage

# Deterministic fixture set (#373/PERF-A-03): the old test_dirs glob over
# test_data/examples/samples/. benchmarked whatever happened to be present
# on the machine running it, so results were not comparable across
# runs/machines -- undermining any baseline gate (#372/PERF-A-02) built on
# top of it. These few small, committed .mid files are the sole default
# source now, independent of the working tree.
FIXTURES_DIR = Path(__file__).parent / "fixtures"
BASELINE_PATH = Path(__file__).parent / "baseline.json"


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

    # Sorted so results are deterministic across runs/platforms (#117) —
    # Path.glob's traversal order is filesystem-dependent otherwise.
    files = sorted(search_dir.glob(pattern))
    return [str(f) for f in files if f.is_file()]


def run_baseline_benchmark(
    check_baseline: bool = True,
    update_baseline: bool = False,
    margin: float = DEFAULT_BASELINE_REGRESSION_MARGIN,
) -> bool:
    """Run the baseline benchmark against the deterministic fixture set.

    Returns True if the run completed with no detected regression (or
    `check_baseline` is False / `update_baseline` is True), False if a
    stage regressed past `margin` versus the checked-in baseline — the
    caller should exit non-zero on False so a regression actually fails a
    CI/local run instead of only printing a warning (#372/PERF-A-02).
    """
    print("=== MIDI2NES Baseline Performance Benchmark ===")

    # Check system resources
    log_memory_usage("System baseline")

    # Create benchmark instance
    benchmark = PerformanceBenchmark(output_dir="benchmark_results")

    test_files = find_test_files(str(FIXTURES_DIR), "*.mid")
    if not test_files:
        print(f"\nNo fixture MIDI files found in {FIXTURES_DIR}/ — "
              "benchmarks/fixtures/ should ship with the repo (#373/PERF-A-03).")
        print("To run against a different set instead, use --files or --directory.")
        return False

    print(f"\nRunning benchmarks on {len(test_files)} fixture files:")
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

    regression_free = True

    # Baseline comparison (#372/PERF-A-02): the report alone greenlit a
    # silent 2x slowdown -- compare this run's per-stage median against the
    # checked-in baseline and fail loudly if a stage regressed. `report` is
    # None only when every file in the batch failed (generate_report's own
    # early-return guard) -- nothing to compare in that case either.
    if report is None:
        print("\nNo benchmark results to compare against the baseline.")
        regression_free = False
    elif update_baseline:
        BASELINE_PATH.write_text(json.dumps(report['summary_statistics'], indent=2) + "\n")
        print(f"\nBaseline updated: {BASELINE_PATH}")
    elif check_baseline:
        baseline = load_baseline(BASELINE_PATH)
        if not baseline:
            print(f"\nNo baseline found at {BASELINE_PATH} yet — "
                  "run with --update-baseline to create one.")
        else:
            regressions = compare_to_baseline(report['summary_statistics'], baseline, margin)
            if regressions:
                regression_free = False
                print("\n⚠ PERFORMANCE REGRESSIONS DETECTED (vs baseline):")
                for r in regressions:
                    print(f"  - {r}")
            else:
                print("\n✅ No performance regressions vs baseline.")

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

    return regression_free


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
    
    benchmark.run_batch_benchmarks(valid_files)
    
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

    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write this run's per-stage medians as the new checked-in baseline "
             "(benchmarks/baseline.json) instead of comparing against it (#372/PERF-A-02)"
    )

    parser.add_argument(
        "--no-baseline-check",
        action="store_true",
        help="Skip the baseline regression comparison (report-only, like the old behavior)"
    )

    parser.add_argument(
        "--baseline-margin",
        type=float,
        default=DEFAULT_BASELINE_REGRESSION_MARGIN,
        help=f"Fail if a stage's median exceeds baseline * margin "
             f"(default: {DEFAULT_BASELINE_REGRESSION_MARGIN})"
    )

    args = parser.parse_args()

    # Determine which files to benchmark
    files_to_benchmark = []

    if args.files:
        files_to_benchmark = args.files
    elif args.directory:
        files_to_benchmark = find_test_files(args.directory, args.pattern)
    else:
        # Run baseline benchmark against the deterministic fixture set,
        # exiting non-zero on a detected regression so this actually fails a
        # CI/local run (#372/PERF-A-02) rather than only printing a warning.
        ok = run_baseline_benchmark(
            check_baseline=not args.no_baseline_check,
            update_baseline=args.update_baseline,
            margin=args.baseline_margin,
        )
        sys.exit(0 if ok else 1)

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
