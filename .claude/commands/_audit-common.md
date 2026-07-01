# Shared Audit Protocol — MIDI2NES

This file is referenced by all audit skills. Do NOT use as a slash command (prefixed with `_`).

## Project Layout

```
Entry point:      main.py                              (CLI dispatch + run_full_pipeline; default = MIDI→ROM)
Version:          midi2nes/__version__.py

MIDI core:        tracker/
  Fast parser:    tracker/parser_fast.py               (parse_midi_to_frames — 120x; default front-end)
  Full parser:    tracker/parser.py                    (older full-feature parser)
  Track mapper:   tracker/track_mapper.py              (assign_tracks_to_nes_channels — legacy mode)
  Tempo:          tracker/tempo_map.py                 (EnhancedTempoMap — frame-accurate tempo)
  Loops:          tracker/loop_manager.py              (loop point detection)
  Patterns (par): tracker/pattern_detector_parallel.py (ParallelPatternDetector — multi-core)
  Patterns (seq): tracker/pattern_detector.py          (EnhancedPatternDetector — fallback + detect-patterns subcommand)

Arranger:         arranger/                            (--arranger mode; polyphony → NES via arpeggiation)
  Role analysis:  arranger/role_analyzer.py            (VoiceRoleAnalyzer — bass/melody/harmony)
  Voice alloc:    arranger/voice_allocator.py          (channel allocation + arpeggiation)
  GM map:         arranger/gm_instruments.py           (GM program → NES channel/duty)
  Integration:    arranger/pipeline_integration.py     (arrange_for_nes entry point)

NES core:         nes/
  Frame gen:      nes/emulator_core.py                 (NESEmulatorCore.process_all_tracks → frames dict)
  Pitch:          nes/pitch_table.py                   (channel-specific NTSC frequency tables)
  Envelope:       nes/envelope_processor.py            (ADSR / velocity → volume)
  Project build:  nes/project_builder.py               (NESProjectBuilder — main.asm/music.asm/nes.cfg)
  Song bank:      nes/song_bank.py                     (multi-song banks; `song` subcommands)
  Debug overlay:  nes/debug_overlay.py                 (--debug on-screen APU/frame diagnostics)

Mappers:          mappers/                             (BaseMapper + nrom/mmc1/mmc3 + factory)
  Interface:      mappers/base.py                      (BaseMapper ABC: header/linker/init/bankswitch/capacity)
  Factory:        mappers/factory.py                   (MapperFactory — size-based auto-select)

Exporters:        exporter/
  Base:           exporter/base_exporter.py            (BaseExporter)
  CA65:           exporter/exporter_ca65.py            (export_tables_with_patterns → music.asm)
  NSF:            exporter/exporter_nsf.py             (NSFExporter)
  FamiStudio:     exporter/exporter_famistudio.py      (FamiStudio text export)
  Compression:    exporter/compression.py

DPCM/drums:       dpcm_sampler/
  Drum mapper:    dpcm_sampler/enhanced_drum_mapper.py (EnhancedDrumMapper, DrumMapperConfig)
  Sample mgr:     dpcm_sampler/dpcm_sample_manager.py
  Engine:         dpcm_sampler/drum_engine.py
  Converter:      dpcm_sampler/dpcm_converter.py
  Packer:         dpcm_sampler/dpcm_packer.py
  Index gen:      dpcm_sampler/generate_dpcm_index.py
  Index data:     dpcm_index.json                      (sample → DPCM mapping table)

Compiler:         compiler/
  ROM compiler:   compiler/compiler.py                 (ROMCompiler / compile_rom — validate→assemble→link→verify)
  CC65 wrapper:   compiler/cc65_wrapper.py             (ca65 / ld65 invocation)

Shared types:     core/
  DTOs:           core/dto.py
  Types:          core/types.py
  Exceptions:     core/exceptions.py                   (CompilationError, ValidationError)

Config:           config/config_manager.py + config/default_config.yaml
Benchmarks:       benchmarks/performance_suite.py + benchmarks/run_benchmarks.py
Profiling:        utils/profiling.py                   (get_memory_usage, log_memory_usage)
Debug tools:      debug/                               (rom_diagnostics, check_rom, rom_tester, nes_devtools)
Tests:            tests/                               (43 test_*.py + conftest.py)
```

## Key Reference Docs

