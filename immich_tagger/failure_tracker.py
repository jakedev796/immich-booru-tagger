"""
Failure tracking system for assets that consistently fail to process.
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Set
from .logging import get_logger
from .config import settings


class FailureTracker:
    """Tracks and manages asset processing failures."""
    
    def __init__(self, failure_file: str = "processing_failures.json"):
        self.failure_file = failure_file
        self.logger = get_logger("failure_tracker")
        
        # Structure: {asset_id: {"attempts": N, "last_failed": "ISO_TIME", "permanently_failed": bool}}
        self.failures: Dict[str, Dict] = {}
        self.last_file_mtime = 0.0  # Track file modification time for external changes
        self.load_failures()
        
    def load_failures(self):
        """Load failure data from disk."""
        try:
            if os.path.exists(self.failure_file):
                # Update file modification time
                self.last_file_mtime = os.path.getmtime(self.failure_file)
                
                with open(self.failure_file, 'r') as f:
                    data = json.load(f)
                    self.failures = data.get("failures", {})
                    self.logger.debug(f"📋 Loaded {len(self.failures)} failure records")
            else:
                self.logger.debug("📋 No failure file found, starting fresh")
                self.failures = {}
                self.last_file_mtime = 0.0
        except Exception as e:
            self.logger.warning(f"⚠️  Failed to load failure data: {e}, starting fresh")
            self.failures = {}
            self.last_file_mtime = 0.0
    
    def save_failures(self):
        """Save failure data to disk."""
        try:
            data = {
                "failures": self.failures,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "failure_timeout": settings.failure_timeout
            }
            
            with open(self.failure_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            # Update our file modification time after saving
            self.last_file_mtime = os.path.getmtime(self.failure_file)
            self.logger.debug(f"💾 Saved {len(self.failures)} failure records")
        except Exception as e:
            self.logger.warning(f"⚠️  Failed to save failure data: {e}")
    
    def record_failure(self, asset_id: str) -> bool:
        """Record a failure for an asset.
        
        Returns:
            True if asset should be retried, False if permanently failed
        """
        now = datetime.now(timezone.utc).isoformat()
        
        if asset_id not in self.failures:
            self.failures[asset_id] = {
                "attempts": 1,
                "last_failed": now,
                "permanently_failed": False
            }
        else:
            self.failures[asset_id]["attempts"] += 1
            self.failures[asset_id]["last_failed"] = now
        
        failure_record = self.failures[asset_id]
        
        # Check if we've exceeded the retry limit
        if settings.failure_timeout > 0 and failure_record["attempts"] >= settings.failure_timeout:
            failure_record["permanently_failed"] = True
            self.logger.warning(f"❌ Asset {asset_id} marked as permanently failed after {failure_record['attempts']} attempts")
            self.save_failures()
            return False
        elif settings.failure_timeout == 0:
            # Never retry if timeout is 0
            failure_record["permanently_failed"] = True
            self.logger.warning(f"❌ Asset {asset_id} marked as permanently failed (no retries allowed)")
            self.save_failures()
            return False
        else:
            self.logger.debug(f"⚠️  Asset {asset_id} failed (attempt {failure_record['attempts']}/{settings.failure_timeout})")
            self.save_failures()
            return True
    
    def is_permanently_failed(self, asset_id: str) -> bool:
        """Check if an asset is permanently failed."""
        return self.failures.get(asset_id, {}).get("permanently_failed", False)
    
    def filter_failed_assets(self, assets: List) -> List:
        """Filter out permanently failed assets from a list.
        
        Args:
            assets: List of Asset objects
            
        Returns:
            Filtered list with permanently failed assets removed
        """
        if not self.failures:
            return assets
            
        initial_count = len(assets)
        filtered_assets = [asset for asset in assets if not self.is_permanently_failed(asset.id)]
        filtered_count = initial_count - len(filtered_assets)
        
        if filtered_count > 0:
            self.logger.info(f"🚫 Filtered out {filtered_count} permanently failed assets")
            
        return filtered_assets
    
    def get_failed_assets(self) -> Dict[str, Dict]:
        """Get all failed assets and their failure info."""
        return {asset_id: info for asset_id, info in self.failures.items()}
    
    def get_permanently_failed_assets(self) -> List[str]:
        """Get list of permanently failed asset IDs."""
        return [asset_id for asset_id, info in self.failures.items() 
                if info.get("permanently_failed", False)]
    
    def get_retry_candidates(self) -> List[str]:
        """Get list of assets that have failed but can still be retried."""
        return [asset_id for asset_id, info in self.failures.items() 
                if not info.get("permanently_failed", False)]
    
    def reset_failures(self, asset_ids: List[str] = None):
        """Reset failure data for specific assets or all assets.
        
        Args:
            asset_ids: List of asset IDs to reset, or None to reset all
        """
        if asset_ids is None:
            # Reset all failures
            count = len(self.failures)
            self.failures = {}
            self.logger.info(f"🔄 Reset all {count} failure records")
        else:
            # Reset specific assets
            count = 0
            for asset_id in asset_ids:
                if asset_id in self.failures:
                    del self.failures[asset_id]
                    count += 1
            self.logger.info(f"🔄 Reset {count} failure records")
        
        self.save_failures()
    
    def check_for_external_changes(self) -> bool:
        """Check if the failure file was modified externally and reload if needed.
        
        Returns:
            True if the file was reloaded, False if no changes detected
        """
        if not os.path.exists(self.failure_file):
            # File was deleted externally
            if self.failures:
                self.logger.info("🔄 Failure file was deleted externally, clearing memory cache")
                self.failures = {}
                self.last_file_mtime = 0.0
                return True
            return False
        
        try:
            current_mtime = os.path.getmtime(self.failure_file)
            if current_mtime > self.last_file_mtime:
                self.logger.info("🔄 Failure file modified externally, reloading...")
                old_count = len(self.failures)
                self.load_failures()
                new_count = len(self.failures)
                
                if old_count != new_count:
                    self.logger.info(f"📊 Failure count changed: {old_count} → {new_count}")
                
                return True
        except Exception as e:
            self.logger.warning(f"⚠️  Failed to check file modification time: {e}")
        
        return False
    
    def get_failure_summary(self) -> Dict:
        """Get a summary of failure statistics."""
        permanently_failed = self.get_permanently_failed_assets()
        retry_candidates = self.get_retry_candidates()
        
        return {
            "total_failed_assets": len(self.failures),
            "permanently_failed": len(permanently_failed),
            "retry_candidates": len(retry_candidates),
            "failure_timeout": settings.failure_timeout,
            "permanently_failed_ids": permanently_failed[:10] if len(permanently_failed) <= 10 else permanently_failed[:10] + ["..."]
        }
