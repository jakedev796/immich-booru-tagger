"""
AI tagging engine for anime-style image analysis.
"""

import os
import io
import tempfile
from typing import List, Optional
from PIL import Image
import numpy as np
from .models import TagPrediction
from .config import settings
from .logging import get_logger


class TaggingEngineError(Exception):
    """Custom exception for tagging engine errors."""
    pass


class BaseTaggingEngine:
    """Base class for tagging engines."""
    
    def __init__(self):
        self.logger = get_logger("tagging_engine")
        self.logger.info("Initializing tagging engine")
    
    def predict_tags(self, image_data: bytes) -> List[TagPrediction]:
        """Predict tags for an image. Must be implemented by subclasses."""
        raise NotImplementedError


class WD14TaggingEngine(BaseTaggingEngine):
    """WD-14 (Waifu Diffusion 1.4) tagging engine using wdtagger package."""
    
    def __init__(self):
        super().__init__()
        self.model_name = "SmilingWolf/wd-swinv2-tagger-v3"  # Default model from wdtagger
        self.logger.info("Initializing WD-14 engine", model_name=self.model_name)
        self._load_model()
    
    def _load_model(self):
        """Load the WD-14 model."""
        try:
            # Import here to avoid issues if not installed
            from wdtagger import Tagger
            
            # Initialize the tagger
            self.tagger = Tagger(model_repo=self.model_name)
            self.logger.info("WD-14 model loaded successfully")
            
        except ImportError:
            raise TaggingEngineError("wdtagger package not installed. Run: pip install wdtagger onnxruntime")
        except Exception as e:
            raise TaggingEngineError(f"Failed to load WD-14 model: {e}")
    
    def predict_tags(self, image_data: bytes) -> List[TagPrediction]:
        """Predict tags using WD-14 model."""
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Run WD-14 inference using wdtagger
            result = self.tagger.tag(image)
            
            # Convert results to TagPrediction objects
            predictions = []
            
            # Handle different output formats from wdtagger
            if isinstance(result, dict):
                # If result is a dict with tag:confidence pairs
                for tag, confidence in result.items():
                    if confidence >= settings.confidence_threshold:
                        predictions.append(TagPrediction(
                            name=tag,
                            confidence=float(confidence)
                        ))
            elif isinstance(result, list):
                # If result is a list of tags
                for tag in result:
                    predictions.append(TagPrediction(
                        name=tag,
                        confidence=0.8  # Default confidence for list format
                    ))
            elif isinstance(result, str):
                # If result is a string, parse it for tag:confidence pairs
                # Format: "tag1 (confidence1), tag2 (confidence2), ..."
                import re
                # Pattern to match "tag (confidence)" or just "tag"
                pattern = r'(\w+(?:_\w+)*)\s*\(([\d.]+)\)'
                matches = re.findall(pattern, result)
                
                for tag, confidence_str in matches:
                    try:
                        confidence = float(confidence_str)
                        if confidence >= settings.confidence_threshold:
                            predictions.append(TagPrediction(
                                name=tag,  # Just the tag name, no confidence
                                confidence=confidence
                            ))
                    except ValueError:
                        # If confidence parsing fails, skip this tag
                        continue
                
                # If no matches found with confidence, try to extract just tag names
                if not predictions:
                    # Split by comma and clean up
                    tags = [tag.strip() for tag in result.split(',')]
                    for tag in tags:
                        # Remove confidence part if present
                        tag = re.sub(r'\s*\([\d.]+\)', '', tag).strip()
                        if tag and len(tag) > 1:  # Skip empty or single-char tags
                            predictions.append(TagPrediction(
                                name=tag,  # Just the tag name
                                confidence=0.8  # Default confidence
                            ))
            else:
                # Handle wdtagger.Result object
                if hasattr(result, 'general_tag_data') and hasattr(result, 'character_tag_data') and hasattr(result, 'rating_data'):
                    # Parse general tags
                    if result.general_tag_data:
                        for tag, confidence in result.general_tag_data.items():
                            if confidence >= settings.confidence_threshold:
                                predictions.append(TagPrediction(
                                    name=tag,
                                    confidence=float(confidence)
                                ))
                    
                    # Parse character tags
                    if result.character_tag_data:
                        for tag, confidence in result.character_tag_data.items():
                            if confidence >= settings.confidence_threshold:
                                predictions.append(TagPrediction(
                                    name=tag,
                                    confidence=float(confidence)
                                ))
                    
                    # Parse rating tags (only take the highest confidence rating)
                    if result.rating_data:
                        max_rating = max(result.rating_data.items(), key=lambda x: x[1])
                        if max_rating[1] >= settings.confidence_threshold:
                            predictions.append(TagPrediction(
                                name=max_rating[0],
                                confidence=float(max_rating[1])
                            ))
                else:
                    # Fallback - try to convert to string and parse
                    self.logger.warning("Unexpected result format from wdtagger", result_type=type(result))
                    if result:
                        predictions.append(TagPrediction(
                            name=str(result),
                            confidence=0.8
                        ))
            
            # Sort by confidence (descending)
            predictions.sort(key=lambda x: x.confidence, reverse=True)
            
            self.logger.debug(
                "WD-14 predictions",
                total_predictions=len(predictions),
                confidence_threshold=settings.confidence_threshold,
                result_type=type(result)
            )
            
            return predictions
            
        except Exception as e:
            raise TaggingEngineError(f"WD-14 prediction failed: {e}")


class DeepDanbooruTaggingEngine(BaseTaggingEngine):
    """DeepDanbooru tagging engine."""
    
    def __init__(self):
        super().__init__()
        self.logger.info("Initializing DeepDanbooru engine")
        self._load_model()
    
    def _load_model(self):
        """Load the DeepDanbooru model."""
        try:
            # Import here to avoid issues if not installed
            import deepdanbooru as dd
            
            # Load the model
            self.model = dd.DeepDanbooru()
            self.logger.info("DeepDanbooru model loaded successfully")
            
        except ImportError:
            raise TaggingEngineError("deepdanbooru package not installed. Run: pip install deepdanbooru tensorflow")
        except Exception as e:
            raise TaggingEngineError(f"Failed to load DeepDanbooru model: {e}")
    
    def predict_tags(self, image_data: bytes) -> List[TagPrediction]:
        """Predict tags using DeepDanbooru model."""
        try:
            import deepdanbooru as dd
            
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Create temporary file for the image
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                image.save(temp_file.name, "JPEG")
                temp_path = temp_file.name
            
            try:
                # Run DeepDanbooru inference
                result = self.model.evaluate(temp_path, threshold=settings.confidence_threshold)
                
                # Convert results to TagPrediction objects
                predictions = []
                for tag, confidence in result.items():
                    if confidence >= settings.confidence_threshold:
                        predictions.append(TagPrediction(
                            name=tag,
                            confidence=float(confidence)
                        ))
                
                # Sort by confidence (descending)
                predictions.sort(reverse=True)
                
                self.logger.debug(
                    "DeepDanbooru predictions",
                    total_predictions=len(predictions),
                    confidence_threshold=settings.confidence_threshold
                )
                
                return predictions
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            
        except Exception as e:
            raise TaggingEngineError(f"DeepDanbooru prediction failed: {e}")


def create_tagging_engine() -> BaseTaggingEngine:
    """Factory function to create the appropriate tagging engine."""
    if settings.tagging_model == "wd14":
        return WD14TaggingEngine()
    elif settings.tagging_model == "deepdanbooru":
        return DeepDanbooruTaggingEngine()
    else:
        raise ValueError(f"Unsupported tagging model: {settings.tagging_model}")
