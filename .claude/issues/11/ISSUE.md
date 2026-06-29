# M-3: Music data never size-checked against mapper PRG capacity

**Severity:** CRITICAL · **Domain:** mappers

can_fit_data/get_data_capacity are never called from the pipeline; oversized music flows
straight to ld65 with no pipeline-side pre-flight.

## Suggested Fix
Compute emitted size and call mapper.can_fit_data() before linking; clear error on overflow.
