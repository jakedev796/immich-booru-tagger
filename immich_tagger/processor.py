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
from .performance_monitor import performance_monitor


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
        
        # Progress tracking
        self.total_processed_assets = 0
        self.total_assigned_tags = 0
        
        # Initialize the processed tag
        self._initialize_processed_tag()
    
    def _initialize_processed_tag(self):
        """Initialize the processed tag for marking completed assets."""
        try:
            self.processed_tag = self.immich_client.get_or_create_tag(settings.processed_tag_name)
            self.logger.info(f"🏷️  Using processed tag: '{self.processed_tag.name}'")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize processed tag: {str(e)}")
            raise ProcessorError(f"Failed to initialize processed tag: {e}")
    
    def process_asset(self, asset: Asset) -> AssetProcessingResult:
        """Process a single asset for tagging."""
        start_time = time.time()
        result = AssetProcessingResult(asset_id=asset.id, success=False)
        
        try:
            # Skip non-image assets for now (could be extended for video frames)
            if asset.type != "IMAGE":
                result.success = False
                result.error = f"Unsupported asset type: {asset.type}"
                return result
            
            # Check if asset already has the processed tag (skip if already done)
            if self.processed_tag and hasattr(asset, 'tags') and asset.tags:
                for tag in asset.tags:
                    if tag.id == self.processed_tag.id:
                        result.success = True
                        result.tags_assigned = []
                        result.processing_time = time.time() - start_time
                        self.logger.debug(f"⏭️  Skipping already processed asset: {asset.id}")
                        return result
            
            # Download asset thumbnail
            image_data = self.immich_client.download_asset(asset.id, use_thumbnail=True)
            
            # Predict tags
            predictions = self.tagging_engine.predict_tags(image_data)
            
            if not predictions:
                result.success = True
                result.tags_assigned = []
            else:
                # Use bulk tag operations for efficiency
                tag_names = [prediction.name for prediction in predictions]
                tag_mapping = self.immich_client.get_or_create_tags_bulk(tag_names)
                
                # Extract tag IDs for successful tags
                tag_ids = []
                for tag_name, tag in tag_mapping.items():
                    tag_ids.append(tag.id)
                    result.tags_assigned.append(tag_name)
                
                # Apply tags to asset
                if tag_ids:
                    self.immich_client.tag_single_asset(asset.id, tag_ids)
                
                result.success = True
            
            # Mark asset as processed
            if self.processed_tag:
                self.immich_client.tag_single_asset(asset.id, [self.processed_tag.id])
            
            processing_time = time.time() - start_time
            result.processing_time = processing_time
            
            # Update internal metrics only
            self.metrics.metrics["assets_processed"] += 1
            self.metrics.metrics["tags_assigned"] += len(result.tags_assigned)
            self.metrics.metrics["processing_time"] += processing_time
            
            # Record performance metrics
            performance_monitor.record_asset_processed(processing_time)
            
        except Exception as e:
            processing_time = time.time() - start_time
            result.success = False
            result.error = str(e)
            result.processing_time = processing_time
            
            # Update failure metrics only  
            self.metrics.metrics["failures"] += 1
        
        return result
    
    def process_batch(self, assets: List[Asset]) -> BatchProcessingResult:
        """Process a batch of assets with optimized bulk operations."""
        start_time = time.time()
        results = []
        
        # Pre-warm the tag cache before processing
        try:
            self.immich_client.get_all_tags(use_cache=True)
        except Exception as e:
            self.logger.warning(f"⚠️  Failed to pre-warm tag cache: {str(e)}")
        
        for asset in assets:
            result = self.process_asset(asset)
            results.append(result)
        
        batch_time = time.time() - start_time
        
        # Calculate batch statistics
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success and r.error)
        skipped = sum(1 for r in results if r.success and not r.tags_assigned)  # Already processed
        processed = sum(1 for r in results if r.success and r.tags_assigned)  # Newly processed
        total_tags_assigned = sum(len(r.tags_assigned) for r in results if r.success)
        
        batch_result = BatchProcessingResult(
            batch_size=len(assets),
            successful=successful,
            failed=failed,
            total_tags_assigned=total_tags_assigned,
            processing_time=batch_time,
            results=results
        )
        
        # Update totals (only count newly processed assets, not skipped ones)
        self.total_processed_assets += processed
        self.total_assigned_tags += total_tags_assigned
        
        # Record performance metrics
        performance_monitor.record_batch_processed(batch_time)
        
        
        # Clean, focused logging with progress
        rate_per_second = len(assets) / batch_time if batch_time > 0 else 0
        
        # Create status message based on what happened
        if skipped > 0:
            status_msg = f"📊 Batch: {processed} processed, {skipped} already done"
            if failed > 0:
                status_msg += f", {failed} failed"
        else:
            status_msg = f"📊 Batch: {processed} processed"
            if failed > 0:
                status_msg += f", {failed} failed"
        
        self.logger.info(
            f"{status_msg} | "
            f"{total_tags_assigned} tags assigned | "
            f"Rate: {rate_per_second:.1f}/sec | "
            f"Total: {self.total_processed_assets} processed, {self.total_assigned_tags} tags"
        )
        
        return batch_result
    
    def get_unprocessed_assets(self, limit: Optional[int] = None) -> List[Asset]:
        """Get untagged image assets that need processing.
        
        Now simplified: uses metadata search to find image assets with no tags.
        Videos are excluded since WD14 cannot process them.
        The API naturally returns ~250 assets at a time.
        """
        if limit is None:
            limit = settings.batch_size
        
        try:
            assets = self.immich_client.get_unprocessed_assets()
            
            if not assets:
                self.logger.info("✅ No more untagged images found - processing complete!")
                return []
            
            self.logger.info(f"🎯 Found {len(assets)} untagged images to process")
            return assets
            
        except Exception as e:
            self.logger.error(f"Failed to get unprocessed assets: {str(e)}")
            raise ProcessorError(f"Failed to get unprocessed assets: {e}")
    
    def run_processing_cycle(self) -> bool:
        """Run a single processing cycle."""
        try:
            # Get unprocessed assets
            assets = self.get_unprocessed_assets()
            
            if not assets:
                self.logger.info("✅ All images have been processed!")
                return False
            
            # Process the batch
            batch_result = self.process_batch(assets)
            
            # Return True if there were any assets processed (successful or failed)
            # This indicates we should continue looking for more assets
            assets_processed = batch_result.successful + batch_result.failed
            return assets_processed > 0
            
        except Exception as e:
            self.logger.error(f"❌ Processing cycle failed: {str(e)}")
            return False
    
    def run_continuous_processing(self, max_cycles: Optional[int] = None):
        """Run continuous processing until no more assets are found or max cycles reached."""
        cycle_count = 0
        
        self.logger.info("🚀 Starting continuous processing...")
        
        while True:
            if max_cycles and cycle_count >= max_cycles:
                self.logger.info(f"🔢 Reached maximum cycles: {max_cycles}")
                break
            
            cycle_count += 1
            
            # Run processing cycle
            should_continue = self.run_processing_cycle()
            
            if not should_continue:
                self.logger.info("🎉 Processing complete! No more assets to process.")
                break
            
            # Small delay between cycles to be gentle on the API
            time.sleep(1.0)
        
        # Final summary
        self.logger.info(
            f"🏁 Processing complete! Total: {self.total_processed_assets} assets processed, "
            f"{self.total_assigned_tags} tags assigned in {cycle_count} cycles"
        )
        
        # Log final performance summary
        performance_monitor.log_performance_summary()
    
    def reset_progress(self):
        """Reset processing progress counters."""
        self.total_processed_assets = 0
        self.total_assigned_tags = 0
        self.logger.info("🔄 Progress counters reset")
    
    def get_progress_status(self) -> dict:
        """Get processing progress information."""
        return {
            "total_processed": self.total_processed_assets,
            "total_tags_assigned": self.total_assigned_tags
        }

    def get_metrics(self):
        """Get current processing metrics."""
        base_metrics = self.metrics.get_metrics()
        performance_metrics = performance_monitor.get_metrics_dict()
        progress_info = self.get_progress_status()
        
        # Combine all metric sources
        combined_metrics = {
            "basic_metrics": base_metrics,
            "performance_metrics": performance_metrics,
            "progress_info": progress_info
        }
        
        return combined_metrics
    
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
