import argparse
import sys
import json
import tempfile
import shutil
from typing import Optional
from pathlib import Path

# Import version information
try:
    from midi2nes import __version__
except ImportError:
    # Fallback for development mode
    __version__ = "0.5.0-dev"

from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore, frames_to_events
from arranger import arrange_for_nes
from nes.project_builder import NESProjectBuilder, NES_CFG_MAPPER_MARKER
from nes.song_bank import SongBank
from exporter.exporter_ca65 import CA65Exporter
from tracker.pattern_detector import (
    EnhancedPatternDetector, sample_events_for_detection, DETECTOR_MAX_EVENTS, MAX_PATTERN_EVENTS
)
from tracker.tempo_map import EnhancedTempoMap
from dpcm_sampler.enhanced_drum_mapper import DrumMapperConfig
from config.config_manager import ConfigManager
from core.exceptions import ConfigurationError
from benchmarks.performance_suite import PerformanceBenchmark
from utils.profiling import get_memory_usage, log_memory_usage
from compiler import compile_rom

# Shared pattern-detection bounds. Both entry points (the `detect-patterns`
# subcommand and the default full pipeline) must use identical parameters so
# their `patterns`/`references` JSON artifacts agree for the same input (#19).
PATTERN_MIN_LENGTH = 3
PATTERN_MAX_LENGTH = 12

def get_pattern_detection_caps(config_path: Optional[str] = None):
    """Resolve the sequential/parallel pattern-detection event-sampling caps.

    Defaults to the hardcoded DETECTOR_MAX_EVENTS/MAX_PATTERN_EVENTS constants;
    when `config_path` is given, `processing.pattern_detection.max_events` /
    `max_pattern_events` override them (#219) — this is the single place both
    the `detect-patterns` subcommand and the default full pipeline resolve
    these caps from, so they stay in sync.
    """
    max_events = DETECTOR_MAX_EVENTS
    max_pattern_events = MAX_PATTERN_EVENTS
    if config_path:
        try:
            config_manager = ConfigManager(config_path)
        except ConfigurationError as e:
            # Clean [ERROR] + exit, matching load_json_stage's convention --
            # main.py has no outer caller to catch this for every subcommand
            # that reaches here (#267/PL-07).
            print(f"[ERROR] {e}")
            sys.exit(1)
        max_events = config_manager.get("processing.pattern_detection.max_events", DETECTOR_MAX_EVENTS)
        max_pattern_events = config_manager.get(
            "processing.pattern_detection.max_pattern_events", MAX_PATTERN_EVENTS)
    return max_events, max_pattern_events

def load_json_stage(path, required_keys, stage_name):
    """Load an inter-stage JSON artifact with an existence/parse/key guard.

    Every step-by-step subcommand did `json.loads(Path(input).read_text())`
    then immediately indexed a hard-coded key, so a missing file, a
    truncated/garbage file, or a file from the wrong pipeline stage all
    surfaced as a raw traceback (FileNotFoundError / JSONDecodeError /
    KeyError) on the documented step-by-step debugging path instead of a
    clear message (#120). Exits with a clean [ERROR] message and code 1,
    matching every other subcommand guard in this file (#110, #13, #15)
    rather than raising, since main.py has no outer caller to catch it.
    """
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] {stage_name} input not found: {p}")
        sys.exit(1)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"[ERROR] {stage_name} input is not valid JSON: {p} ({e})")
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"[ERROR] {stage_name} input must be a JSON object: {p}")
        sys.exit(1)
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(f"[ERROR] {stage_name} input missing expected key(s) {missing}: {p} "
              f"(is this the right stage's JSON?)")
        sys.exit(1)
    return data

def run_parse(args):
    # Use fast parser by default for better performance
    from tracker.parser_fast import parse_midi_to_frames as parse_fast
    midi_data = parse_fast(args.input)
    # Compact separators (#116): this is a machine-only intermediate a human
    # rarely opens, and indent=2 typically inflates it 2-3x for no benefit.
    Path(args.output).write_text(json.dumps(midi_data, separators=(',', ':')))
    print(f"[OK] Parsed MIDI -> {args.output}")

def run_map(args):
    # Guard against a missing/corrupt file or wrong-stage JSON (#110, #120).
    midi_data = load_json_stage(args.input, ['events'], 'parse')
    # Honor --dpcm-index instead of silently using the default (#13).
    dpcm_index_path = getattr(args, 'dpcm_index', None) or 'dpcm_index.json'
    # Extract just the events from the parsed data
    mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
    Path(args.output).write_text(json.dumps(mapped, separators=(',', ':')))
    print(f"[OK] Mapped tracks -> {args.output}")

def run_frames(args):
    # Guard against a missing/corrupt file (#120); the mapped JSON's channel
    # keys are all optional, so there is no fixed required key to validate.
    mapped = load_json_stage(args.input, [], 'map')
    emulator = NESEmulatorCore()
    frames = emulator.process_all_tracks(mapped)
    Path(args.output).write_text(json.dumps(frames, separators=(',', ':')))
    print(f" Generated frames -> {args.output}")

def estimate_segment_sizes(music_asm_path):
    """ROM byte totals music.asm emits (.byte/.word/.incbin), keyed by the active
    `.segment "NAME"`.

    Per-segment rather than a single total because a banked mapper (MMC3)
    distributes data across distinct PRG regions, and the binding limit is the
    region each segment lands in, not the full PRG (#126, #127). ld65 remains the
    exact backstop. .res lives in RAM/ZP (not PRG ROM) and is ignored. A bounded
    `.incbin "f", 0, N` (a truncated DPCM sample, #68) counts N, not the file size.
    """
    import re
    music_path = Path(music_asm_path)
    if not music_path.exists():
        return {}
    sizes = {}
    current = None
    base_dir = music_path.parent
    for raw in music_path.read_text().splitlines():
        line = raw.split(';', 1)[0].strip()  # drop comments
        low = line.lower()
        if low.startswith('.segment'):
            m = re.search(r'"([^"]+)"', line)
            if m:
                current = m.group(1)
            continue
        n = 0
        if low.startswith('.byte'):
            n = len([t for t in line[5:].split(',') if t.strip()])
        elif low.startswith('.word'):
            n = 2 * len([t for t in line[5:].split(',') if t.strip()])
        elif low.startswith('.incbin'):
            bounded = re.search(r'"[^"]+"\s*,\s*\d+\s*,\s*(\d+)', line)
            if bounded:
                n = int(bounded.group(1))
            else:
                m = re.search(r'"([^"]+)"', line)
                if m:
                    p = Path(m.group(1))
                    if not p.is_absolute():
                        p = base_dir / p
                    if p.exists():
                        n = p.stat().st_size
        if n:
            sizes[current] = sizes.get(current, 0) + n
    return sizes


def estimate_music_data_size(music_asm_path):
    """Total ROM data bytes music.asm emits (sum across all segments)."""
    return sum(estimate_segment_sizes(music_asm_path).values())


def _requires_mmc3_bytecode_engine(music_asm_path):
    """True if music.asm was generated by the MMC3 macro-bytecode (pattern-
    compressed) exporter path (CA65Exporter.export_tables_with_patterns with
    non-empty patterns), identified the same way nes/project_builder.py's
    `is_bytecode` does: a marker comment only that path emits.

    That engine's DPCM/sequence-bank switching (`switch_dpcm_bank`,
    `fetch_sequence_byte`) is built directly on MMC3's $8000/$8001 bank
    registers -- NROM has no bank switching at all and MMC1's
    generate_bank_switch_code() doesn't define a `switch_dpcm_bank` label, so
    a non-MMC3 build in this mode fails at link time with an unresolved
    external, not a clean error (discovered while wiring up #217/MAP-6).
    """
    path = Path(music_asm_path)
    return path.exists() and "MMC3 Macro Bytecode" in path.read_text()


