"""
Performance monitoring utilities for the Immich Auto-Tagger service.
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from .logging import get_logger


@dataclass
class PerformanceMetrics:
    """Performance metrics tracking."""
    
    # API call tracking
    api_calls_total: int = 0
    api_calls_cache_hits: int = 0
    api_calls_cache_misses: int = 0
    api_response_times: List[float] = field(default_factory=list)
    
    # Tag operations
    tags_created: int = 0
    tags_retrieved_from_cache: int = 0
    bulk_operations_used: int = 0
    
    # Asset processing
    assets_processed: int = 0
    total_processing_time: float = 0.0
    average_processing_time: Optional[float] = None
    
    # Batch processing
    batches_processed: int = 0
    total_batch_time: float = 0.0
    average_batch_time: Optional[float] = None
    
    def update_averages(self):
        """Update calculated averages."""
        if self.assets_processed > 0:
            self.average_processing_time = self.total_processing_time / self.assets_processed
        
        if self.batches_processed > 0:
            self.average_batch_time = self.total_batch_time / self.batches_processed
    
    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate as a percentage."""
        total_cache_requests = self.api_calls_cache_hits + self.api_calls_cache_misses
        if total_cache_requests == 0:
            return 0.0
        return (self.api_calls_cache_hits / total_cache_requests) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for logging."""
        self.update_averages()
        return {
            "api_calls_total": self.api_calls_total,
            "cache_hit_rate_percent": round(self.get_cache_hit_rate(), 2),
            "tags_created": self.tags_created,
            "tags_from_cache": self.tags_retrieved_from_cache,
            "bulk_operations_used": self.bulk_operations_used,
            "assets_processed": self.assets_processed,
            "average_processing_time": round(self.average_processing_time or 0, 3),
            "batches_processed": self.batches_processed,
            "average_batch_time": round(self.average_batch_time or 0, 3),
        }


class PerformanceMonitor:
    """Performance monitoring and metrics collection."""
    
    def __init__(self):
        self.logger = get_logger("performance")
        self.metrics = PerformanceMetrics()
        self.start_time = time.time()
    
    def record_api_call(self, response_time: float):
        """Record an API call."""
        self.metrics.api_calls_total += 1
        self.metrics.api_response_times.append(response_time)
    
    def record_cache_hit(self):
        """Record a cache hit."""
        self.metrics.api_calls_cache_hits += 1
    
    def record_cache_miss(self):
        """Record a cache miss."""
        self.metrics.api_calls_cache_misses += 1
    
    def record_tag_created(self):
        """Record a tag creation."""
        self.metrics.tags_created += 1
    
    def record_tag_from_cache(self):
        """Record a tag retrieved from cache."""
        self.metrics.tags_retrieved_from_cache += 1
    
    def record_bulk_operation(self):
        """Record usage of bulk operations."""
        self.metrics.bulk_operations_used += 1
    
    def record_asset_processed(self, processing_time: float):
        """Record asset processing completion."""
        self.metrics.assets_processed += 1
        self.metrics.total_processing_time += processing_time
    
    def record_batch_processed(self, batch_time: float):
        """Record batch processing completion."""
        self.metrics.batches_processed += 1
        self.metrics.total_batch_time += batch_time
    
    def get_runtime_seconds(self) -> float:
        """Get total runtime in seconds."""
        return time.time() - self.start_time
    
    def log_performance_summary(self):
        """Log a summary of performance metrics."""
        runtime = self.get_runtime_seconds()
        metrics_dict = self.metrics.to_dict()
        
        self.logger.info(
            f"📈 Performance Summary: Runtime {runtime:.1f}s, "
            f"Cache hit rate {metrics_dict.get('cache_hit_rate_percent', 0):.1f}%, "
            f"API calls {metrics_dict.get('api_calls_total', 0)}"
        )
        
        # Calculate performance estimates
        if self.metrics.assets_processed > 0:
            estimated_time_for_100k = (self.metrics.average_processing_time or 0) * 100000
            assets_per_second = self.metrics.assets_processed / runtime if runtime > 0 else 0
            self.logger.info(
                f"🎯 Performance Estimates: "
                f"{assets_per_second:.1f} assets/sec, "
                f"100k images would take ~{estimated_time_for_100k / 3600:.1f} hours"
            )
    
    def get_metrics_dict(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary."""
        runtime = self.get_runtime_seconds()
        metrics_dict = self.metrics.to_dict()
        metrics_dict["runtime_seconds"] = round(runtime, 2)
        return metrics_dict


# Global performance monitor instance
performance_monitor = PerformanceMonitor()
