# pattern_exporter.py

from collections import defaultdict
from typing import Dict, List, Tuple, Any

class PatternExporter:
    def __init__(self, compressed_data: Dict[str, Any], pattern_refs: Dict[str, List[int]]):
        self.compressed_data = compressed_data
        self.pattern_refs = pattern_refs
        self.pattern_map = self._create_pattern_map()
    
    def _create_pattern_map(self) -> Dict[int, Tuple[str, int]]:
        """Creates a mapping of frame numbers to (pattern_id, offset) pairs"""
        frame_to_pattern = {}
        for pattern_id, positions in self.pattern_refs.items():
            pattern_length = len(self.compressed_data[pattern_id]['events'])
            for start_pos in positions:
                for offset in range(pattern_length):
                    frame_to_pattern[start_pos + offset] = (pattern_id, offset)
        return frame_to_pattern
    
    def get_frame_data(self, frame_number: int) -> Dict[str, Any]:
        """Get the frame data for a specific frame number using pattern compression"""
        if frame_number not in self.pattern_map:
            return {}  # Silent frame
            
        pattern_id, offset = self.pattern_map[frame_number]
        return self.compressed_data[pattern_id]['events'][offset]
    
    def get_max_frame(self) -> int:
        """Get the maximum frame number in the compressed data"""
        if not self.pattern_map:
            return 0
        return max(self.pattern_map.keys())
    
    def expand_to_frames(self) -> Dict[int, Dict[str, Any]]:
        """Expands compressed patterns back to frame-by-frame format"""
        frames = {}
        max_frame = self.get_max_frame()
        
        for frame in range(max_frame + 1):
            frame_data = self.get_frame_data(frame)
            if frame_data:
                frames[frame] = frame_data
                
        return frames
