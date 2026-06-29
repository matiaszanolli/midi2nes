# F-03: Unknown/typo flags on the default path are silently swallowed → wrong ROM

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md

The hand-rolled default-path dispatcher whitelists six flags then `elif arg.startswith('-'):
i += 1` — silently dropping unknown flags. A user typing --no-pattern/--arrange gets the
default mode silently (a different ROM).

## Suggested Fix
Replace the silent skip with print 'Unknown option' + sys.exit(2).
