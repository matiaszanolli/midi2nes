# New file: exporter/base_exporter.py

from typing import Dict, Any, Tuple
from exporter.compression import CompressionEngine

class BaseExporter:
    """Base class for all exporters with compression support"""
    
    def __init__(self):
        self.compression_engine = CompressionEngine()
    
    def compress_channel_data(self, channel_data: Dict[str, Any]) -> Tuple[bytes, Dict[str, Any]]:
        """
        Compress channel data using the compression engine
        
        Args:
            channel_data: Dictionary of frame events for a channel
            
        Returns:
            Tuple of (compressed_data, metadata)
        """
        # Convert frame dictionary to list of events
        max_frame = max(int(f) for f in channel_data.keys()) if channel_data else 0
        events = []
        
        for frame in range(max_frame + 1):
            if str(frame) in channel_data:
                events.append(channel_data[str(frame)])
            else:
                events.append({})  # Empty event for silent frames
        
        return self.compression_engine.compress_pattern(events)
    
    def decompress_channel_data(self, compressed: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decompress channel data using the compression engine
        
        Args:
            compressed: Compressed binary data
            metadata: Compression metadata
            
        Returns:
            Dictionary of frame events
        """
        events = self.compression_engine.decompress_pattern(compressed, metadata)
        return {str(i): event for i, event in enumerate(events) if event}
