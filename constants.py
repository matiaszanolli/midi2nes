FRAME_RATE_HZ = 60
FRAME_MS = 1000 / FRAME_RATE_HZ

# DMC playback rate dpcm_packer.DpcmPacker.add_sample defaults new samples to
# (docs/APU_DMC_REFERENCE.md §2's NTSC rate-index table, index 15 -- the
# fastest/highest-fidelity rate). DEFAULT_DMC_RATE_HZ is that index's real
# playback frequency; kept here (a leaf module) so any code producing or
# consuming a .dmc file at the packer's default rate agrees on the same
# number instead of each defining its own copy (#342/DP-DPCM-03).
DEFAULT_DMC_PITCH_RATE = 15
DEFAULT_DMC_RATE_HZ = 33144

# Pattern-length bounds shared by every pattern-detection call site so the
# production pipeline, the `detect-patterns` subcommand, and the benchmark all
# exercise the same work profile (#262/PERF-11). Kept here (a leaf module with
# no imports) rather than in main.py so benchmarks/ can import them without the
# main.py <-> benchmarks circular dependency.
PATTERN_MIN_LENGTH = 3
PATTERN_MAX_LENGTH = 12
