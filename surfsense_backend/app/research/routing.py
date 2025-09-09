"""Intent detection and tool routing for Toolrow MCP integration."""

import re
import logging
from typing import Any, Dict, List

from app.toolrow_mcp.types import Intent, ToolCall

logger = logging.getLogger(__name__)


class IntentDetector:
    """Detects intent from user queries using rule-based patterns."""
    
    def __init__(self):
        # Drug search patterns
        self.drug_patterns = [
            r"(?:drugs?|medications?|medicines?|treatments?|therapies?).*(?:for|treating|treat)\s+(\w+)",
            r"(?:marketed|approved|available).*(?:drugs?|medications?).*(?:for|treating)\s+(\w+)",
            r"(?:what|which).*(?:drugs?|medications?).*(?:treat|treating|for)\s+(\w+)",
            r"(?:other|alternative).*(?:drugs?|medications?).*(?:market|available)",
        ]
        
        # Trial search patterns
        self.trial_patterns = [
            r"(?:clinical\s+)?trials?.*(?:for|treating|studying)\s+(\w+)",
            r"(?:active|ongoing|phase\s+\d+).*trials?",
            r"(?:studies?|research).*(?:for|on)\s+(\w+)",
        ]
        
        # Literature search patterns
        self.literature_patterns = [
            r"(?:recent|latest|new).*(?:literature|studies?|research|papers?|articles?)",
            r"(?:reviews?|meta-analyses?).*(?:on|about|for)\s+(\w+)",
            r"(?:published|scientific).*(?:literature|studies?)",
        ]
        
        # Filing search patterns
        self.filing_patterns = [
            r"(?:company|corporate).*(?:filings?|reports?)",
            r"(?:SEC|securities?).*(?:filings?|documents?)",
            r"(?:financial|earnings?).*(?:reports?|statements?)",
        ]
        
        # Health data patterns
        self.health_patterns = [
            r"(?:burden|prevalence|incidence|mortality|morbidity).*(?:of|for)\s+(\w+)",
            r"(?:epidemiolog|health\s+data|statistics?).*(?:for|on)\s+(\w+)",
            r"(?:WHO|health\s+organization).*(?:data|statistics?)",
        ]
        
        # Comprehensive query patterns (requiring completeness check)
        self.comprehensive_patterns = [
            r"(?:all|complete|full|entire|comprehensive|total).*(?:list|drugs?|medications?|treatments?|therapies?)",
            r"(?:what|which|how\s+many).*(?:drugs?|medications?|treatments?).*(?:are|exist|available|approved|marketed)",
            r"(?:available|approved|marketed|existing).*(?:drugs?|medications?|treatments?).*(?:for|treating|in\s+the)",
            r"(?:other|additional|more|alternative|remaining).*(?:drugs?|medications?|treatments?|options)",
            r"(?:complete|full|comprehensive).*(?:overview|summary|analysis).*(?:of|for)",
            r"(?:market|industry).*(?:overview|analysis|landscape).*(?:drugs?|medications?|treatments?)",
        ]
        
        # Region patterns
        self.region_patterns = [
            r"\b(US|USA|United States|America|American)\b",
            r"\b(EU|Europe|European)\b",
            r"\b(UK|United Kingdom|Britain|British)\b",
            r"\b(Canada|Canadian)\b",
            r"\b(Japan|Japanese)\b",
        ]
        
        # Time range patterns
        self.time_patterns = [
            r"(?:last|past|recent)\s+(\d+)\s+(years?|months?|weeks?)",
            r"(?:since|from)\s+(\d{4})",
            r"(?:in|during)\s+(\d{4})",
        ]
    
    async def detect(self, question: str) -> Intent:
        """Detect intent from user question."""
        question_lower = question.lower()
        
        intent = Intent(
            category="drug_search",  # Default
            entities=[],
            conditions=[],
            regions=[],
            time_range=None,
            confidence=0.5,
            requires_completeness_check=False
        )
        
        # Determine primary category
        category, confidence = self._classify_category(question_lower)
        intent["category"] = category
        intent["confidence"] = confidence
        
        # Extract entities and conditions
        entities = self._extract_entities(question_lower, category)
        intent["entities"] = entities
        intent["conditions"] = entities  # For medical queries, entities are often conditions
        
        # Extract regions
        regions = self._extract_regions(question_lower)
        intent["regions"] = regions
        
        # Extract time range
        time_range = self._extract_time_range(question_lower)
        intent["time_range"] = time_range
        
        # Check if this is a comprehensive query requiring completeness check
        is_comprehensive = self._is_comprehensive_query(question_lower)
        intent["requires_completeness_check"] = is_comprehensive
        
        logger.debug(f"Detected intent: {intent}")
        return intent
    
    def _classify_category(self, question: str) -> tuple[str, float]:
        """Classify the primary category of the question."""
        # Check patterns in order of specificity
        
        # Drug search
        for pattern in self.drug_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                return "drug_search", 0.8
        
        # Trial search
        for pattern in self.trial_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                return "trial_search", 0.8
        
        # Literature search
        for pattern in self.literature_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                return "literature_search", 0.7
        
        # Filing search
        for pattern in self.filing_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                return "filing_search", 0.7
        
        # Health data
        for pattern in self.health_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                return "health_data", 0.7
        
        # Default to drug search with low confidence
        return "drug_search", 0.3
    
    def _extract_entities(self, question: str, category: str) -> List[str]:
        """Extract entities based on category."""
        entities = []
        
        if category == "drug_search":
            # Extract drug names and conditions
            drug_matches = re.findall(r"(?:for|treating|treat)\s+([a-zA-Z\s]+?)(?:\s|$|[,.])", question)
            for match in drug_matches:
                clean_entity = match.strip().lower()
                if len(clean_entity) > 2:  # Filter out very short matches
                    entities.append(clean_entity)
        
        elif category == "trial_search":
            # Extract conditions and study types
            trial_matches = re.findall(r"(?:for|studying|on)\s+([a-zA-Z\s]+?)(?:\s|$|[,.])", question)
            for match in trial_matches:
                clean_entity = match.strip().lower()
                if len(clean_entity) > 2:
                    entities.append(clean_entity)
        
        elif category == "literature_search":
            # Extract research topics
            lit_matches = re.findall(r"(?:on|about|for)\s+([a-zA-Z\s]+?)(?:\s|$|[,.])", question)
            for match in lit_matches:
                clean_entity = match.strip().lower()
                if len(clean_entity) > 2:
                    entities.append(clean_entity)
        
        # Remove duplicates and clean up
        entities = list(set(entities))
        return entities[:5]  # Limit to top 5 entities
    
    def _extract_regions(self, question: str) -> List[str]:
        """Extract geographic regions from question."""
        regions = []
        
        for pattern in self.region_patterns:
            matches = re.findall(pattern, question, re.IGNORECASE)
            for match in matches:
                region = self._normalize_region(match.lower())
                if region not in regions:
                    regions.append(region)
        
        return regions
    
    def _normalize_region(self, region: str) -> str:
        """Normalize region names to standard codes."""
        region_map = {
            "us": "US",
            "usa": "US", 
            "united states": "US",
            "america": "US",
            "american": "US",
            "eu": "EU",
            "europe": "EU",
            "european": "EU",
            "uk": "UK",
            "united kingdom": "UK",
            "britain": "UK",
            "british": "UK",
            "canada": "CA",
            "canadian": "CA",
            "japan": "JP",
            "japanese": "JP",
        }
        
        return region_map.get(region.lower(), region.upper())
    
    def _extract_time_range(self, question: str) -> str | None:
        """Extract time range from question."""
        for pattern in self.time_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None
    
    def _is_comprehensive_query(self, question: str) -> bool:
        """Check if query requires comprehensive/complete information."""
        import re
        
        for pattern in self.comprehensive_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                logger.debug(f"Comprehensive pattern matched: {pattern}")
                return True
        
        return False


