"""
Immich API client for interacting with the Immich instance.
"""

import time
from typing import List, Optional, Dict, Any
import httpx
from .models import Asset, Tag, BulkTagRequest, CreateTagRequest
from .config import settings
from .logging import get_logger
from .performance_monitor import performance_monitor


class ImmichAPIError(Exception):
    """Custom exception for Immich API errors."""
    pass


class ImmichClient:
    """Client for interacting with the Immich API."""
    
    def __init__(self):
        self.base_url = settings.immich_base_url
        self.api_key = settings.immich_api_key
        self.timeout = settings.request_timeout
        self.max_retries = settings.max_retries
        self.retry_delay = settings.retry_delay
        self.logger = get_logger("immich_client")
        
        # Performance optimizations
        self._tag_cache: Dict[str, Tag] = {}  # name -> Tag mapping
        self._tag_cache_valid = False
        self._tag_cache_timestamp = 0
        self._cache_ttl = settings.tag_cache_ttl
        
        # HTTP client with retry logic
        self.client = httpx.Client(
            timeout=self.timeout,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            }
        )
        
        # Silence httpx request logging
        import logging
        logging.getLogger("httpx").setLevel(logging.WARNING)
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Make an HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"
        request_start = time.time()
        
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data
                )
                response.raise_for_status()
                
                # Record successful API call
                response_time = time.time() - request_start
                performance_monitor.record_api_call(response_time)
                
                return response
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < self.max_retries:
                    self.logger.warning(
                        f"⚠️  Server error {e.response.status_code}, retrying "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
                    continue
                else:
                    self.logger.error(
                        f"❌ HTTP {method} {url} failed: {e.response.status_code} - {e.response.text}"
                    )
                    raise ImmichAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
                    
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    self.logger.warning(
                        "Request error, retrying",
                        error=str(e),
                        attempt=attempt + 1,
                        max_retries=self.max_retries
                    )
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                else:
                    self.logger.error(f"❌ Request failed: {str(e)}")
                    raise ImmichAPIError(f"Request failed: {e}")
    
    def get_untagged_assets(self) -> List[Asset]:
        """Get image assets that have no tags using the metadata search endpoint.
        
        This endpoint naturally returns up to 250 assets at a time that don't have any tags.
        As we tag assets with 'auto:processed', they disappear from this search automatically.
        Only searches for IMAGE assets since WD14 cannot process videos.
        
        Returns:
            List of untagged image assets (max 250 per call)
        """
        self.logger.debug("🔍 Getting untagged image assets via metadata search")
        
        # Use the metadata search endpoint to find image assets without any tags
        response = self._make_request(
            method="POST",
            endpoint="/api/search/metadata",
            json_data={
                "tagIds": None,  # null/None means "assets with no tags"
                "type": "IMAGE"  # Only process images, not videos (WD14 can't process videos)
            }
        )
        
        response_data = response.json()
        
        # Metadata search returns: {"albums": {...}, "assets": {"items": [...], "total": N, "nextPage": "..."}}
        if not isinstance(response_data, dict) or "assets" not in response_data:
            self.logger.error(f"❌ Unexpected metadata response structure: {list(response_data.keys()) if isinstance(response_data, dict) else type(response_data)}")
            return []
            
        assets_section = response_data["assets"]
        assets_list = assets_section.get("items", [])
        total_available = assets_section.get("total", len(assets_list))
        
        self.logger.debug(f"📊 Metadata search: {len(assets_list)} assets returned, {total_available} total available")
        
        # Parse assets
        assets = []
        for asset_data in assets_list:
            try:
                if isinstance(asset_data, dict):
                    assets.append(Asset(**asset_data))
                else:
                    self.logger.debug(f"⚠️  Skipping non-dict asset data: {type(asset_data)}")
            except Exception as e:
                self.logger.warning(f"⚠️  Failed to parse asset: {e}")
                continue
        
        self.logger.info(f"✅ Found {len(assets)} untagged image assets (of {total_available} total available)")
        return assets
    
    def get_unprocessed_assets(self, processed_tag_id: Optional[str] = None, limit: int = 250) -> List[Asset]:
        """Get unprocessed assets - now simplified to use metadata search.
        
        Args:
            processed_tag_id: Ignored - we use tagIds:null to get untagged assets
            limit: Ignored - API returns natural batches of ~250
            
        Returns:
            List of assets that have no tags (and thus need processing)
        """
        return self.get_untagged_assets()
    
    def download_asset(self, asset_id: str, use_thumbnail: bool = True) -> bytes:
        """Download an asset (thumbnail or original)."""
        endpoint = f"/api/assets/{asset_id}/{'thumbnail' if use_thumbnail else 'download'}"
        
        self.logger.debug("Downloading asset", asset_id=asset_id, use_thumbnail=use_thumbnail)
        
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.get(url)
                response.raise_for_status()
                content = response.content
                self.logger.debug("Asset downloaded", asset_id=asset_id, size=len(content))
                return content
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < self.max_retries:
                    self.logger.warning(
                        f"⚠️  Server error {e.response.status_code}, retrying "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                else:
                    self.logger.error(
                        "HTTP request failed",
                        method="GET",
                        url=url,
                        status_code=e.response.status_code,
                        response_text=e.response.text
                    )
                    raise ImmichAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
                    
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    self.logger.warning(
                        "Request error, retrying",
                        error=str(e),
                        attempt=attempt + 1,
                        max_retries=self.max_retries
                    )
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                else:
                    self.logger.error(f"❌ Request failed: {str(e)}")
                    raise ImmichAPIError(f"Request failed: {e}")
    
    def get_all_tags(self, use_cache: bool = True) -> List[Tag]:
        """Get all tags from Immich with optional caching."""
        current_time = time.time()
        
        # Check if cache is valid
        if (use_cache and self._tag_cache_valid and 
            current_time - self._tag_cache_timestamp < self._cache_ttl):
            self.logger.debug("Using cached tags", count=len(self._tag_cache))
            return list(self._tag_cache.values())
        
        self.logger.debug("Fetching all tags from API")
        
        response = self._make_request(method="GET", endpoint="/api/tags")
        tags_data = response.json()
        tags = [Tag(**tag_data) for tag_data in tags_data]
        
        # Update cache
        if use_cache:
            self._tag_cache = {tag.name.lower(): tag for tag in tags}
            self._tag_cache_valid = True
            self._tag_cache_timestamp = current_time
            self.logger.debug("Updated tag cache", count=len(self._tag_cache))
        
        self.logger.debug("Fetched tags", count=len(tags))
        return tags
    
    def create_tag(self, tag_request: CreateTagRequest) -> Tag:
        """Create a new tag in Immich."""
        self.logger.debug("Creating tag", name=tag_request.name)
        
        response = self._make_request(
            method="POST",
            endpoint="/api/tags",
            json_data=tag_request.dict()
        )
        
        tag_data = response.json()
        tag = Tag(**tag_data)
        
        # Update cache immediately
        self._tag_cache[tag.name.lower()] = tag
        
        self.logger.debug("Created tag", tag_id=tag.id, name=tag.name)
        return tag
    
    def get_or_create_tag(self, tag_name: str) -> Tag:
        """Get an existing tag or create it if it doesn't exist."""
        # Validate tag name first
        if not self._is_valid_tag_name(tag_name):
            self.logger.debug(f"Skipping invalid tag name: '{tag_name}'")
            raise ValueError(f"Invalid tag name: '{tag_name}'")
        
        tag_name_clean = tag_name.strip()
        tag_name_lower = tag_name_clean.lower()
        
        # Ensure cache is populated
        if not self._tag_cache_valid:
            self.get_all_tags(use_cache=True)
        
        # Check cache first
        if tag_name_lower in self._tag_cache:
            performance_monitor.record_cache_hit()
            performance_monitor.record_tag_from_cache()
            return self._tag_cache[tag_name_lower]
        
        # Create new tag if not found
        performance_monitor.record_cache_miss()
        self.logger.debug("Creating new tag", name=tag_name_clean)
        try:
            tag_request = CreateTagRequest(name=tag_name_clean)
            new_tag = self.create_tag(tag_request)
            performance_monitor.record_tag_created()
            
            # Add to cache
            self._tag_cache[tag_name_lower] = new_tag
            return new_tag
            
        except Exception as e:
            # Handle "tag already exists" case
            if "already exists" in str(e).lower():
                # Refresh cache and try again
                self.invalidate_tag_cache()
                self.get_all_tags(use_cache=True)
                if tag_name_lower in self._tag_cache:
                    self.logger.debug(f"Found existing tag after cache refresh: {tag_name_clean}")
                    return self._tag_cache[tag_name_lower]
            
            # Re-raise the exception if we can't handle it
            raise
    
    def _is_valid_tag_name(self, tag_name: str) -> bool:
        """Check if a tag name is valid for Immich."""
        if not tag_name or not tag_name.strip():
            return False
        
        # Only filter out characters that would actually break the API or filesystem
        # Be more permissive for anime tags which may have special characters
        invalid_chars = ['\n', '\r', '\t']  # Only control characters
        for char in invalid_chars:
            if char in tag_name:
                return False
        
        # Check length (reasonable limits)
        tag_cleaned = tag_name.strip()
        if len(tag_cleaned) < 1 or len(tag_cleaned) > 100:
            return False
            
        return True

    def get_or_create_tags_bulk(self, tag_names: List[str]) -> Dict[str, Tag]:
        """Get or create multiple tags efficiently. Returns a mapping of original tag names to Tag objects."""
        if not tag_names:
            return {}
        
        # Filter out invalid tag names
        valid_tag_names = [name for name in tag_names if self._is_valid_tag_name(name)]
        if len(valid_tag_names) < len(tag_names):
            invalid_tags = [name for name in tag_names if not self._is_valid_tag_name(name)]
            self.logger.debug(f"Filtered out {len(invalid_tags)} invalid tag names", invalid_tags=invalid_tags)
        
        if not valid_tag_names:
            return {}
        
        # Ensure cache is populated
        if not self._tag_cache_valid:
            self.get_all_tags(use_cache=True)
        
        result = {}
        missing_tags = []
        
        # Check which tags exist in cache
        for tag_name in valid_tag_names:
            tag_name_lower = tag_name.lower()
            if tag_name_lower in self._tag_cache:
                result[tag_name] = self._tag_cache[tag_name_lower]
                performance_monitor.record_cache_hit()
                performance_monitor.record_tag_from_cache()
            else:
                missing_tags.append(tag_name)
                performance_monitor.record_cache_miss()
        
        # Create missing tags
        if missing_tags:
            performance_monitor.record_bulk_operation()
            self.logger.debug("Creating missing tags", count=len(missing_tags))
            for tag_name in missing_tags:
                try:
                    new_tag = self.create_tag(CreateTagRequest(name=tag_name.strip()))
                    result[tag_name] = new_tag
                    performance_monitor.record_tag_created()
                except Exception as e:
                    # Check if tag already exists (common race condition)
                    if "already exists" in str(e).lower():
                        # Refresh cache and try to find the tag
                        self.invalidate_tag_cache()
                        self.get_all_tags(use_cache=True)
                        tag_name_lower = tag_name.lower()
                        if tag_name_lower in self._tag_cache:
                            result[tag_name] = self._tag_cache[tag_name_lower]
                            self.logger.debug(f"Found existing tag after cache refresh: {tag_name}")
                        else:
                            self.logger.debug(f"Tag exists but not found in cache: {tag_name}")
                    else:
                        self.logger.debug("Failed to create tag", tag_name=tag_name, error=str(e))
                    # Continue with other tags
                    continue
        
        self.logger.debug("Bulk tag lookup/creation completed", 
                         requested=len(tag_names), 
                         found=len(result))
        return result
    
    def bulk_tag_assets(self, asset_ids: List[str], tag_ids: List[str]) -> None:
        """Bulk tag assets with multiple tags."""
        if not asset_ids or not tag_ids:
            return
        
        self.logger.debug(
            "Bulk tagging assets",
            asset_count=len(asset_ids),
            tag_count=len(tag_ids)
        )
        
        # Use the correct bulk tagging endpoint with PUT method
        request_data = BulkTagRequest(assetIds=asset_ids, tagIds=tag_ids)
        
        self._make_request(
            method="PUT",
            endpoint="/api/tags/assets",
            json_data=request_data.dict()
        )
        
        self.logger.debug(
            "Bulk tagged assets",
            asset_count=len(asset_ids),
            tag_count=len(tag_ids)
        )
    
    def tag_single_asset(self, asset_id: str, tag_ids: List[str]) -> None:
        """Tag a single asset with multiple tags."""
        if not tag_ids:
            return
        
        self.logger.debug("Tagging single asset", asset_id=asset_id, tag_count=len(tag_ids))
        
        # Use the bulk endpoint for single asset tagging (simpler approach)
        request_data = BulkTagRequest(assetIds=[asset_id], tagIds=tag_ids)
        
        self._make_request(
            method="PUT",
            endpoint="/api/tags/assets",
            json_data=request_data.dict()
        )
        
        self.logger.debug("Tagged single asset", asset_id=asset_id, tag_count=len(tag_ids))
    
    def get_assets_with_tag(self, tag_id: str, limit: Optional[int] = None) -> List[Asset]:
        """Get all assets that have a specific tag.
        
        Args:
            tag_id: The tag ID to search for
            limit: Maximum number of assets to return (default: 1000)
        """
        if limit is None:
            limit = 1000  # Default reasonable limit for tagged asset queries
            
        self.logger.debug(f"📊 Getting assets with tag {tag_id}, limit={limit}")
        
        # Use metadata search with specific tag filter
        response = self._make_request(
            method="POST",
            endpoint="/api/search/metadata",
            json_data={"tagIds": [tag_id]}
        )
        
        response_data = response.json()
        assets_section = response_data.get("assets", {})
        assets_list = assets_section.get("items", [])
        
        # Parse assets
        assets = []
        for asset_data in assets_list[:limit]:  # Respect limit
            try:
                assets.append(Asset(**asset_data))
            except Exception as e:
                self.logger.warning(f"⚠️  Failed to parse tagged asset: {e}")
                continue
        
        if len(assets_list) >= limit:
            self.logger.warning(
                f"Retrieved {len(assets)} tagged assets (limit: {limit}). "
                "There may be more assets with this tag."
            )
        
        return assets
    
    def get_asset(self, asset_id: str) -> Asset:
        """Get a specific asset by ID."""
        self.logger.debug("Getting asset", asset_id=asset_id)
        
        response = self._make_request(method="GET", endpoint=f"/api/assets/{asset_id}")
        asset_data = response.json()
        asset = Asset(**asset_data)
        
        self.logger.debug("Retrieved asset", asset_id=asset_id, name=asset.originalFileName)
        return asset
    
    def remove_tags_from_asset(self, asset_id: str, tag_ids: List[str]) -> None:
        """Remove specific tags from an asset."""
        if not tag_ids:
            return
        
        self.logger.debug("Removing tags from asset", asset_id=asset_id, tag_count=len(tag_ids))
        
        # Use DELETE method to remove tags from asset
        for tag_id in tag_ids:
            self._make_request(
                method="DELETE",
                endpoint=f"/api/tags/{tag_id}/assets/{asset_id}"
            )
        
        self.logger.info("Removed tags from asset", asset_id=asset_id, tag_count=len(tag_ids))
    
    def delete_tag(self, tag_id: str) -> None:
        """Delete a tag from Immich."""
        self.logger.debug("Deleting tag", tag_id=tag_id)
        
        self._make_request(method="DELETE", endpoint=f"/api/tags/{tag_id}")
        
        self.logger.info("Deleted tag", tag_id=tag_id)
    
    def test_connection(self) -> bool:
        """Test the connection to Immich."""
        try:
            # Try to get tags as a simple test
            self.get_all_tags()
            self.logger.info("Connection test successful")
            return True
        except Exception as e:
            self.logger.error("Connection test failed", error=str(e))
            return False
    
    def invalidate_tag_cache(self):
        """Invalidate the tag cache to force refresh on next access."""
        self._tag_cache_valid = False
        self._tag_cache.clear()
        self.logger.debug("Tag cache invalidated")
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
