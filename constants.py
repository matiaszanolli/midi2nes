FRAME_RATE_HZ = 60
FRAME_MS = 1000 / FRAME_RATE_HZ

# Pattern-length bounds shared by every pattern-detection call site so the
# production pipeline, the `detect-patterns` subcommand, and the benchmark all
# exercise the same work profile (#262/PERF-11). Kept here (a leaf module with
# no imports) rather than in main.py so benchmarks/ can import them without the
# main.py <-> benchmarks circular dependency.
PATTERN_MIN_LENGTH = 3
PATTERN_MAX_LENGTH = 12
