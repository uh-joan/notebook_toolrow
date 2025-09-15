"""Claude tool definitions mapped from Toolrow MCP tools."""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ClaudeToolMapper:
    """Maps Toolrow MCP tools to Claude tool format."""
    
    def __init__(self, toolrow_token: str):
        self.toolrow_token = toolrow_token
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl = 300  # 5 minutes
    
    async def get_claude_tools(self, use_cache: bool = True, query: str = "") -> List[Dict[str, Any]]:
        """Get available tools in Claude format, optionally filtered by query relevance."""
        if use_cache and self._is_cache_valid():
            logger.debug("Using cached Claude tools")
            all_tools = self._tools_cache or []
        else:
            # Try to fetch tools from Toolrow MCP first, fallback to hardcoded if needed
            all_tools = await self._fetch_toolrow_tools()
            
            # If MCP returns no tools, fallback to hardcoded schema
            if not all_tools:
                logger.info("MCP returned no tools, falling back to hardcoded schema")
                all_tools = await self._load_hardcoded_tools()
            
            # Update cache
            self._tools_cache = all_tools
            self._cache_timestamp = asyncio.get_event_loop().time()
        
        # Apply smart tool selection and compression
        optimized_tools = self._optimize_tools_for_query(all_tools, query)
        
        logger.info(f"Loaded {len(optimized_tools)}/{len(all_tools)} optimized Claude tools")
        return optimized_tools
    
    def _is_cache_valid(self) -> bool:
        """Check if the cached tools are still valid."""
        if not self._tools_cache or not self._cache_timestamp:
            return False
        
        current_time = asyncio.get_event_loop().time()
        return (current_time - self._cache_timestamp) < self._cache_ttl
    
    def _optimize_tools_for_query(self, all_tools: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Optimize tools for the given query by selecting relevant tools and compressing schemas."""
        if not query:
            # If no query provided, return compressed versions of all tools
            return [self._compress_tool_schema(tool) for tool in all_tools]
        
        # Smart tool selection based on query keywords
        relevant_tools = self._select_relevant_tools(all_tools, query)
        
        # Compress the selected tools
        return [self._compress_tool_schema(tool) for tool in relevant_tools]
    
    def _select_relevant_tools(self, all_tools: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Select tools most relevant to the query using semantic similarity."""
        try:
            # Use semantic similarity approach
            return self._select_tools_by_similarity(all_tools, query)
        except Exception as e:
            logger.warning(f"Semantic selection failed, using fallback: {e}")
            return self._select_tools_fallback(all_tools, query)
    
    def _select_tools_by_similarity(self, all_tools: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Select tools using semantic similarity between query and tool descriptions."""
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            logger.info("sentence-transformers not available, using description matching")
            return self._select_tools_by_description(all_tools, query)
        
        # Initialize embedding model (lightweight)
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Create tool descriptions for embedding
        tool_texts = []
        for tool in all_tools:
            # Combine name and description for better matching
            text = f"{tool.get('name', '').replace('_', ' ')}: {tool.get('description', '')}"
            tool_texts.append(text)
        
        # Get embeddings
        query_embedding = model.encode([query])
        tool_embeddings = model.encode(tool_texts)
        
        # Calculate similarities
        similarities = cosine_similarity(query_embedding, tool_embeddings)[0]
        
        # Score and rank tools
        tool_scores = list(zip(all_tools, similarities))
        tool_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Select top 3-4 tools with similarity > threshold
        threshold = 0.15  # Adjust based on testing
        selected_tools = [tool for tool, score in tool_scores[:4] if score > threshold]
        
        # Ensure at least 2 tools are selected
        if len(selected_tools) < 2:
            selected_tools = [tool for tool, _ in tool_scores[:3]]
        
        logger.info(f"Selected {len(selected_tools)} tools by semantic similarity for: {query[:50]}...")
        return selected_tools
    
    def _select_tools_by_description(self, all_tools: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Fallback: Select tools by matching words in descriptions."""
        query_words = set(query.lower().split())
        
        tool_scores = []
        for tool in all_tools:
            tool_name = tool.get("name", "").replace("_", " ").lower()
            tool_desc = tool.get("description", "").lower()
            tool_text = f"{tool_name} {tool_desc}"
            
            # Count word matches
            tool_words = set(tool_text.split())
            matches = len(query_words.intersection(tool_words))
            
            # Boost score for name matches
            name_matches = len(query_words.intersection(set(tool_name.split())))
            score = matches + (name_matches * 2)
            
            tool_scores.append((tool, score))
        
        # Sort and select top tools
        tool_scores.sort(key=lambda x: x[1], reverse=True)
        selected_tools = [tool for tool, score in tool_scores[:4] if score > 0]
        
        # Ensure minimum selection
        if len(selected_tools) < 2:
            selected_tools = [tool for tool, _ in tool_scores[:3]]
        
        logger.info(f"Selected {len(selected_tools)} tools by description matching for: {query[:50]}...")
        return selected_tools
    
    def _select_tools_fallback(self, all_tools: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Final fallback: Return most generally useful tools."""
        # Define generally useful combinations
        if any(word in query.lower() for word in ["medical", "health", "clinical", "drug", "disease", "icd"]):
            preferred = ["nlm_ct_codes", "ct_gov_studies", "pubmed_articles"]
        elif any(word in query.lower() for word in ["financial", "company", "business", "stock", "sec"]):
            preferred = ["sec_edgar", "pubmed_articles", "nlm_ct_codes"]
        else:
            preferred = ["nlm_ct_codes", "ct_gov_studies", "pubmed_articles"]
        
        selected_tools = []
        for tool_name in preferred:
            tool = next((t for t in all_tools if t.get("name") == tool_name), None)
            if tool:
                selected_tools.append(tool)
        
        # Fill up to 3 tools if needed
        while len(selected_tools) < 3 and len(selected_tools) < len(all_tools):
            for tool in all_tools:
                if tool not in selected_tools:
                    selected_tools.append(tool)
                    break
        
        logger.info(f"Selected {len(selected_tools)} tools by fallback for: {query[:50]}...")
        return selected_tools[:3]
    
    def _compress_tool_schema(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Compress tool schema by removing verbose descriptions and examples."""
        compressed_tool = tool.copy()
        
        # Shorten the main description
        if len(compressed_tool.get("description", "")) > 100:
            compressed_tool["description"] = compressed_tool["description"][:100] + "..."
        
        # Compress input schema
        if "input_schema" in compressed_tool:
            compressed_tool["input_schema"] = self._compress_schema_properties(
                compressed_tool["input_schema"]
            )
        
        return compressed_tool
    
    def _compress_schema_properties(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively compress schema properties."""
        compressed_schema = schema.copy()
        
        if "properties" in compressed_schema:
            compressed_properties = {}
            for prop_name, prop_def in compressed_schema["properties"].items():
                compressed_prop = prop_def.copy()
                
                # Shorten descriptions
                if "description" in compressed_prop and len(compressed_prop["description"]) > 60:
                    compressed_prop["description"] = compressed_prop["description"][:60] + "..."
                
                # Keep only essential enum values (first 5)
                if "enum" in compressed_prop and len(compressed_prop["enum"]) > 5:
                    compressed_prop["enum"] = compressed_prop["enum"][:5] + ["...more"]
                
                compressed_properties[prop_name] = compressed_prop
            
            compressed_schema["properties"] = compressed_properties
        
        return compressed_schema
    
    async def _load_hardcoded_tools(self) -> List[Dict[str, Any]]:
        """Load tools from hardcoded schema file."""
        try:
            from pathlib import Path
            schema_file = Path(__file__).parent / "toolrow_tools_schema.json"
            
            with open(schema_file, 'r') as f:
                tools_data = json.load(f)
            
            # Convert tools to Claude API format (prioritize input_schema over inputSchema)
            claude_tools = []
            for tool in tools_data:
                # Convert to Claude API format - prefer input_schema over inputSchema
                input_schema = None
                if "input_schema" in tool:
                    input_schema = tool["input_schema"]
                elif "inputSchema" in tool:
                    input_schema = tool["inputSchema"]
                else:
                    # Ensure every tool has an input_schema field
                    input_schema = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                
                claude_tool = {
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": input_schema
                }
                
                claude_tools.append(claude_tool)
            
            logger.info(f"Successfully loaded {len(claude_tools)} tools from hardcoded schema")
            return claude_tools
            
        except Exception as e:
            logger.error(f"Error loading hardcoded tools: {e}")
            return []
    
    async def _fetch_toolrow_tools(self) -> List[Dict[str, Any]]:
        """Fetch available tools from Toolrow MCP server using existing infrastructure."""
        try:
            # Import here to avoid circular imports
            from app.toolrow_mcp.client import toolrow_mcp_manager
            
            logger.info("🔧 Fetching tools from MCP server via toolrow_mcp_manager")
            
            # Use the existing MCP manager to list tools
            raw_tools = await toolrow_mcp_manager.list_available_tools()
            
            if not raw_tools:
                logger.info("MCP server returned no tools")
                return []
            
            logger.info(f"✅ MCP server returned {len(raw_tools)} tools")
            
            # Convert tools from MCP format to Claude format
            claude_tools = []
            for i, tool in enumerate(raw_tools):
                input_schema = tool.get("inputSchema", {})
                
                # Debug logging for first tool
                if i == 0:
                    logger.info(f"🔍 First tool debug - Name: {tool.get('name', 'MISSING')}")
                    logger.info(f"🔍 First tool keys: {list(tool.keys())}")
                    logger.info(f"🔍 Has inputSchema: {'inputSchema' in tool}")
                    logger.info(f"🔍 inputSchema type: {type(input_schema)}")
                    logger.info(f"🔍 inputSchema keys: {list(input_schema.keys()) if isinstance(input_schema, dict) else 'NOT_DICT'}")
                
                # Ensure we have a valid input_schema
                if not input_schema or not isinstance(input_schema, dict):
                    logger.warning(f"⚠️ Tool {tool.get('name', 'unknown')} has invalid inputSchema, using default")
                    input_schema = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                
                # Debug the exact schema structure being used
                if i == 0:  # Log first tool's complete schema
                    logger.info(f"🔍 Building tool {tool.get('name')} with input_schema: {input_schema}")
                
                claude_tool = {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "input_schema": input_schema
                }
                
                # Log the final tool structure for first tool
                if i == 0:
                    logger.info(f"🔍 Final claude_tool structure keys: {list(claude_tool.keys())}")
                    logger.info(f"🔍 Final input_schema type: {type(claude_tool.get('input_schema', 'MISSING'))}")
                    logger.info(f"🔍 Final input_schema content: {claude_tool.get('input_schema', 'MISSING')}")
                claude_tools.append(claude_tool)
            
            logger.info(f"Successfully converted {len(claude_tools)} MCP tools to Claude format")
            return claude_tools
            
        except Exception as e:
            logger.error(f"Error fetching tools from MCP server: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    def _convert_to_claude_format(self, toolrow_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert Toolrow tools to Claude tool format with enhanced descriptions."""
        claude_tools = []
        
        for tool in toolrow_tools:
            tool_name = tool.get("name", "unknown")
            
            # Get enhanced description based on tool type
            enhanced_description = self._get_enhanced_description(tool_name, tool.get("description", ""))
            
            claude_tool = {
                "name": tool_name,
                "description": enhanced_description,
                "input_schema": self._normalize_input_schema(tool.get("inputSchema", {}))
            }
            
            claude_tools.append(claude_tool)
            logger.debug(f"Converted tool: {tool_name}")
        
        return claude_tools
    
    def _get_enhanced_description(self, tool_name: str, original_description: str) -> str:
        """Get enhanced descriptions based on PRD specifications."""
        enhanced_descriptions = {
            "ct_gov_studies": (
                "Search clinical trials from ClinicalTrials.gov. Use this for finding ongoing studies, "
                "trial statuses, recruitment information, and research protocols. Supports complex queries "
                "including condition names, intervention types, study phases, and geographic locations."
            ),
            "nlm_ct_codes": (
                "Search medical coding systems including ICD-10-CM diagnosis codes, HCPCS procedure codes, "
                "MeSH terms, and clinical vocabularies. Essential for medical research, billing codes, "
                "and standardized medical terminology."
            ),
            "pubmed_articles": (
                "Search PubMed scientific literature and research papers. Use for finding peer-reviewed "
                "studies, systematic reviews, clinical research, and academic publications on medical topics."
            ),
            "fda_drug_info": (
                "Search FDA drug and device databases. Use for finding drug approvals, safety information, "
                "regulatory filings, adverse event reports, and device clearances."
            ),
            "sec_filings": (
                "Search SEC financial filings including 10-K, 10-Q, 8-K forms and other regulatory documents. "
                "Use for financial research, company information, and regulatory compliance data."
            ),
            "who_health_data": (
                "Search WHO global health statistics and indicators. Use for finding international health data, "
                "disease surveillance information, and global health trends."
            )
        }
        
        return enhanced_descriptions.get(tool_name, original_description or f"Research tool: {tool_name}")
    
    def _normalize_input_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize input schema for Claude compatibility."""
        if not schema or not isinstance(schema, dict):
            return {
                "type": "object",
                "properties": {},
                "required": []
            }
        
        # Ensure schema has required fields
        normalized = {
            "type": schema.get("type", "object"),
            "properties": schema.get("properties", {}),
        }
        
        # Add required fields if present
        if "required" in schema:
            normalized["required"] = schema["required"]
        
        return normalized
    
    def get_tool_by_name(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific tool by name from cache."""
        if not self._tools_cache:
            return None
        
        for tool in self._tools_cache:
            if tool["name"] == tool_name:
                return tool
        
        return None


class ClaudeToolRegistry:
    """Registry for Claude tool definitions with static fallback tools."""
    
    @staticmethod
    def get_fallback_tools() -> List[Dict[str, Any]]:
        """Get fallback tools when Toolrow is not available."""
        return [
            {
                "name": "ct_gov_studies",
                "description": "Search clinical trials from ClinicalTrials.gov. Use this for finding ongoing studies, trial statuses, recruitment information, and research protocols. Supports complex queries including condition names, intervention types, study phases, and geographic locations.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query (e.g., 'diabetes trials recruiting in California')"
                        },
                        "pageSize": {
                            "type": "integer",
                            "description": "Number of results to return (1-100, default: 10)"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["recruiting", "active", "completed", "any"],
                            "description": "Study recruitment status filter"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "nlm_ct_codes",
                "description": "Search medical coding systems including ICD-10-CM diagnosis codes, HCPCS procedure codes, MeSH terms, and clinical vocabularies. Essential for medical research, billing codes, and standardized medical terminology.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["icd-10-cm", "hcpcs", "mesh", "npi"],
                            "description": "Coding system to search"
                        },
                        "terms": {
                            "type": "string",
                            "description": "Search terms for medical codes"
                        }
                    },
                    "required": ["method", "terms"]
                }
            },
            {
                "name": "pubmed_articles",
                "description": "Search PubMed scientific literature and research papers. Use for finding peer-reviewed studies, systematic reviews, clinical research, and academic publications on medical topics.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for PubMed literature"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "fda_drug_info",
                "description": "Search FDA drug and device databases. Use for finding drug approvals, safety information, regulatory filings, adverse event reports, and device clearances.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Drug or device name to search"
                        },
                        "search_type": {
                            "type": "string",
                            "enum": ["drug", "device", "all"],
                            "description": "Type of FDA data to search"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    
    @staticmethod
    def get_system_prompt_tools_section(tools: List[Dict[str, Any]]) -> str:
        """Generate the tools section for the system prompt."""
        tool_descriptions = []
        
        for tool in tools:
            name = tool["name"]
            desc = tool["description"]
            tool_descriptions.append(f"- {name}: {desc}")
        
        return "\n".join(tool_descriptions)