def _direct_export_packed_mapper_name(music_asm_path):
    """Return the mapper name a direct-export music.asm was bin-packed for
    (e.g. 'MMC1'), or None.

    When a mapper's direct_export_bank_size() is not None (currently only
    MMC1), CA65Exporter.export_direct_frames bin-packs the frame tables into
    RODATA_BANK_NN segments that ONLY that mapper's linker config defines, and
    stamps a "; Direct export bank-packed for <name>" marker. `prepare`/
    `compile` parse their own --mapper independently, so a mismatched later
    choice (e.g. `export --mapper mmc1` then `prepare` with the mmc3 default)
    would otherwise pass check_mapper_capacity — which recognizes no
    RODATA_BANK_NN branch for the wrong mapper — and defer the failure to a raw
    ld65 "Missing memory area assignment" error (#283/MAP-2026-07-05B-3,
    #285/PL-09). This is the direct-export mirror of the bytecode-path guard
    _requires_mmc3_bytecode_engine.
    """
    path = Path(music_asm_path)
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        marker = "; Direct export bank-packed for "
        if line.startswith(marker):
            return line[len(marker):].strip()
    return None


def _prepared_mapper_name_from_cfg(nes_cfg_path):
    """Return the mapper name a project was prepared with, read from the
    leading marker NESProjectBuilder stamps into nes.cfg, or None.

    nes.cfg is the authoritative record of what `prepare` built. A NROM (or
    MMC1) direct-export project's music.asm carries no engine/bank marker, so
    without this `compile` cannot tell it apart from an MMC3 project and its
    --mapper default (mmc3) mis-sizes it (#297/MAP-2026-07-06-1). Recovering
    the mapper from nes.cfg makes the split prepare/compile flow round-trip for
    every mapper, and also gives `prepare --mapper auto` a matching compile
    invocation (#269/PL-08).
    """
    path = Path(nes_cfg_path)
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith(NES_CFG_MAPPER_MARKER):
            return line[len(NES_CFG_MAPPER_MARKER):].strip() or None
    return None


def resolve_mapper(mapper_choice, music_asm_path=None):
    """Resolve a --mapper CLI value ('auto', 'nrom', 'mmc1', 'mmc3') to a
    mapper instance (#217/MAP-6).

    MapperFactory.auto_select()'s smallest-fits-first selection previously
    had no caller outside tests/test_mappers.py -- every real build hardcoded
    MMC3Mapper. 'auto' estimates the music data size from music_asm_path and
    picks the smallest mapper that fits it; any other value is looked up
    directly via MapperFactory.get_mapper(). Either way, a music.asm built by
    the MMC3 macro-bytecode engine forces MMC3 -- see
    _requires_mmc3_bytecode_engine.
    """
    from mappers.factory import MapperFactory
    needs_mmc3 = music_asm_path is not None and _requires_mmc3_bytecode_engine(music_asm_path)
    packed_for = (_direct_export_packed_mapper_name(music_asm_path)
                  if music_asm_path is not None else None)
    if mapper_choice == 'auto':
        if needs_mmc3:
            return MapperFactory.get_mapper('mmc3')
        # A direct-export music.asm bin-packed for a specific banked mapper can
        # only link against that mapper's RODATA_BANK_NN regions, so 'auto'
        # must honor it rather than re-estimating a (smaller) mapper by size
        # (#283/#285) -- mirrors forcing MMC3 for the bytecode marker above.
        if packed_for:
            return MapperFactory.get_mapper(packed_for)
        data_size = estimate_music_data_size(music_asm_path)
        return MapperFactory.auto_select(data_size)
    mapper = MapperFactory.get_mapper(mapper_choice)
    if needs_mmc3 and mapper.mapper_number != 4:
        raise ValueError(
            f"{mapper.name} cannot run the MMC3 macro-bytecode (pattern-compressed) "
            f"engine this music.asm was built with -- rebuild with --no-patterns "
            f"for direct frame export, or pass --mapper mmc3."
        )
    if packed_for and mapper.name != packed_for:
        raise ValueError(
            f"this music.asm's frame tables were bank-packed for {packed_for} at "
            f"export time (RODATA_BANK_NN segments only {packed_for}'s linker config "
            f"defines), but --mapper {mapper_choice} was selected here -- re-export "
            f"with --mapper {mapper_choice} or run prepare/compile with "
            f"--mapper {packed_for.lower()}."
        )
    return mapper


def enforce_direct_export_dpcm_mapper(mapper, mapper_choice, frames):
    """Direct-export (--no-patterns) DPCM is MMC3-only. Return the mapper to
    actually build with, forcing MMC3 for 'auto' and rejecting an explicit
    non-MMC3 request (#281/MAP-2026-07-05B-1, #282/MAP-2026-07-05B-2).

    A song with a non-empty ``dpcm`` channel emits two hardcoded MMC3-only
    pieces in the direct-export path:
      - ``play_dpcm`` triggers a sample by writing MMC3's R6 bank-select port
        (``$8000``/``$8001``); on MMC1 those addresses are a 5-write serial
        shift register, so the two raw writes corrupt MMC1's Control register
        and can un-fix the engine/vector bank mid-song (#281);
      - ``DpcmPacker`` emits ``DPCM_NN`` segments only mmc3's nes.cfg defines,
        so a sample that actually packs fails to link on MMC1/NROM (#282).

    Neither path is mapper-aware yet (the MMC1 Mode-2 streaming design in
    docs/MAPPER_MMC1_REFERENCE.md §4 is unimplemented), so rather than ship a
    ROM that corrupts or won't link, mirror the bytecode path (always MMC3):
    'auto' picks MMC3 (a mapper that works); an explicit mmc1/nrom is a clean
    ValueError. Called only on the direct-export branch — the bytecode/pattern
    path is already forced to MMC3.
    """
    if not frames.get('dpcm'):
        return mapper
    if mapper.mapper_number == 4:  # MMC3
        return mapper
    if mapper_choice == 'auto':
        from mappers.mmc3 import MMC3Mapper
        return MMC3Mapper()
    raise ValueError(
        f"--mapper {mapper_choice} does not support DPCM samples in direct-export "
        f"(--no-patterns) mode: this song maps drums to the DPCM channel, whose "
        f"trigger/sample code is MMC3-only. Use --mapper mmc3 (the default) or "
        f"--mapper auto, or rebuild without --no-patterns."
    )


def get_mapper_choice(args):
    """Read args.mapper defensively, defaulting to 'mmc3' (#217/MAP-6).

    A plain `getattr(args, 'mapper', 'mmc3')` breaks for MagicMock-based args
    fixtures (used throughout tests/test_e2e_pipeline.py): MagicMock
    auto-vivifies any accessed attribute instead of raising AttributeError,
    so the getattr default is never reached and resolve_mapper() gets a
    MagicMock instead of a mapper name. Real CLI usage never hits this --
    argparse's `choices=` and the default pipeline's SimpleArgs both always
    set a valid string -- so falling back to 'mmc3' for anything else is
    safe, not a silent typo swallow.
    """
    value = getattr(args, 'mapper', 'mmc3')
    return value if isinstance(value, str) else 'mmc3'


def check_mapper_capacity(music_asm_path, mapper):
    """Pre-flight capacity gate (#11, #126, #127): abort before linking if the
    emitted music data overflows any of the selected mapper's PRG regions.

    Sizes each music.asm segment against the region the mapper's linker config
    loads it into (a banked mapper has several binding regions, not one 510 KB
    ceiling), so an oversized song fails with a clear budget message instead of a
    raw ld65 region overflow. Raises ValueError listing every overflow. Returns
    the total data size for logging.
    """
    segment_sizes = estimate_segment_sizes(music_asm_path)
    errors = mapper.validate_segment_sizes(segment_sizes)
    if errors:
        detail = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(
            f"Music data does not fit the {mapper.name} PRG layout:\n{detail}\n"
            f"Shorten the song or DPCM samples, or select a larger mapper."
        )
    return sum(segment_sizes.values())


def _backup_existing_rom(output_rom):
    """Back up a pre-existing ROM at output_rom before it gets overwritten
    (#178/PL-05), shared by the full pipeline and the `compile` subcommand so
    both get the same restore-on-failure contract.

    Returns the backup path, or None if there was nothing at output_rom yet.
    """
    output_rom = Path(output_rom)
    if not output_rom.exists():
        return None
    backup_path = output_rom.with_suffix('.nes.backup')
    print(f"  💾 Creating backup of existing ROM: {backup_path.name}")
    shutil.copy2(output_rom, backup_path)
    return backup_path


