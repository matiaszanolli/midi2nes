import argparse
import sys
import json
from typing import Dict, Optional
from pathlib import Path
from tracker.parser import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore
from nes.project_builder import NESProjectBuilder
from nes.song_bank import SongBank
from exporter.exporter_nsf import NSFExporter
from exporter.exporter_ca65 import CA65Exporter
from exporter.exporter import generate_famitracker_txt_with_patterns
from tracker.pattern_detector import EnhancedPatternDetector
from tracker.tempo_map import EnhancedTempoMap
from dpcm_sampler.enhanced_drum_mapper import EnhancedDrumMapper, DrumMapperConfig

def run_parse(args):
    midi_data = parse_midi_to_frames(args.input)
    Path(args.output).write_text(json.dumps(midi_data, indent=2))
    print(f"[OK] Parsed MIDI -> {args.output}")

def run_map(args):
    midi_data = json.loads(Path(args.input).read_text())
    dpcm_index_path = 'dpcm_index.json'
    # Extract just the events from the parsed data
    mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
    Path(args.output).write_text(json.dumps(mapped, indent=2))
    print(f"[OK] Mapped tracks -> {args.output}")

def run_frames(args):
    mapped = json.loads(Path(args.input).read_text())
    emulator = NESEmulatorCore()
    frames = emulator.process_all_tracks(mapped)
    Path(args.output).write_text(json.dumps(frames, indent=2))
    print(f" Generated frames -> {args.output}")

def run_prepare(args):
    builder = NESProjectBuilder(args.output)
    if builder.prepare_project(args.input):
        print(f" Prepared NES project -> {args.output}")
        print(" Ready for CC65 compilation!")
        print(" To build:")
        print(f" 1. cd {args.output}")
        print(" 2. ./build.sh  (or build.bat on Windows)")

def run_export(args):
    """Export function supporting multiple formats with pattern compression"""
    frames = json.loads(Path(args.input).read_text())
    
    # Check if we have pattern data
    pattern_data = None
    if args.patterns:
        pattern_data = json.loads(Path(args.patterns).read_text())
    
    if args.format == "nsftxt":
        # Create NSF exporter instance
        exporter = NSFExporter()
        
        # Export with optional metadata
        exporter.export(
            frames_data=frames,
            output_path=args.output,
            song_name="MIDI2NES Export"  # You could add these as optional CLI arguments
        )
        print(f" Exported NSF -> {args.output}")
    
    elif args.format == "ca65":
        # Always use CA65Exporter, with empty patterns if none provided
        if pattern_data:
            patterns = pattern_data['patterns']
            references = pattern_data['references']
        else:
            patterns = {}
            references = {}
            
        exporter = CA65Exporter()
        exporter.export_tables_with_patterns(
            frames,
            patterns,
            references,
            args.output
        )
        print(f" Exported CA65 ASM -> {args.output}")

def run_detect_patterns(args):
    frames = json.loads(Path(args.input).read_text())
    
    # Create tempo map and pattern detector
    tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM default
    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3)
    
    # Extract events from frames structure
    events = []
    for channel_name, channel_frames in frames.items():
        for frame_num, frame_data in channel_frames.items():
            event = {
                'frame': int(frame_num),
                'note': frame_data.get('note', 0),
                'volume': frame_data.get('volume', 0)
            }
            events.append(event)
    
    # Sort events by frame number
    events.sort(key=lambda x: x['frame'])
    
    # Detect patterns
    pattern_result = detector.detect_patterns(events)
    
    # Save compressed patterns
    output = {
        'patterns': pattern_result['patterns'],
        'references': pattern_result['references'],
        'stats': pattern_result['stats']
    }
    Path(args.output).write_text(json.dumps(output, indent=2))
    print(f" Detected patterns -> {args.output}")
    print(f" Compression ratio: {pattern_result['stats']['compression_ratio']:.2f}")

def run_song_add(args):
    """Add a song to the song bank"""
    bank = SongBank()
    
    # Load existing bank if specified
    if args.bank and Path(args.bank).exists():
        bank.import_bank(args.bank)
    
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
    bank.import_bank(args.bank)
    
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
    bank.import_bank(args.bank)
    
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

