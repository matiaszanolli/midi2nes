# F-04: Pattern-detector fallback truncates events to 2000 with no incomplete-output warning

**Severity:** CRITICAL · **Domain:** pipeline

The sequential fallback samples large event lists down (2000) and the success banner is
unconditional, so a truncated ROM ships as SUCCESS with no prominent warning.

## Suggested Fix
Print a prominent WARNING and reflect the incomplete output in the success banner.
