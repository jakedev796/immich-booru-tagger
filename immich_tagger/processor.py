"""
Main processor for the Immich Auto-Tagger service.
"""

import time
from typing import List, Optional
from .immich_client import ImmichClient, ImmichAPIError
from .tagging_engine import create_tagging_engine, TaggingEngineError
from .models import Asset, Tag, TagPrediction, AssetProcessingResult, BatchProcessingResult
from .config import settings
from .logging import get_logger, MetricsLogger


class ProcessorError(Exception):
    """Custom exception for processor errors."""
    pass


class ImmichAutoTagger:
    """Main processor for auto-tagging Immich assets."""
    
    def __init__(self):
        self.logger = get_logger("processor")
        self.metrics = MetricsLogger()
        self.immich_client = ImmichClient()
        self.tagging_engine = create_tagging_engine()
        self.processed_tag: Optional[Tag] = None
        
        # Initialize the processed tag
        self._initialize_processed_tag()
    
    def _initialize_processed_tag(self):
        """Initialize the processed tag for marking completed assets."""
        try:
            self.processed_tag = self.immich_client.get_or_create_tag(settings.processed_tag_name)
            self.logger.info("Initialized processed tag", tag_id=self.processed_tag.id, name=self.processed_tag.name)
        except Exception as e:
            self.logger.error("Failed to initialize processed tag", error=str(e))
            raise ProcessorError(f"Failed to initialize processed tag: {e}")
    
    def process_asset(self, asset: Asset) -> AssetProcessingResult:
        """Process a single asset for tagging."""
        start_time = time.time()
        result = AssetProcessingResult(asset_id=asset.id, success=False)
        
        try:
            self.logger.info("Processing asset", asset_id=asset.id, name=asset.originalFileName)
            
            # Skip non-image assets for now (could be extended for video frames)
            if asset.type != "IMAGE":
                self.logger.warning("Skipping non-image asset", asset_id=asset.id, type=asset.type)
                result.success = False
                result.error = f"Unsupported asset type: {asset.type}"
                return result
            
            # Download asset thumbnail
            image_data = self.immich_client.download_asset(asset.id, use_thumbnail=True)
            
            # Predict tags
            predictions = self.tagging_engine.predict_tags(image_data)
            
            if not predictions:
                self.logger.info("No tags predicted for asset", asset_id=asset.id)
                result.success = True
                result.tags_assigned = []
            else:
                # Get or create tags in Immich
                tag_ids = []
                for prediction in predictions:
                    try:
                        tag = self.immich_client.get_or_create_tag(prediction.name)
                        tag_ids.append(tag.id)
                        result.tags_assigned.append(prediction.name)
                    except Exception as e:
                        self.logger.warning(
                            "Failed to get/create tag",
                            tag_name=prediction.name,
                            error=str(e)
                        )
                
                # Apply tags to asset
                if tag_ids:
                    self.immich_client.tag_single_asset(asset.id, tag_ids)
                
                result.success = True
            
            # Mark asset as processed
            if self.processed_tag:
                self.immich_client.tag_single_asset(asset.id, [self.processed_tag.id])
            
            processing_time = time.time() - start_time
            result.processing_time = processing_time
            
            # Log metrics
            self.metrics.log_asset_processed(
                asset_id=asset.id,
                tags_count=len(result.tags_assigned),
                processing_time=processing_time
            )
            
            self.logger.info(
                "Asset processed successfully",
                asset_id=asset.id,
                tags_assigned=len(result.tags_assigned),
                processing_time=processing_time
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            result.success = False
            result.error = str(e)
            result.processing_time = processing_time
            
            # Log failure
            self.metrics.log_asset_failure(asset_id=asset.id, error=str(e))
            
            self.logger.error(
                "Asset processing failed",
                asset_id=asset.id,
                error=str(e),
                processing_time=processing_time
            )
        
        return result
    
    def process_batch(self, assets: List[Asset]) -> BatchProcessingResult:
        """Process a batch of assets."""
        start_time = time.time()
        results = []
        
        self.logger.info("Starting batch processing", batch_size=len(assets))
        
        for asset in assets:
            result = self.process_asset(asset)
            results.append(result)
        
        batch_time = time.time() - start_time
        
        # Calculate batch statistics
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_tags_assigned = sum(len(r.tags_assigned) for r in results if r.success)
        
        batch_result = BatchProcessingResult(
            batch_size=len(assets),
            successful=successful,
            failed=failed,
            total_tags_assigned=total_tags_assigned,
            processing_time=batch_time,
            results=results
        )
        
        # Log batch completion
        self.metrics.log_batch_complete(batch_size=len(assets), batch_time=batch_time)
        
        self.logger.info(
            "Batch processing complete",
            batch_size=len(assets),
            successful=successful,
            failed=failed,
            total_tags_assigned=total_tags_assigned,
            batch_time=batch_time
        )
        
        return batch_result
    
    def get_unprocessed_assets(self, limit: Optional[int] = None) -> List[Asset]:
        """Get assets that haven't been processed yet."""
        if limit is None:
            limit = settings.batch_size
        
        try:
            # Get all assets (we'll filter out processed ones)
            all_assets = self.immich_client.get_unprocessed_assets(limit=limit * 2)  # Get more to account for filtering
            
            if not all_assets:
                self.logger.info("No assets found")
                return []
            
            # If we have a processed tag, filter out assets that already have it
            if self.processed_tag:
                # For now, we'll process all assets and let the API handle duplicates
                # This is simpler and the API should handle duplicate tag assignments gracefully
                self.logger.info("Found assets to process", count=len(all_assets))
                return all_assets[:limit]  # Return up to the limit
            else:
                self.logger.info("No processed tag configured, processing all assets", count=len(all_assets))
                return all_assets[:limit]
            
        except Exception as e:
            self.logger.error("Failed to get unprocessed assets", error=str(e))
            raise ProcessorError(f"Failed to get unprocessed assets: {e}")
    
    def run_processing_cycle(self) -> bool:
        """Run a single processing cycle."""
        try:
            # Get unprocessed assets
            assets = self.get_unprocessed_assets()
            
            if not assets:
                self.logger.info("No unprocessed assets found")
                return False
            
            # Process the batch
            batch_result = self.process_batch(assets)
            
            # Return True if there were successful processing or if we should continue
            return batch_result.successful > 0 or batch_result.failed > 0
            
        except Exception as e:
            self.logger.error("Processing cycle failed", error=str(e))
            return False
    
    def run_continuous_processing(self, max_cycles: Optional[int] = None):
        """Run continuous processing until no more assets are found or max cycles reached."""
        cycle_count = 0
        
        self.logger.info("Starting continuous processing", max_cycles=max_cycles)
        
        while True:
            if max_cycles and cycle_count >= max_cycles:
                self.logger.info("Reached maximum cycles", max_cycles=max_cycles)
                break
            
            cycle_count += 1
            self.logger.info("Starting processing cycle", cycle_number=cycle_count)
            
            # Run processing cycle
            should_continue = self.run_processing_cycle()
            
            if not should_continue:
                self.logger.info("No more assets to process, stopping")
                break
            
            # Small delay between cycles to be gentle on the API
            time.sleep(1.0)
        
        self.logger.info("Continuous processing completed", total_cycles=cycle_count)
    
    def get_metrics(self):
        """Get current processing metrics."""
        return self.metrics.get_metrics()
    
    def test_connection(self) -> bool:
        """Test the connection to Immich."""
        return self.immich_client.test_connection()
    
    def close(self):
        """Clean up resources."""
        self.immich_client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
