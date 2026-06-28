# Project History

A chronological record of MIDI2NES development. For the forward-looking plan see
[docs/ROADMAP.md](docs/ROADMAP.md); for durable architectural knowledge see
[MEMORY.md](MEMORY.md).

> Dates are taken from the git history. The project began as a 2016 proof of
> concept, was abandoned, then fully rewritten starting **2025-07-15**
> ("Complete refactor"). Everything from v0.2.0 onward describes the rewrite.

---

## v0.5.0-dev — The Macro Engine & Arranger Update *(2025-12 → 2026-06, in progress)*

The largest architectural leap since the rewrite. Static, frame-by-frame APU
dumps were replaced by a compact bytecode interpreter that runs on the NES, and
a full intelligent-arrangement front-end was added.

- **MMC3 Macro-Driven Bytecode Engine** — a dynamic, compressed bytecode
  interpreter (`exporter/exporter_ca65.py` + the in-ROM audio engine) replaces
  static register dumps. Volume / pitch / duty / arpeggio envelopes are encoded
  as reusable macros with dynamic MMC3 bank switching for sequence data.
- **DPCM sample support** — `dpcm_sampler/` with First-Fit-Decreasing sample
  packing (`DpcmPacker`), automatic bank allocation, and DMC level handling in
  the exporter and audio engine.
- **Arranger mode (`--arranger`)** — new `arranger/` package: role analysis
  (bass/melody/harmony), GM-program → NES-channel/duty mapping, smart channel
  allocation, and hardware arpeggiation for polyphonic content.
- **MMC3 as default mapper** — `prepare` and `run_full_pipeline` now build MMC3
  projects (`NESProjectBuilder` + dynamic linker config for DPCM segments).
- **On-screen debug overlay (`--debug`)** — real-time APU, frame-counter, and
  zero-page pointer diagnostics rendered inside the generated ROM.
- **Logarithmic velocity → volume scaling** — perceptually accurate envelope
  volume across pulse/noise channels and the macro engine.
- **Audit tooling** — shared audit protocol, severity definitions, and a suite
  of audit skills (NES hardware, pipeline, patterns, exporters, mappers, DPCM,
  arranger, tempo, performance, safety, tech-debt, regression).
- **Reference docs** — extensive APU / mapper / bytecode references under
  [docs/](docs/) (`AUDIO_BYTECODE_SPEC.md`, `MACRO_USAGE_GUIDE.md`, the
  `APU_*_REFERENCE.md` set, `MAPPER_MMC*_REFERENCE.md`).

## v0.4.0-dev — Performance Revolution & Foundations *(2025-08)*

- **120× faster parsing** — `tracker/parser_fast.py` performs minimal
  MIDI→frames conversion; pattern/loop detection split into later stages.
- **Multi-core pattern detection** — `ParallelPatternDetector` distributes work
  across all CPU cores with smart sampling for very large files and graceful
  single-process fallback.
- **MMC1 128KB ROM support** — large-file ROM generation with NMI-based 60 Hz
  timing; fixed the silent-ROM frame-key type-mismatch bug.
- **Version management** — `midi2nes/__version__.py` and a `--version` flag.
- **Configuration system** — `config/config_manager.py` + `default_config.yaml`,
  with `config init` / `config validate` subcommands and dot-notation access.
- **Benchmarking** — `benchmark run` / `benchmark memory` subcommands and the
  `benchmarks/` performance suite (parse speed + memory profiling).
- **Debug tooling** — `debug/` ROM diagnostics, audio checker, pattern analysis,
  music-structure analyzer, and the `rom_tester` harness.
- **CLI/UX** — visual progress bars, richer help, verbose mode.

## v0.3.5 — Advanced Pattern Detection *(2025-07-29)*

- Pattern detection with **variation support** (transposition/volume shifts) and
  NES-specific compression optimizations.
- Enhanced drum mapping and tempo optimization.

## v0.3.0 — Export Formats & Multi-Song *(2025-07-19 → 2025-07-29)*

- **NSF export** with pattern compression (`exporter/exporter_nsf.py`).
- **FamiStudio export** (`exporter/exporter_famistudio.py`).
- **Pattern compression module** (`exporter/compression.py`) and a dedicated
  pattern exporter.
- **Multi-song song banks** (`nes/song_bank.py`) with bank compression.
- DPCM samples added to the drum/sampler path.
- *(v0.3.0b1 tagged 2025-07-19; v0.3.0 finalized 2025-07-29.)*

## v0.2.0 — Core Pipeline Maturity *(2025-07-15 → 2025-07-16)*

- Complete architectural refactor of the 2016 prototype.
- Pitch processor with per-channel NES pitch tables.
- Envelope and pitch control improvements.
- `EnhancedTempoMap` module with frame alignment.
- Loop manager and the first pattern detector.
- CC65 project compiler with correct iNES headers; end-to-end ASM output for a
  single track.

## Prehistory *(2016)*

- Initial commits: converted a single MIDI track into NES assembly. Shelved
  until the 2025 rewrite.

---

### Test-suite growth

| Milestone        | Tests passing |
|------------------|---------------|
| v0.3.5           | 177           |
| v0.4.0 (config)  | 186           |
| v0.5.0-dev       | 586 (45 files)|