def _restore_backup(output_rom, backup_path):
    """Restore a pre-build backup ROM over the (now-invalid) output. If there
    was no pre-existing ROM to restore, move the freshly written unbootable
    ROM aside instead of leaving a broken .nes at the output path (#178/PL-05)."""
    output_rom = Path(output_rom)
    if backup_path and Path(backup_path).exists():
        print(f"  💊 Restoring backup ROM: {Path(backup_path).name} → {output_rom.name}")
        shutil.copy2(backup_path, output_rom)
        print(f"  ✅ Original ROM restored from backup")
    elif output_rom.exists():
        failed_path = Path(str(output_rom) + '.failed')
        print(f"  🗑️  Moving unbootable ROM aside: {output_rom.name} → {failed_path.name}")
        output_rom.replace(failed_path)


def validate_rom(output_rom):
    """Post-build ROM validation shared by the full pipeline and the `compile`
    subcommand (#15) so step-by-step ROMs get the same gate as the default path.

    Returns True if the ROM is bootable. On a boot-fatal defect (invalid
    $FFFA-$FFFF vectors or no APU init) it returns False — the caller owns backup
    restore (#26). Non-fatal health issues are warned but pass. A diagnostics
    engine failure (e.g. a broken `debug` import) is treated as a validation
    failure (#177/PL-04): callers only reach this function when the user did
    NOT pass --skip-validation, so silently accepting the ROM here would defeat
    the one gate that catches unbootable ROMs. The warning always prints, not
    just under --verbose, so a skipped validation is never silent.
    """
    try:
        from debug.rom_diagnostics import ROMDiagnostics
        rom_result = ROMDiagnostics(verbose=False).diagnose_rom(str(output_rom))
    except Exception as e:
        print(f"  ⚠️  Warning: ROM validation could not run: {e} — ROM NOT validated")
        return False

    fatal_defects = []
    if not rom_result.reset_vectors_valid:
        fatal_defects.append("invalid reset/NMI/IRQ vectors ($FFFA-$FFFF)")
    if rom_result.apu_pattern_count == 0:
        fatal_defects.append("no APU initialization code found")
    if fatal_defects:
        print("[ERROR] ROM validation failed - unbootable ROM:")
        for defect in fatal_defects:
            print(f"    - {defect}")
        return False

    if rom_result.overall_health not in ["HEALTHY", "GOOD"]:
        print(f"⚠️  ROM health check: {rom_result.overall_health}")
        print(f"  Issues found: {len(rom_result.issues)}")
        for issue in rom_result.issues[:3]:
            print(f"    - {issue}")
        if rom_result.overall_health == "ERROR":
            print("[ERROR] ROM validation failed - ROM is invalid")
            return False
    else:
        print(f"  ✓ ROM Health: {rom_result.overall_health}")
        print(f"  ✓ APU Patterns: {rom_result.apu_pattern_count}")
        print(f"  ✓ Assembly Score: {rom_result.assembly_code_score}/220")
    return True


def run_compile(args):
    """Compile a prepared NES project to a ROM and validate it (#15).

    Gives the step-by-step path the same compile + post-build validation the
    full pipeline runs, instead of stopping at `prepare` and building by hand.
    Also gives it the same backup/restore contract as the default pipeline
    (#178/PL-05): a pre-existing output ROM is backed up before compiling and
    restored if compilation or validation fails; a first-time build that fails
    validation has its unbootable ROM moved aside (`<name>.nes.failed`)
    instead of being left at the output path.
    """
    project_path = Path(args.input)
    output_rom = Path(args.output)
    if not project_path.is_dir():
        print(f"[ERROR] Prepared project directory not found: {project_path}")
        sys.exit(1)

    # The exact-size check (#28/M-8) and post-process step need the same mapper
    # the project was actually prepared with (#217/MAP-6). `prepare` stamps that
    # mapper into nes.cfg, so recover it from there authoritatively -- a marker-
    # less NROM/MMC1 music.asm would otherwise fall to the mmc3 default and be
    # rejected with a misleading size mismatch (#297/MAP-2026-07-06-1). This
    # also gives a `prepare --mapper auto` project a working compile (#269).
    # Fall back to --mapper (default mmc3) for older projects with no marker.
    # music.asm is still passed so resolve_mapper can catch a mapper that can't
    # run this project's bytecode engine.
    cfg_mapper = _prepared_mapper_name_from_cfg(project_path / "nes.cfg")
    mapper_choice = cfg_mapper if cfg_mapper else get_mapper_choice(args)
    try:
        mapper = resolve_mapper(mapper_choice, str(project_path / "music.asm"))
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    backup_path = _backup_existing_rom(output_rom)
    build_succeeded = False
    try:
        print(f"Compiling NES ROM from {project_path} ...")
        if not compile_rom(project_path, output_rom, verbose=getattr(args, 'verbose', False), mapper=mapper):
            print("[ERROR] ROM compilation failed")
            sys.exit(1)

        if not getattr(args, 'skip_validation', False):
            print("Validating ROM...")
            if not validate_rom(output_rom):
                sys.exit(1)

        build_succeeded = True
        print(f"[OK] Compiled ROM -> {output_rom}")
    finally:
        if not build_succeeded:
            _restore_backup(output_rom, backup_path)
        elif backup_path:
            backup_path.unlink(missing_ok=True)


def run_prepare(args):
    # --mapper (#217/MAP-6): 'auto' picks the smallest mapper that fits this
    # song's data via MapperFactory.auto_select(), previously reachable only
    # from tests/test_mappers.py. Defaults to mmc3, matching prior behavior
    # for callers who don't pass --mapper.
    try:
        mapper = resolve_mapper(get_mapper_choice(args), args.input)
        data_size = check_mapper_capacity(args.input, mapper)
        print(f"  ✓ Music data {data_size:,} bytes fits the {mapper.name} PRG regions")
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    # Honor --debug on the step-by-step `prepare` path the same way the default
    # pipeline does, instead of silently building a non-debug ROM (#175).
    builder = NESProjectBuilder(args.output, debug_mode=getattr(args, 'debug', False), mapper=mapper)
    # prepare_project may raise (bad path/permissions) or return falsy; either
    # way surface a clean nonzero exit instead of an uncaught traceback or a
    # silent exit 0 on failure (#15).
    try:
        prepared = builder.prepare_project(args.input)
    except Exception as e:
        print(f"[ERROR] Failed to prepare NES project: {e}")
        sys.exit(1)
    if not prepared:
        print("[ERROR] Failed to prepare NES project")
        sys.exit(1)
    print(f" Prepared NES project -> {args.output}")
    print(" Ready for CC65 compilation!")
    print(" To build:")
    print(f" 1. cd {args.output}")
    print(" 2. ./build.sh  (or build.bat on Windows)")
    print(" Or compile + validate in one step: python main.py compile "
          f"{args.output} <output.nes>")

