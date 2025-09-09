"""Coverage analysis engine for knowledge gap detection."""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from difflib import SequenceMatcher

from app.toolrow_mcp.types import EntityRecord, Intent

logger = logging.getLogger(__name__)


class CoverageAnalysis:
    """Results of coverage analysis comparing documents vs live data."""
    
    def __init__(
        self,
        found_entities: List[str],
        live_entities: List[str], 
        matched_entities: List[str],
        missing_entities: List[str],
        completeness_score: float,
        confidence: float = 1.0
    ):
        self.found_entities = found_entities  # Entities found in user documents
        self.live_entities = live_entities    # Entities found in live data
        self.matched_entities = matched_entities  # Entities present in both
        self.missing_entities = missing_entities  # Entities missing from documents
        self.completeness_score = completeness_score  # 0.0 to 1.0
        self.confidence = confidence  # How confident we are in this analysis
        
    @property
    def has_gaps(self) -> bool:
        """True if there are missing entities (knowledge gaps)."""
        return len(self.missing_entities) > 0
        
    @property 
    def is_comprehensive(self) -> bool:
        """True if documents cover most/all available entities."""
        return self.completeness_score >= 0.8
        
    def __repr__(self):
        return (f"CoverageAnalysis(found={len(self.found_entities)}, "
                f"live={len(self.live_entities)}, "
                f"missing={len(self.missing_entities)}, "
                f"score={self.completeness_score:.2f})")


class EntityExtractor:
    """Extracts entities from documents and live data for comparison."""
    
    def __init__(self):
        # Common drug name patterns
        self.drug_patterns = [
            r'\b([A-Z][a-z]+(?:vir|mab|nib|stat|pril|sartan|pam|zole|mycin))\b',  # Drug suffixes
            r'\b([A-Z][a-z]{3,})\s*\([^)]+\)',  # Brand name (generic name) 
            r'\b([A-Z]{2,}[0-9]*)\b',  # Abbreviations like FDA, WHO, etc.
        ]
        
        # Medical condition patterns  
        self.condition_patterns = [
            r'\b(diabetes|obesity|hypertension|depression|anxiety|cancer|asthma)\b',
            r'\b([a-z]+osis|[a-z]+itis|[a-z]+oma)\b',  # Medical suffixes
        ]
    
    def extract_from_documents(self, documents: List[Any], intent: Intent) -> List[str]:
        """Extract entities from user documents based on intent."""
        entities = set()
        
        for doc in documents:
            # Get document content
            content = self._get_document_content(doc)
            if not content:
                continue
                
            # Extract based on intent category
            if intent.get("category") == "drug_search":
                entities.update(self._extract_drug_entities(content))
            elif intent.get("category") == "trial_search":
                entities.update(self._extract_trial_entities(content))
            # Add more categories as needed
                
        logger.info(f"Extracted {len(entities)} entities from {len(documents)} documents")
        return list(entities)
    
    def extract_from_live_data(self, live_records: List[EntityRecord], intent: Intent) -> List[str]:
        """Extract entities from live MCP data."""
        entities = set()
        
        for record in live_records:
            # Extract from title
            if record.get("title"):
                entities.update(self._extract_entities_from_text(record["title"], intent))
            
            # Extract from metadata
            if record.get("metadata"):
                for key, value in record["metadata"].items():
                    if isinstance(value, str):
                        entities.update(self._extract_entities_from_text(value, intent))
                        
        logger.info(f"Extracted {len(entities)} entities from {len(live_records)} live records")
        return list(entities)
    
    def _get_document_content(self, doc: Any) -> str:
        """Extract text content from document object."""
        # Handle different document formats
        if hasattr(doc, 'content'):
            return doc.content
        elif hasattr(doc, 'text'):
            return doc.text
        elif isinstance(doc, dict):
            return doc.get('content', doc.get('text', ''))
        elif isinstance(doc, str):
            return doc
        else:
            return str(doc)
    
    def _extract_drug_entities(self, text: str) -> Set[str]:
        """Extract drug names from text."""
        entities = set()
        
        for pattern in self.drug_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities.update(matches)
        
        # Common drug names (could be expanded with drug database)
        known_drugs = ['wegovy', 'ozempic', 'saxenda', 'qsymia', 'contrave', 'orlistat', 'xenical', 'alli', 'imcivree', 'zepbound']
        for drug in known_drugs:
            if drug.lower() in text.lower():
                entities.add(drug.title())
                
        return entities
    
    def _extract_trial_entities(self, text: str) -> Set[str]:
        """Extract clinical trial entities from text."""
        entities = set()
        
        # Trial phase patterns
        trial_patterns = [
            r'(?:phase\s+)?(?:I{1,3}|[123])\s*(?:trial|study)',
            r'(?:randomized|controlled|double-blind)\s+(?:trial|study)',
        ]
        
        for pattern in trial_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities.update(matches)
            
        return entities
    
    def _extract_entities_from_text(self, text: str, intent: Intent) -> Set[str]:
        """Extract entities from text based on intent."""
        category = intent.get("category", "drug_search")
        
        if category == "drug_search":
            return self._extract_drug_entities(text)
        elif category == "trial_search":
            return self._extract_trial_entities(text)
        else:
            # Generic entity extraction
            entities = set()
            # Extract capitalized words (potential entities)
            words = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
            entities.update(words)
            return entities