These docs under `docs/` are the authoritative, hardware-verified reference for
their domain. Prefer them over re-deriving NES behavior from source during an audit.

| Doc | What it documents |
|-----|------------------|
| `docs/NES_APU_REFERENCE.md` | APU overview, register map ($4000–$4017) |
| `docs/APU_PULSE_REFERENCE.md` | Pulse1/Pulse2 channel registers, duty, sweep |
| `docs/APU_TRIANGLE_REFERENCE.md` | Triangle channel (linear counter, no volume) |
| `docs/APU_NOISE_REFERENCE.md` | Noise channel period/mode |
| `docs/APU_DMC_REFERENCE.md` + `docs/NES_DMA_REFERENCE.md` | DMC/DPCM playback, DMA timing |
| `docs/APU_PITCH_TABLE_REFERENCE.md` | NTSC pitch/timer tables (channel-specific) |
| `docs/APU_ENVELOPE_REFERENCE.md` | Hardware envelope/decay behavior |
| `docs/APU_FRAME_COUNTER_REFERENCE.md` | Frame counter / 60Hz quarter-frame clocks |
| `docs/APU_LENGTH_COUNTER_REFERENCE.md` / `docs/APU_MIXER_REFERENCE.md` | Length counter, channel mixing levels |
| `docs/2A03_CPU_REFERENCE.md` | 2A03 CPU (1.789773 MHz NTSC) |
| `docs/MAPPER_MMC1_REFERENCE.md` / `docs/MAPPER_MMC3_REFERENCE.md` | Mapper register/bank behavior |
| `docs/AUDIO_BYTECODE_SPEC.md` | The generated music data bytecode format the engine plays back |
| `docs/MACRO_USAGE_GUIDE.md` / `docs/arpeggio.md` | Macro system + arpeggiation semantics |
| `docs/ROADMAP.md` / `docs/WORK_PLAN_1.0.0.md` | Roadmap and milestone status (treat as floor, flag doc-rot) |
| `CLAUDE.md` | Build/test commands, pipeline flow, mapper note (prepare defaults to MMC3) |

## NES Hardware Constraints (the invariants audits check against)

- 4 tone channels + DPCM: **Pulse1, Pulse2, Triangle, Noise** (+ DPCM for drums/samples).
- Triangle has **no volume control** (on/off only) and **no duty**.
- NTSC CPU clock **1.789773 MHz**; pitch timers are 11-bit ($0–$7FF) and **differ per channel** (triangle table ≠ pulse table).
- Playback runs at **60 FPS via NMI** — frame data is one entry per 1/60s tick. Do not change the timing model.
- APU register window **$4000–$4017**; channel enables at **$4015**; frame counter at **$4017**.
- ROM is iNES: 16-byte header + PRG-ROM. The selected mapper (NROM/MMC1/MMC3) sets PRG size, banks, and `nes.cfg`. Reset/NMI/IRQ vectors at **$FFFA–$FFFF** must point at valid code.

## Inter-Stage Data Contracts (what each pipeline stage hands off)

A finding that breaks one of these contracts is at least HIGH (see `_audit-severity.md`).

- **parse** → JSON `{"events": [...], ...}` (from `tracker/parser_fast.py`).
- **map** → per-NES-channel mapped events (`assign_tracks_to_nes_channels(events, dpcm_index_path)`), OR
  **arrange** (`--arranger`) → the same downstream `frames`-compatible structure via `arrange_for_nes(events, ...)`.
- **frames** → `NESEmulatorCore.process_all_tracks` returns `{channel_name: {frame_num: {note, volume, ...}}}`.
- **detect-patterns** → dict with keys **`patterns`**, **`references`**, **`stats`** (`compression_ratio`, `original_size`/`original_events`, `compressed_size`, `unique_patterns`/`patterns_found`), **`variations`**. `--no-patterns` builds a stub with empty `patterns`/`references` and `compression_ratio` 1.0.
- **export** → `CA65Exporter.export_tables_with_patterns(frames, patterns, references, output_path)` writes `music.asm`.
- **prepare** → `NESProjectBuilder` writes `main.asm`/`music.asm`/`nes.cfg` + build scripts (default mapper **MMC3**).
- **compile** → `compiler.compile_rom(project_dir, output_rom)` (requires CC65 `ca65`/`ld65`); validates min ROM size.

## Methodology