def run_export(args):
    """Export function supporting multiple formats with pattern compression"""
    # Guard against a missing/corrupt file (#120); the frames JSON's channel
    # keys are all optional, so there is no fixed required key to validate.
    frames = load_json_stage(args.input, [], 'frames')

    # Check if we have pattern data
    pattern_data = None
    if args.patterns:
        # detect-patterns always writes 'patterns'/'references'; a wrong-stage
        # file here used to raise a raw KeyError below instead of this clear
        # message (#120).
        pattern_data = load_json_stage(args.patterns, ['patterns', 'references'], 'detect-patterns')

    # NOTE: `nsf` was removed from --format until the NSF exporter produces a
    # playable file (#81/EXP-05). The old `if args.format == "nsftxt"` branch
    # dispatched on a string argparse never allowed, so `--format nsf` silently
    # wrote nothing (#79). With `ca65` the only choice, argparse now rejects an
    # nsf request up front instead of no-oping; re-add the branch here when NSF
    # is real.
    if args.format == "ca65":
        # Always use CA65Exporter, with empty patterns if none provided
        if pattern_data:
            patterns = pattern_data['patterns']
            references = pattern_data['references']
        else:
            patterns = {}
            references = {}

        exporter = CA65Exporter()

        # Resolve --mapper BEFORE exporting when this is a direct (no
        # patterns) export -- a bank-switching-aware export (MMC1,
        # #255/MAP-2026-07-05-1) must know the target mapper up front to
        # bin-pack frame tables and emit bank-switches. An empty `patterns`
        # dict falls through to direct export the same way
        # export_tables_with_patterns itself dispatches on it, even if
        # --patterns was passed but yielded no patterns.
        mapper = None
        if not patterns:
            from mappers.factory import MapperFactory
            mapper_choice = get_mapper_choice(args)
            try:
                if mapper_choice == 'auto':
                    estimated_size = exporter.estimate_direct_export_size(frames)
                    mapper = MapperFactory.auto_select(estimated_size)
                else:
                    mapper = MapperFactory.get_mapper(mapper_choice)
                # Direct-export DPCM is MMC3-only: force MMC3 for 'auto', reject
                # an explicit non-MMC3 mapper (#281/#282).
                mapper = enforce_direct_export_dpcm_mapper(mapper, mapper_choice, frames)
            except ValueError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)

        exporter.export_tables_with_patterns(
            frames,
            patterns,
            references,
            args.output,
            standalone=False,  # Don't include header and vectors for project builder
            mapper=mapper
        )
            
        # Pack DPCM samples for exported ASM. Tracks any failure so it can be
        # surfaced prominently after the success line rather than buried above
        # it — a corrupt/partial dpcm_index.json (bad JSON, or an entry
        # missing 'id'/'filename') used to be swallowed by this broad except
        # and ship a silently drumless ASM with only an easy-to-miss warning
        # printed before the final status line (#123).
        dpcm_pack_warning = None
        try:
            from dpcm_sampler.dpcm_packer import DpcmPacker
            from dpcm_sampler.generate_dpcm_index import (
                load_dpcm_index_into_packer,
                get_dpcm_sample_ids_from_frames,
            )
            packer = DpcmPacker()
            dpcm_index_path = Path('dpcm_index.json')
            if dpcm_index_path.exists():
                with open(dpcm_index_path, 'r') as f:
                    dpcm_index = json.load(f)
                # Pack only the samples this song triggers, not the whole catalog (#140).
                # Pass the dict directly: an empty dict means "pack nothing" (no
                # DPCM in this song), not "pack everything". The dict shape
                # (dense_id -> catalog_id) also lets the packer key each entry
                # by its dense id instead of a potentially huge catalog id,
                # avoiding the note-byte collision two high catalog ids used
                # to hit (#200/D-14).
                sample_ids = get_dpcm_sample_ids_from_frames(frames)
                loaded_samples, _ = load_dpcm_index_into_packer(
                    packer, dpcm_index, dpcm_index_path, sample_ids=sample_ids)
                if loaded_samples == 0 and sample_ids:
                    dpcm_pack_warning = (
                        f"this song references {len(sample_ids)} DPCM sample(s) but none "
                        f"resolved to a file — the exported ASM has NO drums."
                    )
                with open(args.output, 'a') as f:
                    f.write("\n\n" + packer.generate_assembly())
        except Exception as e:
            dpcm_pack_warning = (
                f"DPCM packing failed ({e}) — the exported ASM has NO drums even "
                f"though dpcm_index.json may reference some."
            )

        print(f" Exported CA65 ASM -> {args.output}")
        if dpcm_pack_warning:
            print(f"   ⚠️  NO DRUMS: {dpcm_pack_warning}")

def run_detect_patterns(args):
    # Guard against a missing/corrupt file (#120); the frames JSON's channel
    # keys are all optional, so there is no fixed required key to validate.
    frames = load_json_stage(args.input, [], 'frames')

    # Sequential detector's event cap, optionally overridden by --config (#219).
    max_events, _ = get_pattern_detection_caps(getattr(args, 'config', None))

    # Create tempo map and pattern detector. tempo_map is a required
    # constructor arg but carries no real tempo-change data here (the events
    # below are already-quantized frame positions, not MIDI ticks), so its
    # per-pattern tempo analysis would only produce a discarded constant
    # result — skip it (analyze_tempo=False) rather than pay for it (#119).
    tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM default
    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH,
                                       max_pattern_length=PATTERN_MAX_LENGTH,
                                       max_events=max_events, analyze_tempo=False)

    # Extract events from frames structure (shared extractor skips the
    # dpcm_sample_map side table and returns them frame-sorted — #261).
    events = frames_to_events(frames)

    # This subcommand runs the sequential EnhancedPatternDetector, whose internal
    # cap is max_events (DETECTOR_MAX_EVENTS unless overridden). Sample uniformly
    # straight to that limit so the warning reports the count the detector
    # actually retains, instead of a larger figure the detector would silently
    # re-sample away (#100, #21).
    original_count = len(events)
    events, was_sampled = sample_events_for_detection(events, max_events)
    if was_sampled:
        print(f"⚠️  Large file ({original_count} events): sampled to {len(events)} "
              f"({len(events)/original_count*100:.1f}%, lossy) before pattern detection")

    # Detect patterns
    pattern_result = detector.detect_patterns(events)
    
    # Save compressed patterns
    output = {
        'patterns': pattern_result['patterns'],
        'references': pattern_result['references'],
        'stats': pattern_result['stats']
    }
    Path(args.output).write_text(json.dumps(output, separators=(',', ':')))
    print(f" Detected patterns -> {args.output}")
    # compression_ratio is a dedup ratio within the patterned subset only, not
    # a measure of the whole song (#169/PAT-03) -- the coverage line says what
    # fraction of the song that subset actually is.
    print(f" Pattern dedup ratio: {pattern_result['stats']['compression_ratio']:.1f}% "
          f"reduction (patterned subset only)")
    print(f" Pattern coverage: {pattern_result['stats']['coverage_ratio']:.1f}% of "
          f"{pattern_result['stats']['total_events']:,} events matched a detected pattern")

def run_song_add(args):
    """Add a song to the song bank"""
    bank = SongBank()

    # Load existing bank if specified. Guards a corrupt/malformed --bank file
    # (#220/SAFE-09) -- the same defect class SAFE-01/#120 fixed for the
    # pipeline subcommands, extended here to the song-bank family.
    if args.bank and Path(args.bank).exists():
        try:
            bank.import_bank(args.bank)
        except Exception as e:
            print(f"[ERROR] Failed to load song bank: {e}")
            sys.exit(1)

    # Prepare metadata
    metadata = {
        'composer': args.composer,
        'loop_point': args.loop_point,
        'tags': args.tags.split(',') if args.tags else [],
        'tempo_base': args.tempo
    }
    
    # Add song to bank
    bank.add_song_from_midi(args.input, args.name, metadata)
    
    # Save bank
    output_path = args.bank or 'song_bank.json'
    bank.export_bank(output_path)
    print(f"Song added to bank: {output_path}")

def run_song_list(args):
    """List songs in the song bank"""
    if not Path(args.bank).exists():
        print(f"Error: Song bank file not found: {args.bank}")
        return

    bank = SongBank()
    try:
        bank.import_bank(args.bank)
    except Exception as e:
        print(f"[ERROR] Failed to load song bank: {e}")
        sys.exit(1)

    print("\nSongs in bank:")
    print("-" * 50)
    for name, song_data in bank.songs.items():
        metadata = song_data['metadata']
        print(f"Title: {name}")
        if metadata.get('composer'):
            print(f"Composer: {metadata['composer']}")
        if metadata.get('tags'):
            print(f"Tags: {', '.join(metadata['tags'])}")
        if metadata.get('loop_point') is not None:
            print(f"Loop point: {metadata['loop_point']}")
        print(f"Bank: {song_data['bank']}")
        print("-" * 50)

def run_song_remove(args):
    """Remove a song from the bank"""
    if not Path(args.bank).exists():
        print(f"Error: Song bank file not found: {args.bank}")
        return

    bank = SongBank()
    try:
        bank.import_bank(args.bank)
    except Exception as e:
        print(f"[ERROR] Failed to load song bank: {e}")
        sys.exit(1)

    if args.name not in bank.songs:
        print(f"Error: Song '{args.name}' not found in bank")
        return
    
    del bank.songs[args.name]
    bank.export_bank(args.bank)
    print(f"Song '{args.name}' removed from bank")

