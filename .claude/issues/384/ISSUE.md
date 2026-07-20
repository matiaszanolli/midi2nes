# SAFE-2026-07-19-2: Whole 8-step pipeline wrapped in one broad except Exception

**Issue:** #384
**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-19.md
**Labels:** low, safety, enhancement
**Dimension:** D1 (Swallowed-Error Handling)
**Status as filed:** NEW

## Description
`run_full_pipeline` wraps all eight steps in a single try/except Exception (print + sys.exit(1)). It cannot discriminate failure classes programmatically. Not a live swallowed-bug: every underlying surface raises a specific typed exception (InvalidMIDIError, ConfigurationError, ToolchainError, CompilationError, ValidationError) whose message is relayed; -v prints full traceback. Residual concern is defense-in-depth/testability only.

## Location
`main.py:848-1173` (try at :848, except Exception as e at :1167)

## Suggested Fix
Optionally catch MIDI2NESError (typed base) distinctly from a final except Exception for truly unexpected defects, so the two are logged/tested differently.

## Related
SAFE-2026-07-19-1 (#381); #125/SAFE-08 (analogous narrowing in config_manager).
