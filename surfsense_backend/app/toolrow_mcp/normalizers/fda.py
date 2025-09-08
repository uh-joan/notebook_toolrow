"""FDA normalizer for drug labels and device information."""

from typing import Any, Dict, List

from ..types import Artifact, EntityRecord
from .base import BaseNormalizer


class FDANormalizer(BaseNormalizer):
    """Normalizer for FDA drug labels and device data."""
    
    def get_provider(self) -> str:
        return "fda"
    
    def normalize(self, raw_response: Dict[str, Any]) -> List[EntityRecord]:
        """Normalize FDA MCP response to EntityRecord format."""
        entities = []
        
        # Handle FDA drug label response format
        results = raw_response.get("results", [])
        if not isinstance(results, list):
            results = [raw_response]
        
        for item in results:
            try:
                entity = self._normalize_fda_item(item)
                if entity:
                    entities.append(entity)
            except Exception as e:
                # Log error but continue processing other items
                continue
        
        return entities
    
    def _normalize_fda_item(self, item: Dict[str, Any]) -> EntityRecord:
        """Normalize a single FDA item."""
        # Extract basic information
        canonical_id = self._extract_nda_number(item)
        title = self._extract_drug_name(item)
        
        # Build entity record
        entity = EntityRecord(
            provider="fda",
            kind="drug_label", 
            canonical_id=canonical_id,
            title=title,
            uri=self._build_fda_uri(canonical_id, item),
            summary=self._extract_summary(item),
            metadata=self._extract_metadata(item),
            artifacts=self._extract_artifacts(item)
        )
        
        return entity
    
    def _extract_nda_number(self, item: Dict[str, Any]) -> str:
        """Extract NDA/ANDA number from FDA response."""
        # Try multiple possible fields
        nda_fields = [
            "application_number",
            "nda_number", 
            "anda_number",
            "spl_id",
            "set_id"
        ]
        
        for field in nda_fields:
            value = item.get(field)
            if value:
                return str(value)
        
        # Fallback to generic ID
        return item.get("id", "unknown")
    
    def _extract_drug_name(self, item: Dict[str, Any]) -> str:
        """Extract drug name from FDA response."""
        # Try multiple possible fields
        name_fields = [
            "brand_name",
            "trade_name", 
            "product_name",
            "generic_name",
            "substance_name",
            "title"
        ]
        
        for field in name_fields:
            value = item.get(field)
            if value:
                return self.clean_text(str(value))
        
        return "Unknown Drug"
    
    def _build_fda_uri(self, canonical_id: str, item: Dict[str, Any]) -> str:
        """Build FDA URI for the drug label."""
        # Check if URI is provided directly
        direct_uri = item.get("uri", item.get("url"))
        if direct_uri:
            return direct_uri
        
        # Build FDA Orange Book or DailyMed URI
        if canonical_id.startswith(("NDA", "ANDA")):
            return f"https://www.accessdata.fda.gov/scripts/cder/ob/index.cfm"
        
        # DailyMed fallback
        set_id = item.get("set_id")
        if set_id:
            return f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}"
        
        return ""
    
    def _extract_summary(self, item: Dict[str, Any]) -> str:
        """Extract summary/description from FDA response."""
        summary_fields = [
            "indication",
            "description", 
            "purpose",
            "active_ingredient",
            "summary"
        ]
        
        for field in summary_fields:
            value = item.get(field)
            if value:
                return self.clean_text(str(value))
        
        return ""
    
    def _extract_metadata(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from FDA response."""
        metadata = {}
        
        # Extract relevant metadata fields
        metadata_fields = [
            "dosage_form",
            "route", 
            "strength",
            "manufacturer",
            "approval_date",
            "rx_otc",
            "therapeutic_equivalence",
            "active_ingredients"
        ]
        
        for field in metadata_fields:
            value = item.get(field)
            if value is not None:
                metadata[field] = value
        
        # Add provider-specific metadata
        metadata["provider"] = "fda"
        metadata["data_source"] = "FDA Orange Book / DailyMed"
        
        return metadata
    
    def _extract_artifacts(self, item: Dict[str, Any]) -> List[Artifact]:
        """Extract downloadable artifacts from FDA response."""
        artifacts = []
        
        # Check for label PDF
        label_url = item.get("label_url", item.get("pdf_url"))
        if label_url:
            artifacts.append(Artifact(
                type="pdf",
                path="",  # Will be set during download
                uri=label_url
            ))
        
        # Check for structured data
        if item.get("structured_data_url"):
            artifacts.append(Artifact(
                type="json",
                path="",
                uri=item["structured_data_url"]
            ))
        
        return artifacts