def load_config(config_path: Optional[str] = None) -> DrumMapperConfig:
    """Load drum mapper configuration from file or use defaults"""
    if config_path and Path(config_path).exists():
        return DrumMapperConfig.from_file(config_path)
    return DrumMapperConfig()

def run_full_pipeline(args):
    """Run the complete MIDI to NES ROM pipeline"""
    input_midi = Path(args.input)
    if not input_midi.exists():
        print(f"[ERROR] Input MIDI file not found: {input_midi}")
        sys.exit(1)
    
    # Determine output ROM path
    if hasattr(args, 'output') and args.output:
        output_rom = Path(args.output)
    else:
        output_rom = input_midi.with_suffix('.nes')
    
    # Create backup if output ROM already exists
    backup_path = _backup_existing_rom(output_rom)
    
    # Check for no-patterns flag
    use_patterns = not (hasattr(args, 'no_patterns') and args.no_patterns)
    
    print(f"🎵 MIDI2NES Pipeline: {input_midi.name} → {output_rom.name}")
    if not use_patterns:
        print("   🔄 Direct export mode (no pattern compression)")
    print("=" * 60)
    
    # Create temporary directory for intermediate files
    build_succeeded = False
    with tempfile.TemporaryDirectory(prefix="midi2nes_") as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # Step 1: Parse MIDI to frames (using fast parser)
            print("[1/7] Parsing MIDI file...")
            from tracker.parser_fast import parse_midi_to_frames as parse_fast
            midi_data = parse_fast(str(input_midi))

            # Check for arranger mode
            use_arranger = hasattr(args, 'arranger') and args.arranger

            if use_arranger:
                # Step 2+3: Use intelligent arranger with arpeggiation
                print("[2/7] Analyzing musical structure...")
                print("[3/7] Arranging for NES with arpeggiation...")
                frames = arrange_for_nes(
                    midi_data["events"],
                    arp_speed=3,  # 20Hz arpeggiation (classic NES)
                    verbose=args.verbose
                )
            else:
                # Step 2: Map tracks to NES channels (legacy mode)
                print("[2/7] Mapping tracks to NES channels...")
                dpcm_index_path = 'dpcm_index.json'
                mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)

                # Step 3: Generate frame data
                print("[3/7] Generating NES frame data...")
                emulator = NESEmulatorCore()
                frames = emulator.process_all_tracks(mapped)
            
            # Step 4: Pattern detection or direct export
            # Tracks any lossy event sampling so the success banner can note that
            # compression stats are approximate (#176/PL-03). Sampling only feeds
            # pattern detection/compression metrics -- every emitted ROM byte
            # still derives from the full `frames` dict, so the ROM itself is
            # never incomplete because of this.
            pattern_loss_warning = None
            if use_patterns:
                print("[4/7] Detecting patterns for compression...")
                # Analysis-only tempo map (#98/TEMPO-06): the detector requires a
                # tempo_map constructor arg, but the events below are already
                # frame-indexed (tempo was applied upstream), so this map carries
                # no real tempo changes and the default ticks_per_beat is
                # irrelevant. ParallelPatternDetector never reads it, and the
                # sequential fallback below sets analyze_tempo=False, so it never
                # feeds frame timing -- do not derive timing from it. Mirrors the
                # documented construction in run_detect_patterns (#119).
                tempo_map = EnhancedTempoMap(initial_tempo=500000)

                # Convert frames to events for pattern detection (shared
                # extractor skips the dpcm_sample_map side table — #261).
                events = frames_to_events(frames)

                # Check if we should skip pattern detection for very large files
                LARGE_FILE_THRESHOLD = 10000
                if len(events) > LARGE_FILE_THRESHOLD:
                    print(f"  ⚠️  Large MIDI file ({len(events):,} events) detected")
                    print(f"  🚀 Proceeding with improved pattern detection...")

                # Sampling caps, optionally overridden by --config (#219).
                max_events, max_pattern_events = get_pattern_detection_caps(getattr(args, 'config', None))

                # Use parallel pattern detection with position mapping fix
                try:
                    from tracker.pattern_detector_parallel import ParallelPatternDetector
                    detector = ParallelPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH, max_pattern_length=PATTERN_MAX_LENGTH, max_pattern_events=max_pattern_events)
                    print(f"  Using parallel pattern detection with {len(events):,} events")
                    pattern_result = detector.detect_patterns(events)
                except Exception as e:
                    print(f"  Parallel detection failed, using fallback: {e}")
                    from tracker.pattern_detector import EnhancedPatternDetector
                    # tempo_map here has no real tempo-change data for the
                    # same reason as run_detect_patterns's fallback (#119).
                    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH, max_pattern_length=PATTERN_MAX_LENGTH, max_events=max_events, analyze_tempo=False)
                    # Sequential fallback can only handle the detector's internal
                    # cap, so sample uniformly straight to max_events. This
                    # keeps song structure (not a head cut) AND makes the warning
                    # below report the count actually retained, not a larger sample
                    # the detector would silently re-cut (#100).
                    fallback_count = len(events)
                    events, was_sampled = sample_events_for_detection(events, max_events)
                    if was_sampled:
                        pattern_loss_warning = (
                            f"pattern detection fell back to the sequential detector and "
                            f"sampled {fallback_count:,} events down to {len(events):,} for "
                            f"compression analysis only — compression stats are approximate; "
                            f"ROM content is unaffected (#176/PL-03)."
                        )
                        print(f"  ⚠️  NOTE: {pattern_loss_warning}")
                    pattern_result = detector.detect_patterns(events)
            else:
                print("[4/7] Skipping pattern detection (direct export mode)...")
                print(f"  📊 Processing direct frame export for complete data preservation")
                # Create dummy pattern result for direct export. The stats must
                # use the SAME schema the detectors emit (original_size /
                # compressed_size / compression_ratio / unique_patterns /
                # total_events / patterned_events / coverage_ratio) so any
                # consumer sees one shape regardless of path (#104). Direct export
                # applies no pattern compression, so ratio is 0% reduction (#17)
                # and coverage is 0% -- nothing is patterned (#169/PAT-03).
                direct_size = sum(len(ch) for ch in frames.values())
                pattern_result = {
                    'patterns': {},
                    'references': {},
                    'stats': {
                        'original_size': direct_size,
                        'compressed_size': direct_size,
                        'compression_ratio': 0,
                        'unique_patterns': 0,
                        'total_events': direct_size,
                        'patterned_events': 0,
                        'coverage_ratio': 0
                    },
                    # Match the 4-key top-level envelope both detectors emit so a
                    # consumer doing pattern_result['variations'] can't KeyError
                    # only on the --no-patterns path (#258/PAT-09).
                    'variations': {}
                }
                events = []  # Not needed for direct export
            
            # Step 5: Export to CA65 assembly
            print("[5/7] Exporting to CA65 assembly...")
            music_asm = temp_path / "music.asm"
            exporter = CA65Exporter()

            # Resolve --mapper BEFORE exporting for a direct (no-patterns)
            # build: a bank-switching-aware export (MMC1, #255/MAP-2026-07-05-1)
            # must know the target mapper up front to bin-pack frame tables and
            # emit bank-switches, unlike the bytecode/pattern path below (always
            # forced to MMC3, which does its own bank-switching internally, so
            # resolving it later at Step 6 -- as before -- is fine there).
            mapper = None
            if not use_patterns:
                from mappers.factory import MapperFactory
                mapper_choice = get_mapper_choice(args)
                try:
                    if mapper_choice == 'auto':
                        estimated_size = exporter.estimate_direct_export_size(frames)
                        mapper = MapperFactory.auto_select(estimated_size)
                    else:
                        mapper = MapperFactory.get_mapper(mapper_choice)
                    # Direct-export DPCM is MMC3-only: force MMC3 for 'auto',
                    # reject an explicit non-MMC3 mapper (#281/#282).
                    mapper = enforce_direct_export_dpcm_mapper(mapper, mapper_choice, frames)
                except ValueError as e:
                    print(f"[ERROR] {e}")
                    sys.exit(1)

            # The CA65 exporter emits every byte from `frames`; the detector's
            # pattern `references` are analysis/metrics only and are never read by
            # export_tables_with_patterns (#4). `patterns` truthiness merely
            # selects the macro-bytecode serializer over direct export, so pass an
            # empty references dict rather than building a table nothing consumes.
            exporter.export_tables_with_patterns(
                frames,
                pattern_result['patterns'],
                {},
                str(music_asm),
                standalone=False,  # We'll create our own project structure
                mapper=mapper
            )
            
            # Step 5.5: Pack DPCM samples. Tracks any failure so the success
            # banner can warn the ROM has no drums, rather than reporting silent
            # loss (#123) — a corrupt/partial dpcm_index.json (bad JSON, or an
            # entry missing 'id'/'filename') used to be swallowed by this broad
            # except with only a warning line that scrolled out of view.
            print("[5.5/7] Packing DPCM samples...")
            dpcm_pack_warning = None
            try:
                from dpcm_sampler.dpcm_packer import DpcmPacker
                from dpcm_sampler.generate_dpcm_index import (
                    load_dpcm_index_into_packer,
                    get_dpcm_sample_ids_from_frames,
                )
                packer = DpcmPacker()
                dpcm_index_path = Path('dpcm_index.json')

                if dpcm_index_path.exists():
                    with open(dpcm_index_path, 'r') as f:
                        dpcm_index = json.load(f)

                    # Pack only the samples this song triggers (#140), truncating
                    # oversized ones (#68), in ascending id order so they align
                    # with the engine's positional tables. An empty dict means
                    # "pack nothing", so pass it through directly (not `or None`).
                    # The dense_id -> catalog_id dict shape also lets the packer
                    # key each entry by its (small) dense id rather than a
                    # potentially huge catalog id (#200/D-14).
                    sample_ids = get_dpcm_sample_ids_from_frames(frames)
                    loaded_samples, _ = load_dpcm_index_into_packer(
                        packer, dpcm_index, dpcm_index_path, verbose=args.verbose,
                        sample_ids=sample_ids
                    )

                    # Generate the lookup tables and binary includes, append to music.asm
                    dpcm_asm = packer.generate_assembly()
                    with open(music_asm, 'a') as f:
                        f.write("\n\n" + dpcm_asm)

                    if loaded_samples > 0:
                        print(f"  ✓ Packed {loaded_samples} DPCM samples across {len(packer.banks)} banks")
                    elif sample_ids:
                        dpcm_pack_warning = (
                            f"this song references {len(sample_ids)} DPCM sample(s) but none "
                            f"resolved to a file — the ROM has NO drums."
                        )
                        print(f"  ⚠️ Warning: {dpcm_pack_warning}")
                    else:
                        print("  ℹ️ No DPCM samples referenced by this song.")
                else:
                    print("  ℹ️ No dpcm_index.json found, skipping DPCM packing.")
            except Exception as e:
                dpcm_pack_warning = (
                    f"DPCM packing failed ({e}) — the ROM has NO drums even though "
                    f"dpcm_index.json may reference some."
                )
                print(f"  ⚠️ Warning: Failed to pack DPCM samples: {str(e)}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()

            # Step 6: Prepare NES project
            print("[6/7] Preparing NES project...")
            project_path = temp_path / "nes_project"

            # Enable debug mode if requested
            debug_mode = hasattr(args, 'debug') and args.debug

            # --mapper (#217/MAP-6): 'auto' picks the smallest mapper that fits
            # this song's data via MapperFactory.auto_select(), previously
            # reachable only from tests/test_mappers.py. Defaults to mmc3,
            # matching prior hardcoded behavior for callers who don't pass
            # --mapper. Already resolved above for a direct-export build
            # (#255/MAP-2026-07-05-1); only the bytecode/pattern path (always
            # forced to MMC3) still resolves here, after export.
            if mapper is None:
                try:
                    mapper = resolve_mapper(get_mapper_choice(args), str(music_asm))
                except ValueError as e:
                    print(f"[ERROR] {e}")
                    sys.exit(1)

            # Capacity pre-flight (#11): catch an oversized song with a clear
            # message before ld65 reports a raw region overflow.
            try:
                data_size = check_mapper_capacity(str(music_asm), mapper)
                print(f"  ✓ Music data {data_size:,} bytes fits the {mapper.name} PRG regions")
            except ValueError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)

            builder = NESProjectBuilder(str(project_path), debug_mode=debug_mode, mapper=mapper)

            if not builder.prepare_project(str(music_asm)):
                print("[ERROR] Failed to prepare NES project")
                sys.exit(1)
            
            # Step 7: Compile ROM
            print("[7/7] Compiling NES ROM...")
            if not compile_rom(project_path, output_rom, verbose=args.verbose, mapper=mapper):
                print("[ERROR] ROM compilation failed")
                sys.exit(1)  # finally handles restore

            # Step 8: Validate ROM — shared with the `compile` subcommand (#15)
            # so step-by-step ROMs get the same boot-fatal gate (#6).
            skip_validation = hasattr(args, 'skip_validation') and args.skip_validation
            if not skip_validation:
                print("[8/8] Validating ROM...")
                if not validate_rom(output_rom):
                    sys.exit(1)  # finally handles restore

            # Success!
            rom_size = output_rom.stat().st_size
            print("\n" + "=" * 60)
            print(f"✅ SUCCESS! ROM created: {output_rom.name}")
            print(f"   ROM size: {rom_size:,} bytes ({rom_size / 1024:.1f} KB)")
            # compression_ratio is a pattern-analysis metric over the patterned
            # subset only, unrelated to the ROM size above (actual size
            # reduction comes from macro/instrument dedup in the bytecode
            # serializer, #4) -- labeled and paired with a coverage line so it
            # isn't misread as describing this ROM (#169/PAT-03).
            print(f"   Pattern dedup ratio: {pattern_result['stats']['compression_ratio']:.1f}% "
                  f"reduction (patterned subset only, pattern-analysis metric)")
            print(f"   Pattern coverage: {pattern_result['stats']['coverage_ratio']:.1f}% of "
                  f"{pattern_result['stats']['total_events']:,} events matched a detected pattern")
            print(f"   Total patterns detected: {len(pattern_result['patterns'])}")
            if pattern_loss_warning:
                print(f"\n   ⚠️  {pattern_loss_warning}")
            if dpcm_pack_warning:
                print(f"\n   ⚠️  NO DRUMS: {dpcm_pack_warning}")
            print("\n🎮 Your NES ROM is ready to run on emulators or flash carts!")

            # The new ROM is final and validated; mark success so the finally
            # block does not attempt a restore, then drop the now-redundant backup.
            build_succeeded = True
            if backup_path:
                backup_path.unlink(missing_ok=True)

        except Exception as e:
            print(f"\n[ERROR] Pipeline failed: {str(e)}")
            if args.verbose:
                import traceback
                print("\nFull traceback:")
                traceback.print_exc()
            sys.exit(1)

        finally:
            # Single restore point that covers every failure path after backup
            # creation: compile failure, prepare failure, top-level exception (#26).
            if not build_succeeded:
                _restore_backup(output_rom, backup_path)

