# ARR-2026-08-05-1: Noise strike-decay merges back-to-back same-pitch drum hits into one strike, dropping re-attacks past 6 frames

**Severity:** HIGH · **Domain:** arranger · **Source:** docs/audits/AUDIT_ARRANGER_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/391

## Description
The #359 noise strike-decay fix (`bc5467a`) groups `frames["noise"]` into "strikes" purely
by contiguous frame number + matching period, with no concept of a discrete note event.
`_apply_sustain` (default on, 200ms gap) routinely produces zero-gap same-pitch frame runs
for fast repeated percussion (e.g. 16th-note hi-hats at 120 BPM = 7.5 frames apart), so
back-to-back separate drum hits collapse into a single decaying strike — later hits' real
volume is discarded and any hit beyond the 6-frame decay window vanishes with no re-attack.
The legacy `NESEmulatorCore` noise path doesn't have this bug since it iterates discrete
MIDI note events rather than an already-flattened frame dict.

## Location
`arranger/voice_allocator.py:476-511` (`FrameByFrameAllocator._apply_noise_strike_decay`)

## Impact
Any `--arranger` build with fast repeated same-pitch percussion hears hits collapse into
one decaying strike instead of a repeated pattern — a regression vs. both the legacy
front-end and the pre-`bc5467a` flat-volume behavior.

## Suggested Fix
Detect a new strike on a volume increase, or move decay application earlier to operate on
the original per-note event list (mirroring the legacy path) instead of a flattened frame
dict.