def run_parse(args):
    midi_data = parse_midi_to_frames(args.input)
    Path(args.output).write_text(json.dumps(midi_data, indent=2))
    print(f"[OK] Parsed MIDI -> {args.output}")

def run_map(args):
    input_data = json.loads(Path(args.input).read_text())
    
    # Initialize drum mapper with configuration
    config = load_config(args.config)
    drum_mapper = EnhancedDrumMapper(
        dpcm_index_path=args.dpcm_index or 'samples/index.json',
        config=config
    )
    
    # Map tracks to NES channels with enhanced drum mapping
    mapped_data = assign_tracks_to_nes_channels(
        input_data,
        drum_mapper=drum_mapper,
        use_advanced_mapping=config.use_advanced_mapping
    )
    
    Path(args.output).write_text(json.dumps(mapped_data, indent=2))
    print(f"[OK] Mapped tracks -> {args.output}")

def main():
    parser = argparse.ArgumentParser(description="MIDI to NES compiler")
    subparsers = parser.add_subparsers(dest='command')

    # Existing subcommands
    p_parse = subparsers.add_parser('parse', help='Parse MIDI to intermediate JSON')
    p_parse.add_argument('input')
    p_parse.add_argument('output')
    p_parse.set_defaults(func=run_parse)

    # Update map command with new configuration options
    p_map = subparsers.add_parser('map', help='Map parsed MIDI to NES channels')
    p_map.add_argument('input')
    p_map.add_argument('output')
    p_map.add_argument('--config', help='Path to drum mapper configuration file')
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
    p_patterns.add_argument('--config', help='Path to pattern detection configuration')
    p_patterns.set_defaults(func=run_detect_patterns)

    p_export = subparsers.add_parser('export', help='Export NES-ready files (ca65/FamiTracker)')
    p_export.add_argument('input')
    p_export.add_argument('output')
    p_export.add_argument('--format', choices=['nsf', 'ca65'], default='ca65')
    p_export.add_argument('--patterns', help='Path to pattern data JSON (optional)')
    p_export.set_defaults(func=run_export)

    # Keep other existing commands...
    p_prepare = subparsers.add_parser('prepare', help='Prepare CA65 project for compilation')
    p_prepare.add_argument('input', help='Input music.asm file')
    p_prepare.add_argument('output', help='Output project directory')
    p_prepare.set_defaults(func=run_prepare)

    # Song bank management commands
    p_song = subparsers.add_parser('song', help='Song bank management')
    song_subparsers = p_song.add_subparsers(dest='song_command')

    p_song_add = song_subparsers.add_parser('add', help='Add song to bank')
    p_song_add.add_argument('input', help='Input MIDI file')
    p_song_add.add_argument('--bank', help='Song bank file (creates new if not exists)')
    p_song_add.add_argument('--name', help='Song name (defaults to filename)')
    p_song_add.add_argument('--composer', help='Song composer')
    p_song_add.add_argument('--loop-point', type=int, help='Loop point in frames')
    p_song_add.add_argument('--tags', help='Comma-separated tags')
    p_song_add.add_argument('--tempo', type=int, default=120, help='Base tempo (default: 120)')
    p_song_add.add_argument('--config', help='Path to drum mapper configuration')
    p_song_add.set_defaults(func=run_song_add)

    p_song_list = song_subparsers.add_parser('list', help='List songs in bank')
    p_song_list.add_argument('bank', help='Song bank file')
    p_song_list.set_defaults(func=run_song_list)

    p_song_remove = song_subparsers.add_parser('remove', help='Remove song from bank')
    p_song_remove.add_argument('bank', help='Song bank file')
    p_song_remove.add_argument('name', help='Song name to remove')
    p_song_remove.set_defaults(func=run_song_remove)

    args = parser.parse_args()

    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

def run_config_init(args):
    """Generate default configuration file"""
    config = DrumMapperConfig()
    config.to_file(args.output)
    print(f"[OK] Generated default configuration -> {args.output}")

def run_config_validate(args):
    """Validate configuration file"""
    try:
        config = DrumMapperConfig.from_file(args.config)
        config.validate()
        print(f"[OK] Configuration file is valid: {args.config}")
    except Exception as e:
        print(f"[ERROR] Configuration validation failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
