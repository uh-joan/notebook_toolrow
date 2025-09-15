"""Response formatting and citation generation for Claude Discovery Agent."""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class CitationManager:
    """Manages citations and source attribution for research results."""
    
    def __init__(self):
        self.citations: List[Dict[str, Any]] = []
        self.citation_counter = 1
    
    def add_citation(self, tool_name: str, result_content: str, query_params: Dict[str, Any] = None) -> int:
        """Add a citation and return its ID."""
        citation_id = self.citation_counter
        self.citation_counter += 1
        
        # Extract source information based on tool type
        source_info = self._extract_source_info(tool_name, result_content, query_params)
        
        citation = {
            "id": citation_id,
            "tool": tool_name,
            "source_type": self._get_source_type(tool_name),
            "title": source_info.get("title", "Research Data"),
            "url": source_info.get("url"),
            "date_accessed": datetime.now().isoformat(),
            "query_params": query_params or {},
            "content_preview": result_content[:200] + "..." if len(result_content) > 200 else result_content
        }
        
        self.citations.append(citation)
        return citation_id
    
    def _extract_source_info(self, tool_name: str, content: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extract source information from tool results."""
        info = {"title": "Research Data", "url": None}
        
        try:
            # Try to parse JSON content
            if content.startswith("{") or content.startswith("["):
                data = json.loads(content)
                
                if tool_name == "ct_gov_studies":
                    info["title"] = "ClinicalTrials.gov Search Results"
                    if params and "query" in params:
                        info["url"] = f"https://clinicaltrials.gov/search?term={params['query'].replace(' ', '+')}"
                
                elif tool_name == "pubmed_articles":
                    info["title"] = "PubMed Literature Search"
                    if params and "query" in params:
                        info["url"] = f"https://pubmed.ncbi.nlm.nih.gov/?term={params['query'].replace(' ', '+')}"
                
                elif tool_name == "nlm_ct_codes":
                    info["title"] = "Medical Coding Systems"
                    info["url"] = "https://lhncbc.nlm.nih.gov/RxNav/"
                
                elif tool_name == "fda_drug_info":
                    info["title"] = "FDA Drug Information"
                    info["url"] = "https://www.fda.gov/drugs/"
                
                elif tool_name == "sec_filings":
                    info["title"] = "SEC Financial Filings"
                    info["url"] = "https://www.sec.gov/edgar/"
                
                elif tool_name == "who_health_data":
                    info["title"] = "WHO Global Health Data"
                    info["url"] = "https://www.who.int/data"
                    
        except json.JSONDecodeError:
            # Not JSON, use content directly
            pass
        
        return info
    
    def _get_source_type(self, tool_name: str) -> str:
        """Get the source type for display."""
        mapping = {
            "ct_gov_studies": "Clinical Trials",
            "pubmed_articles": "Scientific Literature", 
            "nlm_ct_codes": "Medical Codes",
            "fda_drug_info": "FDA Database",
            "sec_filings": "SEC Filings",
            "who_health_data": "WHO Health Data"
        }
        return mapping.get(tool_name, "Research Database")
    
    def get_citations_summary(self) -> str:
        """Get formatted citations summary."""
        if not self.citations:
            return ""
        
        summary = "\n## 📚 Sources\n\n"
        for citation in self.citations:
            source_line = f"[{citation['id']}] **{citation['source_type']}**: {citation['title']}"
            if citation['url']:
                source_line += f" - [{citation['url']}]({citation['url']})"
            summary += source_line + "\n"
        
        return summary
    
    def get_citations_list(self) -> List[Dict[str, Any]]:
        """Get list of citations for API responses."""
        return self.citations.copy()


class ResponseFormatter:
    """Formats Claude's responses with proper structure and citations."""
    
    def __init__(self):
        self.citation_manager = CitationManager()
    
    def format_research_response(
        self, 
        original_query: str,
        claude_response: str, 
        tool_results: List[Dict[str, Any]],
        tool_uses: List[Dict[str, Any]] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Format Claude's response with citations and structure."""
        
        # Add citations for each tool result
        citations = []
        for i, result in enumerate(tool_results):
            if not result.get("is_error") and result.get("content"):
                tool_name = self._extract_tool_name(result, tool_uses, i)
                query_params = self._extract_query_params(tool_uses, i) if tool_uses else {}
                
                citation_id = self.citation_manager.add_citation(
                    tool_name, 
                    str(result["content"]),
                    query_params
                )
                citations.append(citation_id)
        
        # Format the response with citations
        formatted_response = self._structure_response(
            original_query,
            claude_response, 
            citations,
            tool_results
        )
        
        # Add citations section
        citations_summary = self.citation_manager.get_citations_summary()
        if citations_summary:
            formatted_response += citations_summary
        
        return formatted_response, self.citation_manager.get_citations_list()
    
    def _extract_tool_name(self, result: Dict[str, Any], tool_uses: List[Dict[str, Any]] = None, index: int = 0) -> str:
        """Extract tool name from result or tool uses."""
        if tool_uses and index < len(tool_uses):
            return tool_uses[index].get("name", "unknown_tool")
        
        # Try to infer from content
        content = str(result.get("content", "")).lower()
        if "clinical" in content or "trial" in content:
            return "ct_gov_studies"
        elif "icd" in content or "code" in content:
            return "nlm_ct_codes"
        elif "pubmed" in content or "pmid" in content:
            return "pubmed_articles"
        elif "fda" in content:
            return "fda_drug_info"
        else:
            return "research_tool"
    
    def _extract_query_params(self, tool_uses: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
        """Extract query parameters from tool use."""
        if tool_uses and index < len(tool_uses):
            return tool_uses[index].get("input", {})
        return {}
    
    def _structure_response(
        self, 
        query: str, 
        claude_response: str, 
        citation_ids: List[int],
        tool_results: List[Dict[str, Any]]
    ) -> str:
        """Structure the response with proper formatting."""
        
        # Clean and enhance Claude's response
        sections = []
        
        # Add executive summary if Claude's response is long
        if len(claude_response) > 1000:
            sections.append("## 🔍 Research Summary")
            summary = self._extract_summary(claude_response)
            if summary:
                sections.append(summary)
        
        # Add main response content
        sections.append("## 📊 Detailed Findings")
        
        # Process Claude's response and add citation markers
        enhanced_response = self._add_citation_markers(claude_response, citation_ids)
        sections.append(enhanced_response)
        
        # Add data source breakdown
        if tool_results:
            sections.append(self._create_source_breakdown(tool_results))
        
        return "\n\n".join(sections)
    
    def _extract_summary(self, response: str) -> Optional[str]:
        """Extract or generate a summary from Claude's response."""
        # Look for existing summary sections
        lines = response.split('\n')
        summary_lines = []
        in_summary = False
        
        for line in lines:
            if any(keyword in line.lower() for keyword in ['summary', 'overview', 'key findings']):
                in_summary = True
                continue
            elif in_summary and line.strip():
                if line.startswith('#') or line.startswith('##'):
                    break
                summary_lines.append(line.strip())
            elif in_summary and not line.strip() and summary_lines:
                break
        
        if summary_lines:
            return ' '.join(summary_lines)
        
        # Generate summary from first paragraph
        first_paragraph = response.split('\n\n')[0]
        if len(first_paragraph) < 500:
            return first_paragraph
        
        return None
    
    def _add_citation_markers(self, response: str, citation_ids: List[int]) -> str:
        """Add citation markers to relevant sections of the response."""
        if not citation_ids:
            return response
        
        # Add citations to the end of paragraphs that seem to reference data
        enhanced = response
        
        # Look for patterns that indicate data references
        data_patterns = [
            r'(studies? show|research indicates|data suggests|findings reveal)',
            r'(according to|based on|results from)',
            r'(\d+%|\d+ patients?|\d+ cases?|\d+ trials?)',
            r'(clinical trials?|research papers?|studies?)'
        ]
        
        for pattern in data_patterns:
            matches = list(re.finditer(pattern, enhanced, re.IGNORECASE))
            for match in reversed(matches):  # Reverse to maintain positions
                end_pos = match.end()
                # Find end of sentence
                next_period = enhanced.find('.', end_pos)
                if next_period != -1:
                    citation_marker = f" [{','.join(map(str, citation_ids))}]"
                    if citation_marker not in enhanced[next_period:next_period+20]:
                        enhanced = enhanced[:next_period] + citation_marker + enhanced[next_period:]
                    break  # Only add one citation per pattern
        
        return enhanced
    
    def _create_source_breakdown(self, tool_results: List[Dict[str, Any]]) -> str:
        """Create a breakdown of data sources used."""
        breakdown = "## 🗃️ Data Sources Used\n\n"
        
        successful_results = [r for r in tool_results if not r.get("is_error")]
        if not successful_results:
            return ""
        
        breakdown += f"This research drew from **{len(successful_results)}** authoritative database(s):\n\n"
        
        source_types = set()
        for result in successful_results:
            content = str(result.get("content", "")).lower()
            if "clinical" in content:
                source_types.add("🏥 Clinical Trials Database")
            elif "pubmed" in content or "research" in content:
                source_types.add("📚 Scientific Literature")
            elif "icd" in content or "code" in content:
                source_types.add("🏷️ Medical Coding Systems")
            elif "fda" in content:
                source_types.add("🏛️ FDA Regulatory Database")
            else:
                source_types.add("🗄️ Research Database")
        
        for source_type in sorted(source_types):
            breakdown += f"- {source_type}\n"
        
        return breakdown