class CoverageAnalyzer:
    """Analyzes coverage gaps between documents and live data."""
    
    def __init__(self):
        self.entity_extractor = EntityExtractor()
        self.similarity_threshold = 0.8  # For fuzzy matching
    
    async def analyze_coverage(
        self,
        documents: List[Any],
        live_records: List[EntityRecord],
        intent: Intent
    ) -> CoverageAnalysis:
        """
        Analyze coverage by comparing entities in documents vs live data.
        
        Args:
            documents: User's document collection
            live_records: Live data from MCP tools
            intent: Detected intent with category and requirements
            
        Returns:
            CoverageAnalysis with gap detection results
        """
        logger.info(f"Analyzing coverage for {len(documents)} docs vs {len(live_records)} live records")
        
        # Extract entities from both sources
        doc_entities = self.entity_extractor.extract_from_documents(documents, intent)
        live_entities = self.entity_extractor.extract_from_live_data(live_records, intent)
        
        # Normalize and deduplicate entities
        doc_entities_norm = [self._normalize_entity(e) for e in doc_entities]
        live_entities_norm = [self._normalize_entity(e) for e in live_entities]
        
        # Find matches using fuzzy matching
        matched_entities, missing_entities = self._find_gaps(doc_entities_norm, live_entities_norm)
        
        # Calculate completeness score
        if len(live_entities_norm) > 0:
            completeness_score = len(matched_entities) / len(live_entities_norm)
        else:
            completeness_score = 1.0 if len(doc_entities_norm) > 0 else 0.0
        
        # Calculate confidence based on data quality
        confidence = self._calculate_confidence(documents, live_records, intent)
        
        analysis = CoverageAnalysis(
            found_entities=doc_entities_norm,
            live_entities=live_entities_norm,
            matched_entities=matched_entities,
            missing_entities=missing_entities,
            completeness_score=completeness_score,
            confidence=confidence
        )
        
        logger.info(f"Coverage analysis: {analysis}")
        return analysis
    
    def _normalize_entity(self, entity: str) -> str:
        """Normalize entity for comparison."""
        # Convert to lowercase, remove extra spaces
        normalized = re.sub(r'\s+', ' ', entity.strip().lower())
        # Remove common suffixes/prefixes
        normalized = re.sub(r'\b(the|a|an)\s+', '', normalized)
        return normalized
    
    def _find_gaps(self, doc_entities: List[str], live_entities: List[str]) -> Tuple[List[str], List[str]]:
        """Find matched and missing entities using fuzzy matching."""
        matched = []
        missing = []
        
        for live_entity in live_entities:
            best_match = self._find_best_match(live_entity, doc_entities)
            if best_match and self._similarity_score(live_entity, best_match) >= self.similarity_threshold:
                matched.append(live_entity)
            else:
                missing.append(live_entity)
        
        return matched, missing
    
    def _find_best_match(self, target: str, candidates: List[str]) -> Optional[str]:
        """Find best matching candidate for target entity."""
        if not candidates:
            return None
            
        best_score = 0
        best_match = None
        
        for candidate in candidates:
            score = self._similarity_score(target, candidate)
            if score > best_score:
                best_score = score
                best_match = candidate
                
        return best_match
    
    def _similarity_score(self, a: str, b: str) -> float:
        """Calculate similarity score between two entities."""
        return SequenceMatcher(None, a, b).ratio()
    
    def _calculate_confidence(self, documents: List[Any], live_records: List[EntityRecord], intent: Intent) -> float:
        """Calculate confidence in the coverage analysis."""
        confidence = 1.0
        
        # Reduce confidence if we have very few documents
        if len(documents) < 2:
            confidence *= 0.7
            
        # Reduce confidence if we have very few live records
        if len(live_records) < 2:
            confidence *= 0.8
            
        # Reduce confidence if intent confidence is low
        intent_confidence = intent.get("confidence", 0.5)
        confidence *= intent_confidence
        
        return max(0.1, min(1.0, confidence))  # Clamp between 0.1 and 1.0
