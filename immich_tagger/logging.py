"""
Logging configuration for the Immich Auto-Tagger service.
"""

import sys
import logging
from typing import Any, Dict
import structlog
from rich.console import Console
from rich.logging import RichHandler
from .config import settings


def setup_logging() -> None:
    """Configure structured logging with rich console output."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level),
        handlers=[RichHandler(rich_tracebacks=True)]
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


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
        
        self.logger.info(
            "Asset processed successfully",
            asset_id=asset_id,
            tags_count=tags_count,
            processing_time=processing_time,
            total_assets_processed=self.metrics["assets_processed"],
            total_tags_assigned=self.metrics["tags_assigned"],
        )
    
    def log_asset_failure(self, asset_id: str, error: str) -> None:
        """Log a failed asset processing."""
        self.metrics["failures"] += 1
        
        self.logger.error(
            "Asset processing failed",
            asset_id=asset_id,
            error=error,
            total_failures=self.metrics["failures"],
        )
    
    def log_batch_complete(self, batch_size: int, batch_time: float) -> None:
        """Log batch completion metrics."""
        self.logger.info(
            "Batch processing complete",
            batch_size=batch_size,
            batch_time=batch_time,
            total_assets_processed=self.metrics["assets_processed"],
            total_tags_assigned=self.metrics["tags_assigned"],
            total_failures=self.metrics["failures"],
            avg_processing_time=self.metrics["processing_time"] / max(1, self.metrics["assets_processed"]),
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.copy()
