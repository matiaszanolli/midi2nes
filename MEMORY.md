# Project Memory

Durable, non-obvious knowledge about MIDI2NES — the things that aren't visible
from a quick read of the code and that tend to bite. Pairs with
[CLAUDE.md](CLAUDE.md) (working instructions), [HISTORY.md](HISTORY.md)
(what changed when), and [docs/ROADMAP.md](docs/ROADMAP.md) (what's next).

## Current status (v0.5.0-dev)

- End-to-end pipeline is operational: `python main.py input.mid output.nes`.
- **1024 tests** across 53 files, all passing (`python -m pytest`).
- Two front-ends produce the same `frames` dict: **legacy** (default) and
  **arranger** (`--arranger`). Everything downstream of frames is shared.
- Default mapper is **MMC3** (not MMC1 — older docs lie). DPCM lives in
  MMC3-switched banks.

## Pipeline shape

```
MIDI → Parse → Map/Arrange → Frames → Patterns → Export → Project → Compile → ROM
       fast     NES chans     60fps    compress   CA65     builder    CC65     .nes
```

`run_full_pipeline` in [main.py](main.py) runs every stage in a temp dir and
ends at `compiler.compile_rom`, so the single-command form **requires the CC65
toolchain** (`ca65`/`ld65`) installed. The step subcommands (`parse`, `map`,
`frames`, `detect-patterns`, `export`, `prepare`) do not.

## Gotchas worth remembering

- **Frame keys are strings, not ints.** A type mismatch on frame keys caused
  silent ROMs historically (fixed 2025-12-26). Watch for it when touching
  frame dicts.
- **Stale docs under `docs/legacy/`** describe the MMC1 era and say "always use
  MMC1." That is no longer true; MMC3 is the default. CLAUDE.md's "ROM
  Structure" note is similarly stale on the mapper.
- **Pattern detection has two implementations.** `ParallelPatternDetector`
  (`tracker/pattern_detector_parallel.py`) is the default and is multi-core with
  smart sampling + graceful fallback; `EnhancedPatternDetector`
  (`tracker/pattern_detector.py`) is the single-process path used by
  `detect-patterns` and as fallback. Keep their output schemas identical
  (patterns, references, stats, variations).
- **`parser_fast.py` is intentionally minimal.** It only does MIDI→frames; loop
  detection, pattern detection and optimization are separate stages. That split
  is what buys the 120× speedup — don't fold them back in.
- **NMI 60 Hz timing is load-bearing.** `main.asm` drives the music update from
  the NMI handler; do not change the timing model.

## Where things live

- `tracker/` — parsing, tempo map, track mapping (legacy), pattern detection,
  loop manager.
- `arranger/` — role analysis, GM-instrument mapping, voice allocation +
  arpeggiation; `arrange_for_nes` is the entry point.
- `exporter/` — CA65 (macro bytecode engine), NSF, FamiStudio, compression.
- `mappers/` — `base.py` + `nrom`/`mmc1`/`mmc3`; `MapperFactory` auto-selects by
  data size.
- `nes/` — frame generation (`emulator_core.py`), project builder, pitch tables,
  envelope processor, song bank.
- `dpcm_sampler/` — drum mapping + DPCM sample management/packing (FFD).
- `compiler/` — CC65 wrapper and `compile_rom` (validate → assemble → link →
  verify).
- `debug/` — ROM diagnostics, quick `check_rom`, `rom_tester` harness.

## NES hardware constraints (don't violate)

- 4 channels: Pulse1, Pulse2, Triangle, Noise (+ DPCM for drums).
- NTSC CPU clock 1.789773 MHz; pitch tables are **per-channel** (Pulse ≠
  Triangle).
- iNES header is 16 bytes; reset vectors at `$FFFA-$FFFF` must point to valid
  code; APU registers are `$4000-$4015`.