def main():
    parser = argparse.ArgumentParser(
        description=f"MIDI to NES ROM compiler v{__version__}\n\nDefault usage: midi2nes song.mid [output.nes]",
        epilog="For more information, visit: https://github.com/matiaszanolli/midi2nes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--version', action='version', version=f'MIDI2NES {__version__}')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug overlay in ROM (shows APU status, frame counter, errors on screen)')
    parser.add_argument('--arranger', '-a', action='store_true', help='Use intelligent arranger with arpeggiation for polyphonic content (default pipeline only; no subcommand equivalent yet)')
    
    subparsers = parser.add_subparsers(dest='command', help='Advanced commands (optional - default is MIDI to ROM conversion)')

    # Existing subcommands
    p_parse = subparsers.add_parser('parse', help='Parse MIDI to intermediate JSON')
    p_parse.add_argument('input')
    p_parse.add_argument('output')
    p_parse.set_defaults(func=run_parse)

    # Update map command with new configuration options
    p_map = subparsers.add_parser('map', help='Map parsed MIDI to NES channels')
    p_map.add_argument('input')
    p_map.add_argument('output')
    # NOTE: drum-mapper --config is not consumed by assign_tracks_to_nes_channels,
    # so it was dropped here rather than left as a silently-ignored flag (#13).
    p_map.add_argument('--dpcm-index', help='Path to DPCM sample index')
    p_map.set_defaults(func=run_map)

    # Add new configuration management commands
    p_config = subparsers.add_parser('config', help='Configuration management')
    config_subparsers = p_config.add_subparsers(dest='config_command')

    # Generate default config
    p_config_init = config_subparsers.add_parser('init', 
                                                help='Generate default configuration')
    p_config_init.add_argument('output', help='Output configuration file path')
    p_config_init.set_defaults(func=run_config_init)

    # Validate config
    p_config_validate = config_subparsers.add_parser('validate', 
                                                    help='Validate configuration file')
    p_config_validate.add_argument('config', help='Configuration file to validate')
    p_config_validate.set_defaults(func=run_config_validate)

    # Keep existing commands
    p_frames = subparsers.add_parser('frames', help='Generate frame data from mapped tracks')
    p_frames.add_argument('input')
    p_frames.add_argument('output')
    p_frames.set_defaults(func=run_frames)

    p_patterns = subparsers.add_parser('detect-patterns',
                                      help='Detect and compress patterns in frame data')
    p_patterns.add_argument('input')
    p_patterns.add_argument('output')
    # NOTE: --config here only overrides processing.pattern_detection.max_events
    # (the sequential detector's sampling cap, #219) — it still does NOT touch
    # the tempo or PATTERN_MIN/MAX_LENGTH, which stay hardcoded. Same scoped
    # treatment as map --config (#13, #109): only wire what is actually consumed.
    p_patterns.add_argument('--config', help='Path to YAML config overriding pattern-detection sampling caps')
    p_patterns.set_defaults(func=run_detect_patterns)

    p_export = subparsers.add_parser('export', help='Export NES-ready files (ca65/FamiTracker)')
    p_export.add_argument('input')
    p_export.add_argument('output')
    # `nsf` is intentionally absent until the NSF exporter is playable (#79/#81);
    # offering it made `--format nsf` a silent no-op rather than a real export.
    p_export.add_argument('--format', choices=['ca65'], default='ca65')
    p_export.add_argument('--patterns', help='Path to pattern data JSON (optional)')
    p_export.add_argument('--mapper', choices=['auto', 'nrom', 'mmc1', 'mmc3'], default='mmc3',
                           help="NES mapper this export targets (must match the mapper "
                                "later passed to `prepare`); only affects direct (no "
                                "patterns) exports. Default: mmc3")
    p_export.set_defaults(func=run_export)

    # Keep other existing commands...
    p_prepare = subparsers.add_parser('prepare', help='Prepare CA65 project for compilation')
    p_prepare.add_argument('input', help='Input music.asm file')
    p_prepare.add_argument('output', help='Output project directory')
    p_prepare.add_argument('--mapper', choices=['auto', 'nrom', 'mmc1', 'mmc3'], default='mmc3',
                            help="NES mapper to target. 'auto' picks the smallest mapper "
                                 "that fits this song's data (default: mmc3)")
    p_prepare.set_defaults(func=run_prepare)

    # `compile` gives the step-by-step path the same compile + validation gate as
    # the full pipeline, instead of stopping at `prepare` (#15).
    p_compile = subparsers.add_parser('compile', help='Compile a prepared NES project to a ROM and validate it')
    p_compile.add_argument('input', help='Prepared NES project directory')
    p_compile.add_argument('output', help='Output .nes ROM path')
    p_compile.add_argument('--mapper', choices=['nrom', 'mmc1', 'mmc3'], default='mmc3',
                            help='NES mapper the project directory was prepared with '
                                 '(must match `prepare --mapper`; default: mmc3)')
    p_compile.add_argument('--skip-validation', action='store_true', help='Skip post-compile ROM validation')
    p_compile.add_argument('--verbose', '-v', action='store_true', help='Verbose validation output')
    p_compile.set_defaults(func=run_compile)

    # Song bank management commands
    p_song = subparsers.add_parser(
        'song',
        help='Song bank management (JSON storage/analysis only; not compiled to ROM)'
    )
    song_subparsers = p_song.add_subparsers(dest='song_command')

    p_song_add = song_subparsers.add_parser('add', help='Add song to bank')
    p_song_add.add_argument('input', help='Input MIDI file')
    p_song_add.add_argument('--bank', help='Song bank file (creates new if not exists)')
    p_song_add.add_argument('--name', help='Song name (defaults to filename)')
    p_song_add.add_argument('--composer', help='Song composer')
    p_song_add.add_argument('--loop-point', type=int, help='Loop point in frames')
    p_song_add.add_argument('--tags', help='Comma-separated tags')
    p_song_add.add_argument('--tempo', type=int, default=120, help='Base tempo (default: 120)')
    # NOTE: song-add --config was not consumed by run_song_add, so it was dropped
    # rather than left as a silently-ignored flag — same treatment as map --config
    # (#13, #109).
    p_song_add.set_defaults(func=run_song_add)

    p_song_list = song_subparsers.add_parser('list', help='List songs in bank')
    p_song_list.add_argument('bank', help='Song bank file')
    p_song_list.set_defaults(func=run_song_list)

    p_song_remove = song_subparsers.add_parser('remove', help='Remove song from bank')
    p_song_remove.add_argument('bank', help='Song bank file')
    p_song_remove.add_argument('name', help='Song name to remove')
    p_song_remove.set_defaults(func=run_song_remove)

    # Add benchmark command
    p_benchmark = subparsers.add_parser('benchmark', help='Performance benchmarking')
    benchmark_subparsers = p_benchmark.add_subparsers(dest='benchmark_command')
    
    # Run benchmark
    p_benchmark_run = benchmark_subparsers.add_parser('run', help='Run performance benchmark')
    p_benchmark_run.add_argument('files', nargs='*', help='MIDI files to benchmark (optional)')
    p_benchmark_run.add_argument('--output', default='benchmark_results', help='Output directory')
    p_benchmark_run.add_argument('--memory', action='store_true', help='Enable detailed memory profiling')
    p_benchmark_run.set_defaults(func=run_benchmark)
    
    # Memory usage command
    p_benchmark_memory = benchmark_subparsers.add_parser('memory', help='Show current memory usage')
    p_benchmark_memory.set_defaults(func=run_benchmark_memory)

    # Custom argument parsing to handle default behavior
    import sys
    
    # Check if first argument (if any) is a subcommand
    subcommands = ['parse', 'map', 'config', 'frames', 'detect-patterns', 'export', 'prepare', 'compile', 'song', 'benchmark']
    
    # Handle special cases first
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    if len(sys.argv) == 2 and sys.argv[1] in ['--help', '-h']:
        parser.print_help()
        sys.exit(0)
    
    if len(sys.argv) == 2 and sys.argv[1] in ['--version']:
        parser.parse_args(sys.argv[1:])
        return
    
    # Check if first non-option argument is a subcommand
    first_arg = None
    for arg in sys.argv[1:]:
        if not arg.startswith('-'):
            first_arg = arg
            break
    
    if first_arg in subcommands:
        # --arranger is declared on the top-level parser, so argparse happily
        # accepts it before a subcommand -- but no subcommand reads args.arranger,
        # so it would be silently discarded and the step-by-step chain would
        # produce the legacy (non-arranger) song with zero diagnostics (#174).
        pre_subcommand_args = sys.argv[1:sys.argv.index(first_arg)]
        if '--arranger' in pre_subcommand_args or '-a' in pre_subcommand_args:
            print("Error: --arranger only applies to the default MIDI-to-ROM pipeline; "
                  "there is no step-by-step equivalent yet.", file=sys.stderr)
            print(f"Run 'midi2nes --arranger song.mid' instead, or drop --arranger before '{first_arg}'.",
                  file=sys.stderr)
            sys.exit(2)
        # It's a subcommand, parse normally
        args = parser.parse_args()
        if hasattr(args, 'func'):
            args.func(args)
        else:
            parser.print_help()
    else:
        # It's the default MIDI-to-ROM behavior
        # Parse global options first
        global_args = []
        remaining_args = []
        
        i = 1
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg in ['--verbose', '-v']:
                global_args.extend([arg])
                i += 1
            elif arg in ['--debug', '-d']:
                global_args.extend([arg])
                i += 1
            elif arg in ['--arranger', '-a']:
                global_args.extend([arg])
                i += 1
            elif arg == '--version':
                # Match argparse's action='version' behavior: print and exit
                # immediately regardless of any other arguments present, rather
                # than filing this into global_args where nothing consumed it
                # and a full pipeline run happened instead (#179/PL-06).
                print(f"MIDI2NES {__version__}")
                sys.exit(0)
            elif arg == '--no-patterns':
                global_args.extend([arg])
                i += 1
            elif arg == '--skip-validation':
                global_args.extend([arg])
                i += 1
            elif arg == '--config':
                if i + 1 >= len(sys.argv):
                    print("Error: --config requires a path argument", file=sys.stderr)
                    sys.exit(2)
                global_args.extend([arg, sys.argv[i + 1]])
                i += 2
            elif arg == '--mapper':
                if i + 1 >= len(sys.argv) or sys.argv[i + 1] not in ('auto', 'nrom', 'mmc1', 'mmc3'):
                    print("Error: --mapper requires one of: auto, nrom, mmc1, mmc3", file=sys.stderr)
                    sys.exit(2)
                global_args.extend([arg, sys.argv[i + 1]])
                i += 2
            elif arg.startswith('-'):
                # Reject unknown/typo flags instead of silently dropping them —
                # a swallowed --no-patterns/--arranger produces a different ROM (#8).
                print(f"Error: Unknown option: {arg}", file=sys.stderr)
                print("Run 'midi2nes --help' for available options.", file=sys.stderr)
                sys.exit(2)
            else:
                remaining_args.append(arg)
                i += 1

        if not remaining_args:
            print("Error: Please provide an input MIDI file")
            print("\nUsage examples:")
            print("  midi2nes song.mid                  # Creates song.nes")
            print("  midi2nes song.mid output.nes       # Creates output.nes")
            print("  midi2nes --arranger song.mid       # Smart voice allocation + arpeggiation")
            print("  midi2nes --no-patterns song.mid    # Direct export (no compression)")
            print("  midi2nes --debug song.mid          # Debug ROM (shows APU status on screen)")
            print("  midi2nes --skip-validation song.mid # Skip ROM validation after compilation")
            print("  midi2nes --config cfg.yaml song.mid # Override pattern-detection sampling caps")
            print("  midi2nes --mapper auto song.mid    # Auto-select the smallest mapper that fits")
            print("  midi2nes --help                    # Show full help")
            sys.exit(1)

        # Create a simple args object for the default pipeline
        class SimpleArgs:
            def __init__(self):
                self.input = remaining_args[0] if remaining_args else None
                self.output = remaining_args[1] if len(remaining_args) > 1 else None
                self.verbose = '--verbose' in global_args or '-v' in global_args
                self.no_patterns = '--no-patterns' in global_args
                self.debug = '--debug' in global_args or '-d' in global_args
                self.arranger = '--arranger' in global_args or '-a' in global_args
                self.skip_validation = '--skip-validation' in global_args
                self.config = (global_args[global_args.index('--config') + 1]
                              if '--config' in global_args else None)
                self.mapper = (global_args[global_args.index('--mapper') + 1]
                              if '--mapper' in global_args else 'mmc3')
                self.command = None

        args = SimpleArgs()
        run_full_pipeline(args)

def run_config_init(args):
    """Generate default configuration file"""
    try:
        config_manager = ConfigManager()
        config_manager.copy_default_config_to(args.output)
        print(f"[OK] Generated default configuration -> {args.output}")
        print(f"     Edit this file to customize MIDI2NES behavior")
    except Exception as e:
        print(f"[ERROR] Failed to generate configuration: {str(e)}")
        sys.exit(1)

def run_config_validate(args):
    """Validate configuration file"""
    try:
        config_manager = ConfigManager(args.config)
        config_manager.validate()
        print(f"[OK] Configuration file is valid: {args.config}")
        
        # Show some key settings
        if hasattr(args, 'verbose') and args.verbose:
            print("\nConfiguration summary:")
            print(f"  Pattern detection min length: {config_manager.get('processing.pattern_detection.min_length')}")
            print(f"  Memory limit: {config_manager.get('performance.max_memory_mb')} MB")
            print(f"  NSF load address: 0x{config_manager.get('export.nsf.load_address'):04X}")
            
    except Exception as e:
        print(f"[ERROR] Configuration validation failed: {str(e)}")
        sys.exit(1)

def run_benchmark(args):
    """Run performance benchmarks"""
    benchmark = PerformanceBenchmark()
    
    # Set up test files
    test_files = []
    if args.files:
        for file_pattern in args.files:
            file_path = Path(file_pattern)
            if file_path.is_file():
                test_files.append(str(file_path))
            elif file_path.is_dir():
                # Find MIDI files in directory
                midi_files = list(file_path.glob('*.mid')) + list(file_path.glob('*.midi'))
                test_files.extend([str(f) for f in midi_files])
            else:
                print(f"Warning: {file_pattern} not found")
    
    if not test_files:
        print("No test files specified. Using built-in test data.")
        # Generate some test data
        test_files = None
    
    try:
        # Create output directory
        output_dir = Path(args.output)
        output_dir.mkdir(exist_ok=True)
        
        # Run the benchmarks
        print(f"Running performance benchmarks...")
        if args.memory:
            print("Memory profiling enabled")
            
        if test_files:
            # Run benchmarks on provided files
            results = {}
            for midi_file in test_files:
                print(f"Running pipeline benchmark on: {midi_file}")
                try:
                    result = benchmark.run_full_pipeline(midi_file)
                    results[Path(midi_file).name] = {
                        'file_path': result.file_path,
                        'file_size_kb': result.file_size_kb,
                        'execution_time': result.total_duration_ms / 1000,  # Convert to seconds
                        'memory_peak': result.total_memory_mb,
                        'stages': [{stage.stage: {'duration_ms': stage.duration_ms, 'success': stage.success}} for stage in result.stages],
                        'midi_info': result.midi_info
                    }
                    if result.midi_info.get('total_events', 0) > 0:
                        results[Path(midi_file).name]['throughput'] = result.midi_info['total_events'] / (result.total_duration_ms / 1000)
                except Exception as e:
                    print(f"  Failed to benchmark {midi_file}: {str(e)}")
                    results[Path(midi_file).name] = {'error': str(e)}
        else:
            print("Running synthetic benchmark tests...")
            # Create simple synthetic test
            results = {
                'synthetic_test': {
                    'execution_time': 0.001,
                    'memory_peak': 10.0,
                    'note': 'Synthetic test - no actual MIDI files provided'
                }
            }
        
        # Save results to JSON
        results_file = output_dir / "benchmark_results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        # Print summary
        print(f"\n[OK] Benchmark completed -> {results_file}")
        print("\nBenchmark Summary:")
        print("-" * 50)
        
        for test_name, result in results.items():
            if isinstance(result, dict) and 'execution_time' in result:
                print(f"{test_name}: {result['execution_time']:.3f}s")
                if 'memory_peak' in result:
                    print(f"  Peak memory: {result['memory_peak']:.2f} MB")
                if 'throughput' in result:
                    print(f"  Throughput: {result['throughput']:.1f} events/sec")
        
    except Exception as e:
        print(f"[ERROR] Benchmark failed: {str(e)}")
        sys.exit(1)

def run_benchmark_memory(args):
    """Show current memory usage"""
    try:
        memory_info = get_memory_usage()
        log_memory_usage("Current Memory Usage")
        
        print("Memory Usage Report:")
        print("-" * 30)
        for key, value in memory_info.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f} MB")
            else:
                print(f"{key}: {value}")
                
    except Exception as e:
        print(f"[ERROR] Memory profiling failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
