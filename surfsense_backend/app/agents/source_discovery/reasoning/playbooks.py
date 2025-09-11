"""
Playbooks for query expansion and refinement strategies.

Provides systematic approaches to handle different search scenarios:
- Zero or sparse results (expansion strategies)
- Overbroad results (refinement strategies)
- Tool chaining for complex queries
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import date

from .models import SearchState, ToolResult
from .config import ReasoningConfig
from .utils import year_window, extract_terms, normalize_search_terms

logger = logging.getLogger(__name__)


class ExpansionPlaybook:
    """Strategies for expanding queries when results are sparse."""
    
    @staticmethod
    def get_code_mapping_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Expand query using medical code mapping."""
        strategies = []
        
        # Extract medical terms for code mapping
        medical_terms = []
        for term in state.working_terms:
            # Look for medical conditions, diseases, etc.
            if any(keyword in term.lower() for keyword in 
                   ['diabetes', 'obesity', 'hypertension', 'cancer', 'heart']):
                medical_terms.append(term)
        
        if not medical_terms and state.working_terms:
            medical_terms = [state.working_terms[0]]  # Use first term as fallback
        
        for term in medical_terms[:3]:  # Limit to prevent too many calls
            strategies.append({
                "name": "icd10_mapping",
                "tool": "nlm_ct_codes",
                "params": {
                    "method": "icd-10-cm",
                    "terms": term
                },
                "reason": f"Map '{term}' to ICD-10 codes for broader medical search"
            })
        
        return strategies
    
    @staticmethod
    def get_terminology_suggestion_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Expand query using terminology suggestions."""
        strategies = []
        
        # Use ct.gov suggest to normalize and expand terminology
        if state.working_terms:
            primary_term = " ".join(state.working_terms[:2])  # Combine first 2 terms
            strategies.append({
                "name": "ct_suggest",
                "tool": "ct_gov_studies.suggest",
                "params": {
                    "q": primary_term
                },
                "reason": f"Get terminology suggestions for '{primary_term}'"
            })
        
        return strategies
    
    @staticmethod
    def get_temporal_expansion_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Expand query by broadening time windows."""
        strategies = []
        
        # Broaden search window for trials
        broad_window = year_window(config.broaden_years_back)
        query_terms = " ".join(state.working_terms[:3])
        
        strategies.append({
            "name": "temporal_expansion",
            "tool": "ct_gov_studies.search",
            "params": {
                "q": query_terms,
                "start_date_from": broad_window["from"],
                "status": "any",  # Include all statuses
                "pageSize": 20  # Get more results
            },
            "reason": f"Broaden time window to last {config.broaden_years_back} years"
        })
        
        return strategies
    
    @staticmethod
    def get_synonym_expansion_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Expand query using medical synonyms and related terms."""
        strategies = []
        
        # Common medical synonym mappings
        synonym_map = {
            "diabetes": ["diabetes mellitus", "diabetic", "DM", "T1D", "T2D"],
            "obesity": ["obese", "overweight", "BMI", "adiposity"],
            "hypertension": ["high blood pressure", "HTN", "blood pressure"],
            "cancer": ["carcinoma", "tumor", "malignant", "neoplasm"],
            "heart disease": ["cardiac", "cardiovascular", "CVD", "myocardial"],
            "depression": ["depressive disorder", "major depression", "MDD"],
            "anxiety": ["anxiety disorder", "GAD", "panic disorder"]
        }
        
        expanded_terms = set(state.working_terms)
        
        for term in state.working_terms:
            term_lower = term.lower()
            for key, synonyms in synonym_map.items():
                if key in term_lower:
                    expanded_terms.update(synonyms[:2])  # Add top 2 synonyms
        
        if expanded_terms != set(state.working_terms):
            # Create search with expanded terms
            expanded_query = " ".join(list(expanded_terms)[:5])  # Limit to 5 terms
            strategies.append({
                "name": "synonym_expansion", 
                "tool": "ct_gov_studies.search",
                "params": {
                    "q": expanded_query,
                    "pageSize": 15
                },
                "reason": f"Expand with synonyms: {list(expanded_terms - set(state.working_terms))}"
            })
        
        return strategies
    
    @staticmethod
    def get_cross_tool_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Try different tools for cross-validation."""
        strategies = []
        attempted_tools = set(state.attempted_strategies)
        
        # If we tried trials, try literature
        if "ct_gov_studies" not in [s for s in attempted_tools if "ct_gov" in s]:
            primary_query = " ".join(state.working_terms[:3])
            strategies.append({
                "name": "literature_search",
                "tool": "pubmed_articles",
                "params": {
                    "query": primary_query,
                    "max_results": 10
                },
                "reason": "Cross-validate with literature search"
            })
        
        # If we haven't tried FDA, try it for drug-related queries
        if "fda" not in attempted_tools and any(
            drug_term in " ".join(state.working_terms).lower() 
            for drug_term in ["drug", "medication", "therapy", "treatment"]
        ):
            strategies.append({
                "name": "fda_search",
                "tool": "fda_info", 
                "params": {
                    "query": state.working_terms[0]
                },
                "reason": "Search FDA for drug/treatment information"
            })
        
        return strategies