- Be skeptical. Assume there are bugs even if the code "looks fine."
- For each claim, re-read the code path to confirm before including it.
- Prefer evidence from concrete code paths (call sites, data structures, configs) over assumptions.
- After making a finding, attempt to disprove it. Only include findings you cannot disprove.
- For NES-behavior claims, cite the relevant `docs/APU_*.md` / `docs/MAPPER_*.md` rather than asserting from memory.

## Python-Specific Context Rules

- **Inter-stage JSON drift**: every stage reads/writes JSON. A key renamed in one producer but not its consumer is a silent break — `grep` the key across producer and consumer.
- **Error handling**: bare `except:` / `except Exception: pass` that swallows a real failure is a finding; so is `json.loads` / file I/O with no guard on a user-supplied path.
- **Subprocess**: `compiler/cc65_wrapper.py` shells out to `ca65`/`ld65` — check return-code handling, missing-tool detection, and that stderr surfaces.
- **Multiprocessing**: `ParallelPatternDetector` uses worker pools — check shared-state mutation, pickle-ability of args, and the documented graceful fallback to `EnhancedPatternDetector`.
- **Numeric width**: NES values are bytes / 11-bit timers. Flag any path that can emit a note/volume/timer out of hardware range without clamping.
- **Float frame timing**: tempo→frame conversion is float math; flag accumulation that can drift off the 60Hz grid.

## Context Management Rules

- **Grep before Read** — search for the specific symbol first, then read only the relevant section.
- **Paginate large files** — use `offset`/`limit` on `Read` for big modules.
- **Incremental writes** — append findings to the report as you go.
- **One dimension at a time** — finish and write up one dimension before starting the next.

## Path-Reference Convention

Backticked file/dir paths in any `audit-*/SKILL.md` (or this file) **must resolve against
the live repository tree**. The gate at `.claude/commands/_audit-validate.sh` enforces this.

- Backticks = "this path exists right now". The gate fails the audit if it doesn't.
- Forward-looking refs (a not-yet-created file) or removed files **must not** use backticks —
  write them as plain text or italics.
- Run `.claude/commands/_audit-validate.sh` before committing edits to any audit skill.

## Deduplication (MANDATORY)

Before reporting ANY finding:

1. Run: `gh issue list --repo matiaszanolli/midi2nes --limit 200 --json number,title,state,labels` and save to `/tmp/audit/issues.json`
2. Search for keywords from your finding in existing issue titles.
3. Scan `docs/audits/` for prior reports covering the same issue.
4. If OPEN: note as "Existing: #NNN" and skip.
5. If CLOSED: verify the fix is in place. If regressed, report as "Regression of #NNN".
6. If no match: report as NEW.

## Base Per-Finding Format

```
### <ID>: <Short Title>
- **Severity**: CRITICAL | HIGH | MEDIUM | LOW
- **Dimension**: <audit area>
- **Location**: `<file-path>:<line-range>`
- **Status**: NEW | Existing: #NNN | Regression of #NNN
- **Description**: What is wrong and why
- **Evidence**: Code snippet or exact call path demonstrating the issue
- **Impact**: What breaks, when, blast radius (which game / which pipeline stage / which channel)
- **Related**: Links to related findings or issues
- **Suggested Fix**: Brief direction (1-3 sentences)
```

Some audits add extra fields (e.g. `Changed in`, `Hardware ref`) — see each skill.

## Labels

The repo currently has only the **default GitHub label set**
(`bug`, `enhancement`, `duplicate`, `question`, `help wanted`, `invalid`, `wontfix`).
There are **no** severity or domain labels yet. `/audit-publish` is the single place
this is reconciled: it pulls the live label set with
`gh label list --repo matiaszanolli/midi2nes`, and either (a) creates the recommended
severity/domain set once (deliberate, see `/audit-publish`), or (b) files with `bug` /
`enhancement` only and encodes severity + domain as a badge line in the issue body.
**Never** pass a label to `gh issue create` that is not in the live set — it rejects unknown labels.

## Report Finalization

1. Save your report to: `docs/audits/AUDIT_<TYPE>_<TODAY>.md` (YYYY-MM-DD format).
2. Do NOT create GitHub issues directly.
3. Inform the user the report is ready and suggest:
   ```
   /audit-publish docs/audits/AUDIT_<TYPE>_<TODAY>.md
   ```
