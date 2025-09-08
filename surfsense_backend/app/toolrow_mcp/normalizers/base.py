"""Base normalizer for Toolrow MCP provider responses."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..types import EntityRecord


class BaseNormalizer(ABC):
    """Base class for provider-specific normalizers."""
    
    @abstractmethod
    def normalize(self, raw_response: Dict[str, Any]) -> List[EntityRecord]:
        """Normalize raw MCP response to EntityRecord format."""
        pass
    
    @abstractmethod
    def get_provider(self) -> str:
        """Get the provider name this normalizer handles."""
        pass
    
    def extract_artifacts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract artifact information from raw response."""
        # Default implementation - override in subclasses
        return []
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""
        
        # Basic text cleaning
        cleaned = text.strip()
        # Remove excessive whitespace
        cleaned = " ".join(cleaned.split())
        return cleaned
    
    def extract_canonical_id(self, raw_data: Dict[str, Any]) -> str:
        """Extract canonical ID from raw response."""
        # Default implementation - override in subclasses
        return raw_data.get("id", raw_data.get("canonical_id", ""))
    
    def build_uri(self, canonical_id: str, raw_data: Dict[str, Any]) -> str:
        """Build URI for the entity."""
        # Default implementation - override in subclasses
        return raw_data.get("uri", raw_data.get("url", ""))
