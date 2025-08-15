"""
Immich API client for interacting with the Immich instance.
"""

import time
from typing import List, Optional, Dict, Any
import httpx
from .models import Asset, Tag, SearchFilters, BulkTagRequest, CreateTagRequest
from .config import settings
from .logging import get_logger


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
        
        # HTTP client with retry logic
        self.client = httpx.Client(
            timeout=self.timeout,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            }
        )
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Make an HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data
                )
                response.raise_for_status()
                return response
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < self.max_retries:
                    self.logger.warning(
                        "Server error, retrying",
                        status_code=e.response.status_code,
                        attempt=attempt + 1,
                        max_retries=self.max_retries
                    )
                    time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
                    continue
                else:
                    self.logger.error(
                        "HTTP request failed",
                        method=method,
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
                    self.logger.error("Request failed", error=str(e))
                    raise ImmichAPIError(f"Request failed: {e}")
    
    def search_assets(self, filters: SearchFilters) -> List[Asset]:
        """Search for assets using the Immich API."""
        self.logger.debug("Searching assets", filters=filters.dict())
        
        response = self._make_request(
            method="POST",
            endpoint="/api/search/random",
            json_data=filters.dict(exclude_none=True)
        )
        
        assets_data = response.json()
        assets = [Asset(**asset_data) for asset_data in assets_data]
        
        self.logger.info("Found assets", count=len(assets))
        return assets
    
    def get_unprocessed_assets(self, processed_tag_id: Optional[str] = None, limit: int = 100) -> List[Asset]:
        """Get assets that haven't been processed yet."""
        # For now, get all assets and filter in the processor
        # The Immich API doesn't support negative tag filtering with "!" syntax
        filters = SearchFilters(size=limit)
        
        return self.search_assets(filters)
    
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
                        "Server error, retrying",
                        status_code=e.response.status_code,
                        attempt=attempt + 1,
                        max_retries=self.max_retries
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
                    self.logger.error("Request failed", error=str(e))
                    raise ImmichAPIError(f"Request failed: {e}")
    
    def get_all_tags(self) -> List[Tag]:
        """Get all tags from Immich."""
        self.logger.debug("Fetching all tags")
        
        response = self._make_request(method="GET", endpoint="/api/tags")
        tags_data = response.json()
        tags = [Tag(**tag_data) for tag_data in tags_data]
        
        self.logger.info("Fetched tags", count=len(tags))
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
        
        self.logger.info("Created tag", tag_id=tag.id, name=tag.name)
        return tag
    
    def get_or_create_tag(self, tag_name: str) -> Tag:
        """Get an existing tag or create it if it doesn't exist."""
        # First, try to find existing tag
        all_tags = self.get_all_tags()
        for tag in all_tags:
            if tag.name.lower() == tag_name.lower():
                return tag
        
        # Create new tag if not found
        tag_request = CreateTagRequest(name=tag_name)
        return self.create_tag(tag_request)
    
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
        
        self.logger.info(
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
        
        self.logger.info("Tagged single asset", asset_id=asset_id, tag_count=len(tag_ids))
    
    def get_assets_with_tag(self, tag_id: str) -> List[Asset]:
        """Get all assets that have a specific tag."""
        self.logger.debug("Getting assets with tag", tag_id=tag_id)
        
        # Search for assets with the specific tag
        filters = SearchFilters(tagIds=[tag_id])
        return self.search_assets(filters)
    
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
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
