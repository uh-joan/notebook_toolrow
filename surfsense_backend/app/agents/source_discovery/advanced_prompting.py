"""Advanced prompting techniques for Claude Discovery Agent."""

import re
from typing import Dict, List, Optional, Tuple
from enum import Enum


class QueryType(Enum):
    """Different types of discovery queries."""
    CLINICAL_RESEARCH = "clinical_research"
    DRUG_DISCOVERY = "drug_discovery" 
    REGULATORY_COMPLIANCE = "regulatory_compliance"
    LITERATURE_REVIEW = "literature_review"
    COMPARATIVE_ANALYSIS = "comparative_analysis"
    GENERAL_RESEARCH = "general_research"


class QueryComplexity(Enum):
    """Complexity levels for queries."""
    SIMPLE = "simple"          # Single concept, direct lookup
    MODERATE = "moderate"      # 2-3 concepts, may need multiple tools
    COMPLEX = "complex"        # Multiple concepts, requires synthesis
    COMPREHENSIVE = "comprehensive"  # Broad scope, needs extensive research


class AdvancedPromptGenerator:
    """Generates optimized prompts based on query analysis."""
    
    def __init__(self):
        self.query_patterns = {
            QueryType.CLINICAL_RESEARCH: [
                r"\b(clinical trial|study|trial|research|patient|treatment)\b",
                r"\b(phase [1-4]|randomized|controlled|efficacy|safety)\b",
                r"\b(recruitment|enrollment|inclusion|exclusion)\b"
            ],
            QueryType.DRUG_DISCOVERY: [
                r"\b(drug|medication|compound|pharmaceutical|therapy)\b",
                r"\b(mechanism|target|pathway|interaction|biomarker)\b",
                r"\b(dosage|administration|formulation)\b"
            ],
            QueryType.REGULATORY_COMPLIANCE: [
                r"\b(fda|approval|regulation|compliance|guideline)\b",
                r"\b(clearance|submission|requirement|standard)\b",
                r"\b(labeling|indication|contraindication)\b"
            ],
            QueryType.LITERATURE_REVIEW: [
                r"\b(research|literature|study|paper|publication)\b",
                r"\b(meta-analysis|systematic review|evidence)\b",
                r"\b(findings|results|conclusions|outcomes)\b"
            ],
            QueryType.COMPARATIVE_ANALYSIS: [
                r"\b(compare|comparison|versus|vs|difference)\b",
                r"\b(alternative|option|choice|better|worse)\b",
                r"\b(advantage|disadvantage|benefit|risk)\b"
            ]
        }
        
        self.complexity_indicators = {
            QueryComplexity.SIMPLE: [
                r"^(what is|define|find|lookup|get)\b",
                r"\b(icd.{0,5}code|code for|definition of)\b"
            ],
            QueryComplexity.MODERATE: [
                r"\band\b.*\band\b",  # Multiple concepts with "and"
                r"\b(how|why|when|where)\b",
                r"\b(related to|associated with|linked to)\b"
            ],
            QueryComplexity.COMPLEX: [
                r"\b(analyze|evaluate|assess|compare|contrast)\b",
                r"\b(comprehensive|detailed|thorough|extensive)\b",
                r"\b(impact|effect|influence|relationship)\b"
            ],
            QueryComplexity.COMPREHENSIVE: [
                r"\b(all|every|complete|full|entire)\b.*\b(information|data|research)\b",
                r"\b(overview|survey|landscape|state of the art)\b",
                r"\b(trends|developments|advances|progress)\b"
            ]
        }
    
    def analyze_query(self, query: str) -> Tuple[QueryType, QueryComplexity]:
        """Analyze query to determine type and complexity."""
        query_lower = query.lower()
        
        # Determine query type
        query_type = QueryType.GENERAL_RESEARCH
        max_matches = 0
        
        for qtype, patterns in self.query_patterns.items():
            matches = sum(1 for pattern in patterns if re.search(pattern, query_lower, re.IGNORECASE))
            if matches > max_matches:
                max_matches = matches
                query_type = qtype
        
        # Determine complexity
        complexity = QueryComplexity.SIMPLE
        
        for comp_level, patterns in self.complexity_indicators.items():
            if any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in patterns):
                complexity = comp_level
                break
        
        return query_type, complexity
    
    def generate_system_prompt(
        self, 
        query_type: QueryType, 
        complexity: QueryComplexity,
        available_tools: List[Dict],
        context: Optional[str] = None
    ) -> str:
        """Generate optimized system prompt based on query analysis."""
        
        # Base prompt
        base_prompt = """You are SourceBook Discover, an expert research assistant specializing in biomedical and regulatory research."""
        
        # Type-specific instructions
        type_instructions = self._get_type_specific_instructions(query_type)
        
        # Complexity-specific strategy
        complexity_strategy = self._get_complexity_strategy(complexity)
        
        # Tool usage guidance
        tool_guidance = self._get_tool_usage_guidance(query_type, complexity, available_tools)
        
        # Context integration
        context_section = f"\n\nCONTEXTUAL AWARENESS:\n{context}" if context else ""
        
        # Performance optimization hints
        perf_hints = self._get_performance_hints(complexity)
        
        return f"""{base_prompt}

{type_instructions}

{complexity_strategy}

{tool_guidance}

RESPONSE FORMATTING:
- Start with a brief executive summary (1-2 sentences)
- Organize findings by data source when using multiple tools
- Include confidence indicators (High/Medium/Low) for key findings
- Provide source URLs and access dates when available
- End with actionable next steps or follow-up questions

{perf_hints}{context_section}"""
    
    def _get_type_specific_instructions(self, query_type: QueryType) -> str:
        """Get specialized instructions based on query type."""
        instructions = {
            QueryType.CLINICAL_RESEARCH: """
CLINICAL RESEARCH FOCUS:
- Prioritize peer-reviewed studies and registered clinical trials
- Include study phases, patient populations, and methodology details
- Note recruitment status and geographic locations for trials
- Highlight primary and secondary endpoints
- Consider safety profiles and adverse event reporting""",
            
            QueryType.DRUG_DISCOVERY: """
DRUG DISCOVERY FOCUS:
- Emphasize mechanism of action and pharmacokinetics
- Include FDA approval status and regulatory pathways
- Note drug-drug interactions and contraindications
- Consider different formulations and administration routes
- Highlight biomarkers and patient selection criteria""",
            
            QueryType.REGULATORY_COMPLIANCE: """
REGULATORY COMPLIANCE FOCUS:
- Focus on current FDA guidelines and requirements
- Include regulatory pathways (510k, PMA, NDA, BLA)
- Note compliance deadlines and submission requirements
- Consider international regulatory harmonization (ICH, EMA)
- Highlight recent regulatory changes or guidance updates""",
            
            QueryType.LITERATURE_REVIEW: """
LITERATURE REVIEW FOCUS:
- Prioritize systematic reviews and meta-analyses
- Include publication dates and journal impact factors
- Note study limitations and bias assessments
- Consider evidence quality and strength of recommendations
- Highlight gaps in current knowledge""",
            
            QueryType.COMPARATIVE_ANALYSIS: """
COMPARATIVE ANALYSIS FOCUS:
- Structure comparisons using standardized criteria
- Include head-to-head studies when available
- Note differences in patient populations and outcomes
- Consider cost-effectiveness and real-world evidence
- Highlight clinical significance of differences""",
            
            QueryType.GENERAL_RESEARCH: """
GENERAL RESEARCH APPROACH:
- Cast a wide net initially to understand the landscape
- Identify the most relevant data sources for the topic
- Balance breadth and depth based on available information
- Synthesize findings from multiple authoritative sources"""
        }
        
        return instructions.get(query_type, instructions[QueryType.GENERAL_RESEARCH])
    
    def _get_complexity_strategy(self, complexity: QueryComplexity) -> str:
        """Get strategy based on query complexity."""
        strategies = {
            QueryComplexity.SIMPLE: """
SIMPLE QUERY STRATEGY:
- Use the most direct tool for the specific lookup
- Provide concise, factual answers with primary sources
- Include brief context but avoid over-elaboration
- Single tool use is often sufficient""",
            
            QueryComplexity.MODERATE: """
MODERATE COMPLEXITY STRATEGY:
- Use 2-3 complementary tools to provide comprehensive coverage
- Cross-reference findings between sources when possible
- Provide structured answers with clear sections
- Include both primary data and contextual information""",
            
            QueryComplexity.COMPLEX: """
COMPLEX QUERY STRATEGY:
- Use parallel tool execution for comprehensive data gathering
- Synthesize information across multiple databases
- Provide analytical insights beyond just data presentation
- Include comparative analysis and evidence weighing
- Consider multiple perspectives and interpretations""",
            
            QueryComplexity.COMPREHENSIVE: """
COMPREHENSIVE QUERY STRATEGY:
- Execute broad searches across all relevant databases
- Organize findings into thematic categories
- Provide both overview and detailed findings
- Include trend analysis and future directions
- Generate extensive follow-up questions for deeper exploration
- Consider interdisciplinary connections"""
        }
        
        return strategies[complexity]
    
    def _get_tool_usage_guidance(self, query_type: QueryType, complexity: QueryComplexity, tools: List[Dict]) -> str:
        """Get tool-specific usage guidance."""
        tool_names = [tool.get("name", "") for tool in tools]
        
        guidance = "TOOL SELECTION GUIDANCE:\n"
        
        # Type-specific tool priorities
        if query_type == QueryType.CLINICAL_RESEARCH:
            guidance += "- Prioritize: ct_gov_studies for trials, pubmed_articles for research\n"
            guidance += "- Secondary: nlm_ct_codes for medical terminology\n"
        elif query_type == QueryType.DRUG_DISCOVERY:
            guidance += "- Prioritize: fda_drug_info for approvals, pubmed_articles for research\n"
            guidance += "- Secondary: ct_gov_studies for ongoing trials\n"
        elif query_type == QueryType.REGULATORY_COMPLIANCE:
            guidance += "- Prioritize: fda_drug_info, sec_filings for regulatory documents\n"
            guidance += "- Secondary: pubmed_articles for regulatory science\n"
        
        # Complexity-specific tool strategies
        if complexity in [QueryComplexity.COMPLEX, QueryComplexity.COMPREHENSIVE]:
            guidance += "- Use parallel tool execution when appropriate\n"
            guidance += "- Cross-reference findings between databases\n"
        
        # Available tools reminder
        guidance += f"\nAVAILABLE TOOLS: {', '.join(tool_names)}"
        
        return guidance
    
    def _get_performance_hints(self, complexity: QueryComplexity) -> str:
        """Get performance optimization hints."""
        if complexity in [QueryComplexity.COMPLEX, QueryComplexity.COMPREHENSIVE]:
            return """
PERFORMANCE OPTIMIZATION:
- Use token-efficient tool calls with focused parameters
- Leverage parallel execution for independent searches
- Structure responses for easy scanning and reference
- Balance comprehensiveness with response time"""
        else:
            return """
PERFORMANCE OPTIMIZATION:
- Use direct, focused tool calls
- Provide concise but complete answers
- Minimize unnecessary elaboration"""


# Global instance for easy access
advanced_prompt_generator = AdvancedPromptGenerator()