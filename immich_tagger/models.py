"""
Data models for the Immich Auto-Tagger service.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class Asset(BaseModel):
    """Immich asset model."""
    id: str
    type: str  # "IMAGE" or "VIDEO"
    originalPath: str
    originalFileName: str  # Changed from originalName
    fileCreatedAt: datetime
    fileModifiedAt: datetime
    checksum: str
    deviceAssetId: Optional[str] = None
    deviceId: Optional[str] = None
    ownerId: str
    libraryId: str
    originalMimeType: Optional[str] = None
    thumbhash: Optional[str] = None
    localDateTime: Optional[datetime] = None
    isFavorite: bool = False
    isArchived: bool = False
    isTrashed: bool = False
    visibility: Optional[str] = None
    duration: Optional[str] = None
    livePhotoVideoId: Optional[str] = None
    people: List[str] = []
    isOffline: bool = False
    hasMetadata: bool = False
    duplicateId: Optional[str] = None
    resized: Optional[bool] = None
    updatedAt: datetime


class Tag(BaseModel):
    """Immich tag model."""
    id: str
    name: str
    type: str = "OBJECT"
    userId: Optional[str] = None
    renameTagId: Optional[str] = None
    updatedAt: datetime
    createdAt: datetime


class TagPrediction(BaseModel):
    """Tag prediction from AI model."""
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    
    def __lt__(self, other):
        """Sort by confidence (descending)."""
        return self.confidence > other.confidence


class AssetProcessingResult(BaseModel):
    """Result of processing an asset."""
    asset_id: str
    success: bool
    tags_assigned: List[str] = []
    processing_time: float = 0.0
    error: Optional[str] = None


class BatchProcessingResult(BaseModel):
    """Result of processing a batch of assets."""
    batch_size: int
    successful: int
    failed: int
    total_tags_assigned: int
    processing_time: float
    results: List[AssetProcessingResult]


class HealthStatus(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    metrics: Dict[str, Any] = {}


class SearchFilters(BaseModel):
    """Filters for searching assets."""
    tagIds: Optional[List[str]] = None
    type: Optional[str] = None  # "IMAGE" or "VIDEO"
    size: Optional[int] = None
    order: Optional[str] = "DESC"  # "ASC" or "DESC"
    withArchived: bool = False
    withDeleted: bool = False


class BulkTagRequest(BaseModel):
    """Request for bulk tagging assets."""
    assetIds: List[str]
    tagIds: List[str]


class CreateTagRequest(BaseModel):
    """Request for creating a new tag."""
    name: str
    type: str = "OBJECT"
