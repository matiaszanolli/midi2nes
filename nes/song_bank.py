# nes/song_bank.py

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from pathlib import Path
from tracker.parser import parse_midi_to_frames

@dataclass
class SongMetadata:
    title: str
    composer: Optional[str] = None
    order: int = 0
    loop_point: Optional[int] = None
    tags: List[str] = None
    tempo_base: int = 120

    def validate(self):
        """Validate metadata fields"""
        if self.tempo_base <= 0:
            raise ValueError(f"Invalid tempo_base: {self.tempo_base}")
        if self.loop_point is not None and self.loop_point < 0:
            raise ValueError(f"Invalid loop_point: {self.loop_point}")
        return True

class SongBank:
    def __init__(self):
        self.songs = {}
        self.current_bank = 0
        self.max_bank_size = 16384  # 16KB per bank
        self.total_banks = 8  # Default to 8 banks (128KB total)

    def calculate_bank_usage(self) -> Dict[int, int]:
        """Calculate current usage of banks in bytes"""
        usage = {}
        for song_data in self.songs.values():
            bank = song_data['bank']
            size = song_data['size']
            usage[bank] = usage.get(bank, 0) + size
        return usage

    def debug_size_info(self, segments: Dict) -> Dict:
        """Debug method to understand size calculations"""
        events_size = len(str(segments.get('events', {}))) * 2
        patterns_size = len(str(segments.get('patterns', {}))) * 2
        frames_size = len(segments.get('frames', [])) * 4
        total_size = events_size + patterns_size + frames_size
        
        return {
            'events_size': events_size,
            'patterns_size': patterns_size,
            'frames_size': frames_size,
            'total_size': total_size,
            'max_bank_size': self.max_bank_size,
            'fits_in_bank': total_size <= self.max_bank_size
        }

    def add_song_from_midi(self, midi_path: str, name: Optional[str] = None, 
                          metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a song to the bank from a MIDI file"""
        parsed_data = parse_midi_to_frames(midi_path)
        song_name = name or Path(midi_path).stem
        
        # Create metadata object
        meta = SongMetadata(
            title=song_name,
            composer=metadata.get('composer') if metadata else None,
            order=len(self.songs),
            loop_point=metadata.get('loop_point') if metadata else None,
            tags=metadata.get('tags', []) if metadata else [],
            tempo_base=metadata.get('tempo_base', 120) if metadata else 120
        )
        
        segments = self._process_segments(parsed_data)
        self.add_song(song_name, segments, vars(meta))

    def _process_segments(self, parsed_data: Dict) -> Dict:
        """Process parsed MIDI data into segments"""
        return {
            'events': parsed_data['events'],
            'patterns': parsed_data.get('patterns', {}),
            'frames': parsed_data.get('frames', [])
        }

    def add_song(self, name: str, segments: Dict, metadata: Optional[Dict] = None) -> None:
        """Add a song to the bank with its segments and metadata"""
        if name in self.songs:
            raise ValueError(f"Song '{name}' already exists in the bank")

        # Validate metadata
        meta = SongMetadata(
            title=name,
            composer=metadata.get('composer') if metadata else None,
            order=len(self.songs),
            loop_point=metadata.get('loop_point') if metadata else None,
            tags=metadata.get('tags', []) if metadata else [],
            tempo_base=metadata.get('tempo_base', 120) if metadata else 120
        )
        meta.validate()

        # Calculate size and bank assignment
        size = self._estimate_segment_size(segments)
        bank = self._calculate_bank_assignment(size)
        
        if bank >= self.total_banks:
            raise ValueError(f"Not enough bank space for song '{name}'")

        self.songs[name] = {
            'segments': segments,
            'metadata': vars(meta),
            'bank': bank,
            'size': size
        }

    def _calculate_bank_assignment(self, size: int) -> int:
        """Calculate which bank this song should go into based on size"""
        usage = self.calculate_bank_usage()
        
        for bank in range(self.total_banks):
            if usage.get(bank, 0) + size <= self.max_bank_size:
                return bank
        
        raise ValueError("No available bank space")

    def _estimate_segment_size(self, segments: Dict) -> int:
        """Estimate the size of segments in bytes"""
        # More realistic size estimation
        events = segments.get('events', [])
        patterns = segments.get('patterns', {})
        frames = segments.get('frames', [])
        
        # Event size: each event typically needs ~8 bytes (frame, note, velocity, command)
        events_size = len(events) * 8
        
        # Pattern size: each pattern entry needs ~4 bytes (pattern ID + length + data)
        patterns_size = sum(len(pattern) * 4 for pattern in patterns.values())
        
        # Frame size: each frame needs 4 bytes (state data)
        frames_size = len(frames) * 4
        
        # Add some overhead for metadata and structure
        overhead = 256
        
        return events_size + patterns_size + frames_size + overhead
    
    def get_song_data(self, name: str) -> Optional[Dict]:
        """Get all data for a specific song"""
        return self.songs.get(name)

    def export_bank(self, output_path: str) -> None:
        """Export the entire song bank to a file"""
        bank_data = {
            'version': '0.3.0',
            'bank_info': {
                'total_banks': self.total_banks,
                'bank_size': self.max_bank_size
            },
            'songs': self.songs
        }
        
        Path(output_path).write_text(json.dumps(bank_data, indent=2))

    def import_bank(self, input_path: str) -> None:
        """Import a song bank from a file"""
        data = json.loads(Path(input_path).read_text())
        self.total_banks = data['bank_info']['total_banks']
        self.max_bank_size = data['bank_info']['bank_size']
        self.songs = data['songs']
