from typing import Dict
from collections import defaultdict

class DPCMSampleManager:
    def __init__(self, max_samples=16, memory_limit=4096):  # 4KB default limit
        self.max_samples = max_samples
        self.memory_limit = memory_limit
        self.active_samples = {}  # Currently loaded samples
        self.usage_stats = defaultdict(int)  # Track sample usage

    def allocate_sample(self, sample_name: str, sample_data: Dict) -> Dict:
        """
        Intelligently allocates DPCM samples based on usage and memory constraints
        
        Args:
            sample_name: Name of the sample to allocate
            sample_data: Dictionary containing sample metadata and binary data
            
        Returns:
            Dict containing sample allocation information
        """
        # Update usage statistics
        self.usage_stats[sample_name] += 1
        
        # Check if sample is already allocated
        if sample_name in self.active_samples:
            return self.active_samples[sample_name]
            
        # Calculate memory requirements - use length from metadata if available
        sample_size = sample_data.get('length', 1024)  # Default sample size
        
        # Check memory constraints
        current_memory = sum(s['metadata']['size'] 
                           for s in self.active_samples.values())
        
        if current_memory + sample_size > self.memory_limit:
            self._optimize_sample_bank()
            
        # At capacity: evict the lowest-scoring sample to make room.
        if len(self.active_samples) >= self.max_samples:
            self._optimize_sample_bank(force=True)

        # Allocate new sample
        sample_info = {
            'id': len(self.active_samples),
            'name': sample_name,
            'data': sample_data.get('data', []),  # Default to empty list if no data
            'metadata': {
                'size': sample_size,
                'frequency': sample_data.get('frequency', 33144),
                'original_name': sample_name
            }
        }
        
        self.active_samples[sample_name] = sample_info

        return sample_info
        
    def _optimize_sample_bank(self, force: bool = False) -> None:
        """
        Optimizes the sample bank based on usage statistics and memory constraints
        
        Args:
            force: If True, forces removal of least used samples
        """
        if len(self.active_samples) < self.max_samples and not force:
            return
            
        # Calculate sample scores based on:
        # - Usage frequency (most important)
        # - Memory size (prefer keeping smaller samples)
        sample_scores = {}

        for name, sample in self.active_samples.items():
            usage_score = self.usage_stats[name]
            size_score = 1.0 / (sample['metadata']['size'] + 1)  # Prefer smaller samples

            # Combined score (weighted)
            sample_scores[name] = (
                usage_score * 0.7 +  # Usage is most important
                size_score * 0.3     # Size is second
            )

        # Sort samples by score
        sorted_samples = sorted(
            sample_scores.items(),
            key=lambda x: x[1]
        )
        
        # Remove lowest scoring samples until we're under limits
        while (len(self.active_samples) >= self.max_samples or 
               self._get_total_memory() > self.memory_limit):
            if not sorted_samples:
                break
            sample_to_remove = sorted_samples.pop(0)[0]
            self._remove_sample(sample_to_remove)
            
    def _remove_sample(self, sample_name: str) -> None:
        """
        Removes a sample from the active samples
        """
        if sample_name in self.active_samples:
            del self.active_samples[sample_name]

    def _get_total_memory(self) -> int:
        """
        Calculates total memory usage of active samples
        """
        return sum(len(s.get('data', [])) // 8 for s in self.active_samples.values())