class ToolRouter:
    """Routes intents to appropriate Toolrow MCP tools."""
    
    def __init__(self):
        self.tool_mappings = {
            "drug_search": [
                "fda_info.labels.search",
                "fda_info.orange_book.search"
            ],
            "trial_search": [
                "ct_gov_studies.search",
                "ct_gov_studies.search_advanced"
            ],
            "literature_search": [
                "pubmed_articles.search",
                "pubmed_articles.search_advanced"
            ],
            "filing_search": [
                "sec_edgar.search",
                "sec_edgar.filings"
            ],
            "health_data": [
                "who_health.query",
                "who_health.indicators"
            ]
        }
    
    async def route(self, intent: Intent, canonicalized: Dict[str, Any]) -> List[ToolCall]:
        """Route intent to appropriate tool calls."""
        category = intent.get("category", "drug_search")
        tools = self.tool_mappings.get(category, [])
        
        if not tools:
            logger.warning(f"No tools mapped for category: {category}")
            return []
        
        tool_calls = []
        
        for tool in tools:
            params = await self._build_tool_params(tool, intent, canonicalized)
            if params:
                tool_call = ToolCall(
                    tool=tool,
                    params=params,
                    timeout_ms=30000
                )
                tool_calls.append(tool_call)
        
        logger.debug(f"Routed to {len(tool_calls)} tools for category {category}")
        return tool_calls
    
    async def _build_tool_params(
        self,
        tool: str,
        intent: Intent,
        canonicalized: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Build parameters for a specific tool based on intent."""
        params = {}
        
        if "fda" in tool:
            params = await self._build_fda_params(tool, intent, canonicalized)
        elif "ct_gov" in tool:
            params = await self._build_ct_gov_params(tool, intent, canonicalized)
        elif "pubmed" in tool:
            params = await self._build_pubmed_params(tool, intent, canonicalized)
        elif "sec" in tool:
            params = await self._build_sec_params(tool, intent, canonicalized)
        elif "who" in tool:
            params = await self._build_who_params(tool, intent, canonicalized)
        
        return params if params else None
    
    async def _build_fda_params(
        self,
        tool: str,
        intent: Intent,
        canonicalized: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build FDA tool parameters."""
        params = {}
        
        # Add condition/indication codes if available
        codes = canonicalized.get("codes", [])
        if codes:
            params["indication_codes"] = codes[:3]  # Limit to top 3
        
        # Add text-based conditions
        conditions = intent.get("conditions", [])
        if conditions:
            params["indication"] = conditions[0]  # Primary condition
        
        # Add region filter
        regions = intent.get("regions", [])
        if regions:
            params["region"] = regions[0]  # Primary region
        
        # Default to marketed drugs
        params["marketed"] = True
        
        return params
    
    async def _build_ct_gov_params(
        self,
        tool: str,
        intent: Intent,
        canonicalized: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build ClinicalTrials.gov tool parameters."""
        params = {}
        
        # Add condition codes
        codes = canonicalized.get("codes", [])
        if codes:
            params["condition_codes"] = codes[:3]
        
        # Add text-based conditions
        conditions = intent.get("conditions", [])
        if conditions:
            params["condition"] = conditions[0]
        
        # Add study status
        params["status"] = "active"  # Default to active trials
        
        # Add phase if mentioned in query
        # This could be enhanced to extract phase from intent
        
        return params
    
    async def _build_pubmed_params(
        self,
        tool: str,
        intent: Intent,
        canonicalized: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build PubMed tool parameters."""
        params = {}
        
        # Build search query from entities
        entities = intent.get("entities", [])
        if entities:
            params["query"] = " AND ".join(entities[:3])  # Combine top entities
        
        # Add time range filter
        time_range = intent.get("time_range")
        if time_range:
            params["date_range"] = time_range
        else:
            # Default to recent literature (last 24 months)
            params["date_range"] = "24 months"
        
        # Add filters for recent, high-quality literature
        params["filters"] = {
            "publication_types": ["Review", "Meta-Analysis", "Clinical Trial"],
            "sort": "relevance"
        }
        
        return params
    
    async def _build_sec_params(
        self,
        tool: str,
        intent: Intent,
        canonicalized: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build SEC EDGAR tool parameters."""
        params = {}
        
        # Extract company entities
        entities = intent.get("entities", [])
        if entities:
            params["company"] = entities[0]  # Primary company
        
        # Default form types
        params["forms"] = ["10-K", "10-Q", "8-K"]
        
        return params
    
    async def _build_who_params(
        self,
        tool: str,
        intent: Intent,
        canonicalized: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build WHO health data tool parameters."""
        params = {}
        
        # Map conditions to WHO indicator IDs
        # This would need a mapping table in practice
        conditions = intent.get("conditions", [])
        if conditions:
            params["indicator"] = conditions[0]
        
        # Add regions
        regions = intent.get("regions", [])
        if regions:
            params["countries"] = regions
        
        # Default to recent years
        params["years"] = "2020-2023"
        
        return params
