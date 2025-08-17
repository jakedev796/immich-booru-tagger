#!/usr/bin/env python3
"""
Cleanup script for removing permanently failed assets from Immich.

This script is designed to remove assets that have consistently failed to process,
as they are likely corrupted, unreadable, or have format issues that prevent
the AI tagging models from processing them.

CAUTION: This script will permanently delete assets from your Immich library.
Use with care and ensure you have backups if needed.
"""

import json
import sys
import argparse
from typing import List, Dict, Optional
from immich_tagger.immich_client import ImmichClient
from immich_tagger.failure_tracker import FailureTracker
from immich_tagger.logging import get_logger
from immich_tagger.config import settings


class AssetCleanupError(Exception):
    """Exception for asset cleanup operations."""
    pass


class FailedAssetCleaner:
    """Handles cleanup of permanently failed assets."""
    
    def __init__(self):
        self.logger = get_logger("asset_cleaner")
        self.immich_client = ImmichClient()
        self.failure_tracker = FailureTracker()
        
    def get_failed_assets_info(self) -> Dict[str, Dict]:
        """Get detailed information about failed assets."""
        failed_assets = self.failure_tracker.get_failed_assets()
        permanently_failed = {
            asset_id: info for asset_id, info in failed_assets.items() 
            if info.get("permanently_failed", False)
        }
        
        return permanently_failed
    
    def get_asset_details(self, asset_ids: List[str]) -> List[Dict]:
        """Get detailed asset information from Immich API."""
        asset_details = []
        
        for asset_id in asset_ids:
            try:
                # Try to get asset details from Immich
                response = self.immich_client._make_request(
                    method="GET",
                    endpoint=f"/api/assets/{asset_id}"
                )
                
                if response.status_code == 200:
                    asset_data = response.json()
                    asset_details.append({
                        "id": asset_id,
                        "originalFileName": asset_data.get("originalFileName", "unknown"),
                        "type": asset_data.get("type", "unknown"),
                        "fileSize": asset_data.get("exifInfo", {}).get("fileSizeInByte", 0),
                        "createdAt": asset_data.get("fileCreatedAt", "unknown"),
                        "status": "exists"
                    })
                else:
                    asset_details.append({
                        "id": asset_id,
                        "originalFileName": "unknown",
                        "type": "unknown",
                        "fileSize": 0,
                        "createdAt": "unknown",
                        "status": f"api_error_{response.status_code}"
                    })
                    
            except Exception as e:
                self.logger.debug(f"Failed to get details for asset {asset_id}: {e}")
                asset_details.append({
                    "id": asset_id,
                    "originalFileName": "unknown",
                    "type": "unknown", 
                    "fileSize": 0,
                    "createdAt": "unknown",
                    "status": "error"
                })
                
        return asset_details
    
    def delete_assets(self, asset_ids: List[str], force: bool = False) -> Dict[str, str]:
        """Delete assets from Immich.
        
        Args:
            asset_ids: List of asset IDs to delete
            force: If True, skip individual confirmations
            
        Returns:
            Dict mapping asset_id to result status ("deleted", "error", "skipped")
        """
        results = {}
        
        for asset_id in asset_ids:
            try:
                if not force:
                    confirm = input(f"Delete asset {asset_id}? (y/N): ").strip().lower()
                    if confirm != 'y':
                        results[asset_id] = "skipped"
                        self.logger.info(f"⏭️  Skipped {asset_id}")
                        continue
                
                # Delete the asset via Immich API
                response = self.immich_client._make_request(
                    method="DELETE",
                    endpoint="/api/assets",
                    json_data={"ids": [asset_id]}
                )
                
                if response.status_code in [200, 204]:
                    results[asset_id] = "deleted"
                    self.logger.info(f"🗑️  Deleted asset {asset_id}")
                else:
                    results[asset_id] = f"error_{response.status_code}"
                    self.logger.error(f"❌ Failed to delete {asset_id}: HTTP {response.status_code}")
                    
            except Exception as e:
                results[asset_id] = "error"
                self.logger.error(f"❌ Failed to delete {asset_id}: {e}")
                
        return results
    
    def cleanup_failure_records(self, successfully_deleted: List[str]):
        """Remove failure records for successfully deleted assets."""
        if successfully_deleted:
            self.failure_tracker.reset_failures(successfully_deleted)
            self.logger.info(f"🧹 Cleaned up failure records for {len(successfully_deleted)} deleted assets")
    
    def run_cleanup(self, dry_run: bool = False, force: bool = False, 
                   asset_ids: Optional[List[str]] = None) -> Dict:
        """Run the cleanup process.
        
        Args:
            dry_run: If True, show what would be deleted without actually deleting
            force: If True, skip confirmations (use with caution!)
            asset_ids: If provided, only consider these specific asset IDs
            
        Returns:
            Summary of cleanup results
        """
        self.logger.info("🧹 Starting failed asset cleanup process")
        
        # Get failed assets
        failed_assets = self.get_failed_assets_info()
        if not failed_assets:
            self.logger.info("✅ No permanently failed assets found")
            return {"total_failed": 0, "processed": 0, "deleted": 0}
        
        # Filter to specific assets if requested
        if asset_ids:
            failed_assets = {
                aid: info for aid, info in failed_assets.items() 
                if aid in asset_ids
            }
            if not failed_assets:
                self.logger.info("❌ None of the specified asset IDs are permanently failed")
                return {"total_failed": 0, "processed": 0, "deleted": 0}
        
        asset_list = list(failed_assets.keys())
        self.logger.info(f"📊 Found {len(asset_list)} permanently failed assets")
        
        # Get asset details for better user information
        self.logger.info("🔍 Fetching asset details from Immich...")
        asset_details = self.get_asset_details(asset_list)
        
        # Show what will be processed
        self.logger.info("📋 Assets to be processed:")
        total_size = 0
        existing_assets = []
        
        for detail in asset_details:
            failure_info = failed_assets[detail["id"]]
            size_mb = detail["fileSize"] / (1024 * 1024) if detail["fileSize"] > 0 else 0
            total_size += size_mb
            
            status_info = ""
            if detail["status"] == "exists":
                existing_assets.append(detail["id"])
                status_info = f"✅ Exists ({size_mb:.1f} MB)"
            elif detail["status"].startswith("api_error"):
                status_info = f"⚠️  API Error ({detail['status']})"
            else:
                status_info = "❌ Error getting details"
                
            self.logger.info(
                f"   • {detail['originalFileName']} ({detail['id']})"
                f" - {failure_info['attempts']} attempts - {status_info}"
            )
        
        if total_size > 0:
            self.logger.info(f"💾 Total size of existing assets: {total_size:.1f} MB")
        
        # Safety check - only process existing assets
        processable_assets = existing_assets
        if not processable_assets:
            self.logger.warning("⚠️  No assets can be processed (none exist in Immich)")
            return {"total_failed": len(failed_assets), "processed": 0, "deleted": 0}
        
        # Dry run mode
        if dry_run:
            self.logger.info(f"🔍 DRY RUN: Would delete {len(processable_assets)} assets")
            return {
                "total_failed": len(failed_assets), 
                "processed": len(processable_assets),
                "deleted": 0
            }
        
        # Confirmation prompt (unless force mode)
        if not force:
            self.logger.warning("⚠️  WARNING: This will permanently delete assets from Immich!")
            self.logger.info("💡 Tip: Use --dry-run first to preview what will be deleted")
            
            confirm = input(f"\n🗑️  Delete {len(processable_assets)} permanently failed assets? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y']:
                self.logger.info("❌ Cleanup cancelled by user")
                return {"total_failed": len(failed_assets), "processed": 0, "deleted": 0}
        
        # Perform deletions
        self.logger.info(f"🗑️  Deleting {len(processable_assets)} assets...")
        delete_results = self.delete_assets(processable_assets, force=force)
        
        # Process results
        deleted = [aid for aid, result in delete_results.items() if result == "deleted"]
        errors = [aid for aid, result in delete_results.items() if result.startswith("error")]
        skipped = [aid for aid, result in delete_results.items() if result == "skipped"]
        
        # Cleanup failure records for successfully deleted assets
        if deleted:
            self.cleanup_failure_records(deleted)
        
        # Summary
        self.logger.info(f"✅ Cleanup complete:")
        self.logger.info(f"   🗑️  Deleted: {len(deleted)} assets")
        if errors:
            self.logger.info(f"   ❌ Errors: {len(errors)} assets")
        if skipped:
            self.logger.info(f"   ⏭️  Skipped: {len(skipped)} assets")
        
        return {
            "total_failed": len(failed_assets),
            "processed": len(processable_assets), 
            "deleted": len(deleted),
            "errors": len(errors),
            "skipped": len(skipped)
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Remove permanently failed assets from Immich",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be deleted (safe)
  python cleanup_failed_assets.py --dry-run
  
  # Interactive cleanup with confirmations
  python cleanup_failed_assets.py
  
  # Automated cleanup (no confirmations - USE WITH CAUTION!)
  python cleanup_failed_assets.py --force
  
  # Clean up specific asset IDs only
  python cleanup_failed_assets.py --asset-ids asset-id-1 asset-id-2
  
CAUTION: This script permanently deletes assets from Immich.
Always use --dry-run first to preview the changes!
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts (USE WITH CAUTION!)"
    )
    
    parser.add_argument(
        "--asset-ids",
        nargs='+',
        metavar='ID',
        help="Only process specific asset IDs"
    )
    
    args = parser.parse_args()
    
    # Safety check
    if args.force and not args.dry_run:
        print("⚠️  WARNING: --force mode will delete assets without confirmation!")
        confirm = input("Are you absolutely sure? Type 'DELETE' to continue: ")
        if confirm != 'DELETE':
            print("❌ Cancelled for safety")
            sys.exit(1)
    
    try:
        cleaner = FailedAssetCleaner()
        results = cleaner.run_cleanup(
            dry_run=args.dry_run,
            force=args.force,
            asset_ids=args.asset_ids
        )
        
        print(f"\n📊 Final Results: {results}")
        
    except KeyboardInterrupt:
        print("\n❌ Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger = get_logger("cleanup_main")
        logger.error(f"❌ Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
