# F-03: Unknown/typo flags on the default path are silently swallowed → wrong ROM (silent song change)

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #8

## Description
The hand-rolled default-path dispatcher whitelists six flags then `elif arg.startswith('-'): i += 1  # Skip unknown options for now`. A user typing `--no-pattern` (missing s), `--arrange`, `--no-validation`, or `--skipvalidation` has the flag silently discarded; the pipeline runs default mode (patterns ON, legacy mapping, validation ON).

## Evidence
main.py:664-666 increments i with no error. Live repro: `--no-pattern` and `--arrange` both reach the input-existence check, proving the flag was dropped not rejected.

## Impact
Intending --no-patterns silently gets the pattern path (F-01); intending --arranger silently gets legacy single-voice mapping — voices dropped, different song. Silently different song is CRITICAL. Subcommands correctly error via argparse; the bug is specific to the manual default-path loop.

## Related
F-05, F-01

## Suggested Fix
Replace silent skip with `print(Unknown option) ; sys.exit(2)`, or route default path through argparse parse_known_args and reject leftovers.

**Location:** `main.py:664-666`
