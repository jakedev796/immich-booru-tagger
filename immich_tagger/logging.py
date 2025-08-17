"""
Logging configuration for the Immich Auto-Tagger service.
"""

import sys
import logging
from typing import Any, Dict
from rich.console import Console
from rich.logging import RichHandler
from .config import settings


def setup_logging() -> None:
    """Configure clean, simple logging output."""
    
    # Configure standard library logging with Rich handler
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level),
        handlers=[RichHandler(
            rich_tracebacks=True,
            show_time=True,
            show_path=False,
            show_level=False,
            markup=True
        )],
        force=True  # Override any existing configuration
    )
    
    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING) 
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Silence AI model loggers  
    logging.getLogger("wdtagger").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("tensorflow").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("safetensors").setLevel(logging.WARNING)


def get_logger(name: str):
    """Get a standard logger instance."""
    return logging.getLogger(name)


class MetricsLogger:
    """Logger for tracking processing metrics."""
    
    def __init__(self):
        self.logger = get_logger("metrics")
        self.metrics: Dict[str, Any] = {
            "assets_processed": 0,
            "tags_assigned": 0,
            "failures": 0,
            "processing_time": 0.0,
        }
    
    def log_asset_processed(self, asset_id: str, tags_count: int, processing_time: float) -> None:
        """Log a successfully processed asset."""
        self.metrics["assets_processed"] += 1
        self.metrics["tags_assigned"] += tags_count
        self.metrics["processing_time"] += processing_time
        
        # Only log individual assets at DEBUG level to avoid spam
        self.logger.debug(
            f"Asset processed: {asset_id} | Tags: {tags_count} | Time: {processing_time:.3f}s | "
            f"Total: {self.metrics['assets_processed']} assets, {self.metrics['tags_assigned']} tags"
        )
    
    def log_asset_failure(self, asset_id: str, error: str) -> None:
        """Log a failed asset processing."""
        self.metrics["failures"] += 1
        
        # Log failures at WARNING level (less verbose than ERROR but still visible)
        self.logger.warning(f"Asset processing failed: {asset_id} | Error: {error}")
    
    def log_batch_complete(self, batch_size: int, batch_time: float) -> None:
        """Log batch completion metrics."""
        # Don't log batch completion here - the processor handles clean logging
        pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.copy()