class RefinementPlaybook:
    """Strategies for refining queries when results are too broad."""
    
    @staticmethod
    def get_phase_refinement_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Refine by focusing on specific trial phases."""
        strategies = []
        
        # Focus on Phase 2/3 trials (more mature)
        query_terms = " ".join(state.working_terms[:3])
        strategies.append({
            "name": "phase_refinement",
            "tool": "ct_gov_studies.search",
            "params": {
                "q": query_terms,
                "phase": "Phase 2,Phase 3",
                "pageSize": 15
            },
            "reason": "Focus on Phase 2/3 trials for more mature research"
        })
        
        return strategies
    
    @staticmethod
    def get_status_refinement_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Refine by focusing on specific trial statuses."""
        strategies = []
        
        query_terms = " ".join(state.working_terms[:3])
        
        # Focus on active/recruiting trials
        strategies.append({
            "name": "status_refinement",
            "tool": "ct_gov_studies.search",
            "params": {
                "q": query_terms,
                "status": "recruiting,active,enrolling",
                "pageSize": 15
            },
            "reason": "Focus on active/recruiting trials"
        })
        
        return strategies
    
    @staticmethod
    def get_temporal_refinement_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Refine by narrowing time windows."""
        strategies = []
        
        # Narrow to more recent studies
        narrow_window = year_window(config.default_years_back // 2)  # Half the default window
        query_terms = " ".join(state.working_terms[:3])
        
        strategies.append({
            "name": "temporal_refinement",
            "tool": "ct_gov_studies.search",
            "params": {
                "q": query_terms,
                "start_date_from": narrow_window["from"],
                "pageSize": 15
            },
            "reason": f"Focus on recent studies (last {config.default_years_back // 2} years)"
        })
        
        return strategies
    
    @staticmethod
    def get_geographic_refinement_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Refine by geographic constraints."""
        strategies = []
        
        query_terms = " ".join(state.working_terms[:3])
        
        # Focus on US studies if not specified
        if "us" not in query_terms.lower() and "united states" not in query_terms.lower():
            strategies.append({
                "name": "geographic_refinement",
                "tool": "ct_gov_studies.search",
                "params": {
                    "q": query_terms,
                    "location": "United States",
                    "pageSize": 15
                },
                "reason": "Focus on US-based studies"
            })
        
        return strategies
    
    @staticmethod
    def get_precision_refinement_strategy(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Refine by increasing search precision."""
        strategies = []
        
        # Use more specific, longer query
        if len(state.working_terms) >= 2:
            precise_query = " ".join(state.working_terms[:4])  # Use more terms for precision
            strategies.append({
                "name": "precision_refinement",
                "tool": "ct_gov_studies.search", 
                "params": {
                    "q": f'"{precise_query}"',  # Quoted for exact phrase matching
                    "pageSize": 10
                },
                "reason": "Use exact phrase matching for higher precision"
            })
        
        return strategies


class ChainingPlaybook:
    """Strategies for chaining tools in complex workflows."""
    
    @staticmethod
    def get_drug_to_trials_chain(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Chain from drug lookup to related trials."""
        chain_steps = []
        
        # Step 1: FDA drug lookup
        if state.working_terms:
            drug_term = next((term for term in state.working_terms 
                            if any(suffix in term.lower() for suffix in 
                                 ['mab', 'pril', 'sartan', 'olol', 'ide'])), 
                           state.working_terms[0])
            
            chain_steps.append({
                "name": "drug_lookup",
                "tool": "fda_info",
                "params": {"query": drug_term},
                "reason": f"Look up FDA information for '{drug_term}'"
            })
        
        # Step 2: Related trials (will be executed after drug lookup)
        return chain_steps
    
    @staticmethod
    def get_condition_to_codes_to_trials_chain(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Chain from condition to codes to trials."""
        chain_steps = []
        
        if state.working_terms:
            condition = state.working_terms[0]
            
            # Step 1: Map condition to ICD codes
            chain_steps.append({
                "name": "condition_to_codes",
                "tool": "nlm_ct_codes",
                "params": {
                    "method": "icd-10-cm",
                    "terms": condition
                },
                "reason": f"Map '{condition}' to ICD-10 codes"
            })
        
        return chain_steps
    
    @staticmethod
    def get_trials_to_literature_chain(state: SearchState, config: ReasoningConfig) -> List[Dict[str, Any]]:
        """Chain from trials to related literature."""
        chain_steps = []
        
        if state.working_terms:
            query_terms = " ".join(state.working_terms[:3])
            
            # Literature search based on trial terms
            chain_steps.append({
                "name": "trials_to_literature",
                "tool": "pubmed_articles",
                "params": {
                    "query": f"{query_terms} clinical trial",
                    "max_results": 10
                },
                "reason": f"Find literature related to '{query_terms}' trials"
            })
        
        return chain_steps


class PlaybookOrchestrator:
    """Orchestrates the selection and execution of playbook strategies."""
    
    def __init__(self, config: ReasoningConfig):
        self.config = config
        self.expansion = ExpansionPlaybook()
        self.refinement = RefinementPlaybook()
        self.chaining = ChainingPlaybook()
    
    def get_expansion_strategies(self, state: SearchState, current_hits: int) -> List[Dict[str, Any]]:
        """Get appropriate expansion strategies based on current state."""
        strategies = []
        
        if current_hits == 0:
            # Zero hits - try aggressive expansion
            strategies.extend(self.expansion.get_code_mapping_strategy(state, self.config))
            strategies.extend(self.expansion.get_terminology_suggestion_strategy(state, self.config))
            strategies.extend(self.expansion.get_synonym_expansion_strategy(state, self.config))
            strategies.extend(self.expansion.get_temporal_expansion_strategy(state, self.config))
        else:
            # Some hits but too few - try moderate expansion
            strategies.extend(self.expansion.get_terminology_suggestion_strategy(state, self.config))
            strategies.extend(self.expansion.get_temporal_expansion_strategy(state, self.config))
            strategies.extend(self.expansion.get_cross_tool_strategy(state, self.config))
        
        return strategies[:3]  # Limit to top 3 strategies
    
    def get_refinement_strategies(self, state: SearchState, current_hits: int) -> List[Dict[str, Any]]:
        """Get appropriate refinement strategies based on current state."""
        strategies = []
        
        # Try refinement strategies in order of effectiveness
        strategies.extend(self.refinement.get_phase_refinement_strategy(state, self.config))
        strategies.extend(self.refinement.get_status_refinement_strategy(state, self.config))
        strategies.extend(self.refinement.get_temporal_refinement_strategy(state, self.config))
        strategies.extend(self.refinement.get_precision_refinement_strategy(state, self.config))
        
        return strategies[:2]  # Limit to top 2 strategies
    
    def get_chaining_strategies(self, state: SearchState, query_analysis) -> List[Dict[str, Any]]:
        """Get appropriate chaining strategies based on query analysis."""
        strategies = []
        
        # Determine chaining based on query type and entities
        if query_analysis.query_type == "drugs":
            strategies.extend(self.chaining.get_drug_to_trials_chain(state, self.config))
        elif query_analysis.query_type == "trials":
            strategies.extend(self.chaining.get_trials_to_literature_chain(state, self.config))
        elif any(entity_type in ["conditions"] for entity_type in query_analysis.entities):
            strategies.extend(self.chaining.get_condition_to_codes_to_trials_chain(state, self.config))
        
        return strategies
    
    def select_best_strategies(self, available_strategies: List[Dict[str, Any]], 
                             state: SearchState, max_strategies: int = 3) -> List[Dict[str, Any]]:
        """Select the best strategies based on current state and history."""
        # Filter out already attempted strategies
        attempted = set(state.attempted_strategies)
        
        filtered_strategies = [
            strategy for strategy in available_strategies
            if strategy["name"] not in attempted
        ]
        
        # Prioritize based on strategy effectiveness (could be learned over time)
        priority_order = [
            "icd10_mapping",
            "ct_suggest", 
            "phase_refinement",
            "synonym_expansion",
            "temporal_expansion",
            "status_refinement"
        ]
        
        # Sort by priority
        def strategy_priority(strategy):
            name = strategy["name"]
            try:
                return priority_order.index(name)
            except ValueError:
                return len(priority_order)  # Put unknown strategies at end
        
        sorted_strategies = sorted(filtered_strategies, key=strategy_priority)
        
        return sorted_strategies[:max_strategies]
