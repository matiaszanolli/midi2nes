# New file: exporter/compression.py

import json
from typing import List, Dict, Tuple, Any

class CompressionEngine:
    """Engine for compressing NES music pattern data using RLE and delta compression"""
    
    def __init__(self):
        self.min_rle_length = 2  # Minimum repetitions for RLE compression
        self.min_delta_length = 3  # Minimum sequence length for delta compression
    
    def compress_pattern(self, pattern: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Compress a pattern using RLE and delta compression
        
        Args:
            pattern: List of note/event dictionaries
            
        Returns:
            Tuple of (compressed_data, metadata)
        """
        if not pattern:
            return [], {'rle_blocks': [], 'delta_blocks': []}
        
        if len(pattern) == 1:
            return pattern, {'rle_blocks': [], 'delta_blocks': []}
        
        compressed = []
        metadata = {'rle_blocks': [], 'delta_blocks': []}
        i = 0
        
        while i < len(pattern):
            # Try RLE compression first
            rle_length = self._find_rle_sequence(pattern, i)
            if rle_length >= self.min_rle_length:
                # Add RLE block
                start_idx = len(compressed)
                compressed.append({
                    '_type': 'rle',
                    'data': pattern[i],
                    'count': rle_length
                })
                metadata['rle_blocks'].append((start_idx, rle_length))
                i += rle_length
                continue
            
            # Try delta compression
            delta_length = self._find_delta_sequence(pattern, i)
            if delta_length >= self.min_delta_length:
                # Add delta block
                start_idx = len(compressed)
                delta_data = self._create_delta_block(pattern[i:i+delta_length])
                compressed.append({
                    '_type': 'delta',
                    'start': pattern[i],
                    'deltas': delta_data
                })
                metadata['delta_blocks'].append((start_idx, delta_length))
                i += delta_length
                continue
            
            # No compression, store raw event
            compressed.append(pattern[i])
            i += 1
        
        return compressed, metadata
    
    def decompress_pattern(self, compressed: List[Dict[str, Any]], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Decompress a compressed pattern
        
        Args:
            compressed: Compressed pattern data
            metadata: Compression metadata
            
        Returns:
            Original uncompressed pattern
        """
        if not compressed:
            return []
        
        decompressed = []
        
        for item in compressed:
            if isinstance(item, dict) and item.get('_type') == 'rle':
                # Decompress RLE block
                for _ in range(item['count']):
                    event = item['data'].copy()
                    if '_type' in event:
                        del event['_type']
                    decompressed.append(event)
            elif isinstance(item, dict) and item.get('_type') == 'delta':
                # Decompress delta block
                current_event = item['start'].copy()
                if '_type' in current_event:
                    del current_event['_type']
                decompressed.append(current_event)
                
                for delta in item['deltas']:
                    current_event = current_event.copy()
                    for key, value in delta.items():
                        if key in current_event:
                            current_event[key] += value
                        else:
                            current_event[key] = value
                    decompressed.append(current_event)
            else:
                # Raw event
                event = item.copy() if isinstance(item, dict) else item
                if isinstance(event, dict) and '_type' in event:
                    del event['_type']
                decompressed.append(event)
        
        return decompressed
    
    def _find_rle_sequence(self, pattern: List[Dict[str, Any]], start: int) -> int:
        """Find length of repeating sequence starting at start index"""
        if start >= len(pattern):
            return 0
        
        base_event = pattern[start]
        count = 1
        
        for i in range(start + 1, len(pattern)):
            if self._events_equal(pattern[i], base_event):
                count += 1
            else:
                break
        
        return count
    
    def _find_delta_sequence(self, pattern: List[Dict[str, Any]], start: int) -> int:
        """Find length of sequence that can be delta compressed"""
        if start + 2 >= len(pattern):
            return 0
        
        # Check if we have a sequence where notes change by consistent amounts
        count = 1
        prev_event = pattern[start]
        
        for i in range(start + 1, len(pattern)):
            current_event = pattern[i]
            
            # Check if this can be part of a delta sequence
            if self._can_delta_compress(prev_event, current_event):
                count += 1
                prev_event = current_event
            else:
                break
        
        return count if count >= self.min_delta_length else 0
    
    def _can_delta_compress(self, prev_event: Dict[str, Any], current_event: Dict[str, Any]) -> bool:
        """Check if two events can be delta compressed"""
        # Both events must have the same keys (except for numeric values that can be delta'd)
        numeric_keys = {'note', 'volume', 'sample_id'}
        
        for key in prev_event:
            if key not in current_event:
                return False
            if key not in numeric_keys and prev_event[key] != current_event[key]:
                return False
        
        for key in current_event:
            if key not in prev_event:
                return False
        
        # Must have at least one numeric change
        has_numeric_change = False
        for key in numeric_keys:
            if key in prev_event and key in current_event:
                if prev_event[key] != current_event[key]:
                    has_numeric_change = True
                    break
        
        return has_numeric_change
    
    def _create_delta_block(self, sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create delta data for a sequence"""
        if len(sequence) < 2:
            return []
        
        deltas = []
        numeric_keys = {'note', 'volume', 'sample_id'}
        
        for i in range(1, len(sequence)):
            prev_event = sequence[i-1]
            current_event = sequence[i]
            
            delta = {}
            for key in numeric_keys:
                if key in prev_event and key in current_event:
                    diff = current_event[key] - prev_event[key]
                    if diff != 0:
                        delta[key] = diff
            
            deltas.append(delta)
        
        return deltas
    
    def _events_equal(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> bool:
        """Check if two events are equal (ignoring _type field)"""
        # Create copies without _type field for comparison
        e1 = {k: v for k, v in event1.items() if k != '_type'}
        e2 = {k: v for k, v in event2.items() if k != '_type'}
        return e1 == e2
    
    def compress_song_bank(self, bank_data: Dict[str, Any]) -> bytes:
        """Compress entire song bank data"""
        compressed_songs = {}
        
        for song_name, song_data in bank_data.items():
            if 'patterns' in song_data:
                compressed_patterns = {}
                for pattern_name, pattern in song_data['patterns'].items():
                    compressed_data, metadata = self.compress_pattern(pattern)
                    compressed_patterns[pattern_name] = {
                        'data': compressed_data,
                        'metadata': metadata
                    }
                
                compressed_songs[song_name] = {
                    **song_data,
                    'patterns': compressed_patterns
                }
            else:
                compressed_songs[song_name] = song_data
        
        return json.dumps(compressed_songs).encode('utf-8')
    
    def decompress_song_bank(self, compressed_data: bytes) -> Dict[str, Any]:
        """Decompress song bank data"""
        bank_data = json.loads(compressed_data.decode('utf-8'))
        
        for song_name, song_data in bank_data.items():
            if 'patterns' in song_data:
                decompressed_patterns = {}
                for pattern_name, pattern_info in song_data['patterns'].items():
                    if isinstance(pattern_info, dict) and 'data' in pattern_info:
                        decompressed = self.decompress_pattern(
                            pattern_info['data'], 
                            pattern_info['metadata']
                        )
                        decompressed_patterns[pattern_name] = decompressed
                    else:
                        decompressed_patterns[pattern_name] = pattern_info
                
                bank_data[song_name] = {
                    **song_data,
                    'patterns': decompressed_patterns
                }
        
        return bank_data
