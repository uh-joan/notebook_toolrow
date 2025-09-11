"""
Utility functions for the reasoning system.

Provides helper functions for result evaluation, date handling,
deduplication, and other common operations.
"""

from datetime import date, timedelta, datetime
from typing import Any, List, TypeVar, Callable, Set, Dict, Optional
import hashlib
import json
import re

T = TypeVar('T')


def is_zero(result: Any) -> bool:
    """Check if a result represents zero hits."""
    if not result:
        return True
    
    # Handle ToolResult objects
    if hasattr(result, 'hits'):
        return result.hits == 0
    
    # Handle raw data structures
    if isinstance(result, dict):
        hits = result.get('hits', result.get('totalCount', result.get('count', 0)))
        return hits == 0
    
    # Handle lists
    if isinstance(result, list):
        return len(result) == 0
    
    return False


def too_few(result: Any, config) -> bool:
    """Check if result count is below minimum threshold."""
    hits = extract_hit_count(result)
    return hits < config.min_ok


def too_many(result: Any, config) -> bool:
    """Check if result count exceeds maximum threshold.""" 
    hits = extract_hit_count(result)
    return hits > config.max_ok


def extract_hit_count(result: Any) -> int:
    """Extract hit count from various result formats."""
    if not result:
        return 0
    
    # Handle ToolResult objects
    if hasattr(result, 'hits'):
        return result.hits
    
    # Handle raw data structures
    if isinstance(result, dict):
        # Handle MCP tool result format with content
        if 'content' in result and isinstance(result['content'], list):
            for content_item in result['content']:
                if isinstance(content_item, dict) and 'text' in content_item:
                    text = content_item['text']
                    # Look for patterns like "X of Y studies found" or "Results: X of Y"
                    patterns = [
                        r'Results.*?(\d+)\s+of\s+\d+',  # "Results: X of Y"
                        r'(\d+)\s+of\s+\d+\s+studies',  # "X of Y studies"
                        r'Found\s+(\d+)\s+results',     # "Found X results"
                        r'Total.*?(\d+)'                # "Total: X"
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            return int(match.group(1))
        
        # Try common field names
        for field in ['hits', 'totalCount', 'count', 'total', 'results']:
            if field in result:
                value = result[field]
                if isinstance(value, int):
                    return value
                elif isinstance(value, list):
                    return len(value)
        
        # If results is a list, count it
        if 'results' in result and isinstance(result['results'], list):
            return len(result['results'])
    
    # Handle lists
    if isinstance(result, list):
        return len(result)
    
    return 0


def year_window(years_back: int) -> Dict[str, str]:
    """Generate date window for searches."""
    end_date = date.today()
    start_date = end_date - timedelta(days=years_back * 365)
    
    return {
        "from": start_date.strftime("%Y-%m-%d"),
        "to": end_date.strftime("%Y-%m-%d")
    }


def dedupe(items: List[T], key: Callable[[T], Any] = lambda x: x) -> List[T]:
    """Remove duplicates from a list while preserving order."""
    seen: Set[Any] = set()
    result: List[T] = []
    
    for item in items:
        item_key = key(item)
        if item_key not in seen:
            seen.add(item_key)
            result.append(item)
    
    return result


def extract_terms(query: str) -> Dict[str, List[str]]:
    """Extract medical terms, conditions, and other entities from a query."""
    query_lower = query.lower()
    
    # Common medical condition patterns
    conditions = []
    condition_patterns = [
        r'\b(diabetes|diabetic)\b',
        r'\b(obesity|obese)\b', 
        r'\b(hypertension|high blood pressure)\b',
        r'\b(cancer|carcinoma|tumor|malignant)\b',
        r'\b(heart disease|cardiac|cardiovascular)\b',
        r'\b(depression|anxiety|mental health)\b'
    ]
    
    for pattern in condition_patterns:
        matches = re.findall(pattern, query_lower)
        conditions.extend(matches)
    
    # Drug/device patterns
    drugs = []
    drug_patterns = [
        r'\b([a-z]+mab)\b',  # monoclonal antibodies
        r'\b([a-z]+(pril|sartan|olol|pine|ide))\b',  # common drug suffixes
        r'\b(semaglutide|metformin|insulin|aspirin)\b'  # common drugs
    ]
    
    for pattern in drug_patterns:
        matches = re.findall(pattern, query_lower)
        if isinstance(matches[0], tuple) if matches else False:
            drugs.extend([m[0] for m in matches])
        else:
            drugs.extend(matches)
    
    # Trial phase patterns
    phases = re.findall(r'\b(phase\s*[123]|phase\s*i{1,3})\b', query_lower)
    
    # Status patterns
    statuses = []
    status_patterns = [
        r'\b(recruiting|enrolling)\b',
        r'\b(completed|finished)\b',
        r'\b(active|ongoing)\b',
        r'\b(terminated|stopped)\b'
    ]
    
    for pattern in status_patterns:
        matches = re.findall(pattern, query_lower)
        statuses.extend(matches)
    
    return {
        "conditions": list(set(conditions)),
        "drugs": list(set(drugs)),
        "phases": list(set(phases)),
        "statuses": list(set(statuses)),
        "free_text": [query]  # Convert string to list for Pydantic validation
    }


def generate_cache_key(tool: str, params: Dict[str, Any]) -> str:
    """Generate a consistent cache key for tool calls."""
    # Sort parameters for consistent hashing
    sorted_params = json.dumps(params, sort_keys=True, default=str)
    content = f"{tool}:{sorted_params}"
    return hashlib.md5(content.encode()).hexdigest()


def normalize_search_terms(terms: List[str]) -> List[str]:
    """Normalize search terms for better matching."""
    normalized = []
    
    for term in terms:
        # Remove extra whitespace
        term = ' '.join(term.split())
        
        # Convert to lowercase
        term = term.lower()
        
        # Remove common stop words in medical context
        stop_words = {'the', 'of', 'in', 'for', 'with', 'and', 'or', 'a', 'an'}
        words = [w for w in term.split() if w not in stop_words]
        
        if words:
            normalized.append(' '.join(words))
    
    return list(set(normalized))  # Remove duplicates


def extract_entities_from_result(result: Any, tool: str) -> List[Dict[str, Any]]:
    """Extract structured entities from tool results using generic parsing."""
    entities = []
    
    if not result or not hasattr(result, 'data') or not result.data:
        return entities
    
    data = result.data
    
    # Generic approach: try to extract meaningful information from any tool result
    if isinstance(data, dict):
        # Handle MCP content format
        if 'content' in data and isinstance(data['content'], list):
            for content_item in data['content']:
                if isinstance(content_item, dict) and 'text' in content_item:
                    text = content_item['text']
                    
                    # Try to parse as JSON first
                    try:
                        parsed_data = json.loads(text)
                        entities.extend(_extract_from_structured_data(parsed_data, tool))
                    except (json.JSONDecodeError, TypeError):
                        # Parse as text content
                        entities.extend(_extract_from_text_content(text, tool))
        
        # Handle direct structured data
        else:
            entities.extend(_extract_from_structured_data(data, tool))
    
    return entities


def _extract_from_structured_data(data: Dict[str, Any], tool: str) -> List[Dict[str, Any]]:
    """Extract entities from structured data (JSON format)."""
    entities = []
    
    # Look for common array fields that might contain results
    result_fields = ['results', 'data', 'items', 'studies', 'entries']
    
    for field in result_fields:
        if field in data and isinstance(data[field], list):
            for item in data[field]:
                if isinstance(item, dict):
                    # Create a generic entity with available fields
                    entity = {"type": _infer_entity_type(tool), "source": tool}
                    
                    # Extract common fields dynamically
                    id_fields = ['id', 'nctId', 'code', 'identifier']
                    name_fields = ['title', 'name', 'briefTitle', 'label']
                    
                    for id_field in id_fields:
                        if id_field in item:
                            entity['id'] = item[id_field]
                            break
                    
                    for name_field in name_fields:
                        if name_field in item:
                            entity['title'] = item[name_field]
                            break
                    
                    # Add any other relevant fields
                    for key, value in item.items():
                        if key not in ['id', 'title'] and not key.startswith('_'):
                            entity[key] = value
                    
                    entities.append(entity)
            break  # Only process the first matching field
    
    return entities


def _extract_from_text_content(text: str, tool: str) -> List[Dict[str, Any]]:
    """Extract entities from text content using generic patterns."""
    entities = []
    
    # Extract hit count for placeholder entities
    hit_patterns = [
        r'(\d+)\s+of\s+\d+',  # "X of Y"
        r'Found\s+(\d+)',     # "Found X"
        r'Total.*?(\d+)',     # "Total: X"
        r'Results.*?(\d+)'    # "Results: X"
    ]
    
    for pattern in hit_patterns:
        match = re.search(pattern, text)
        if match:
            count = int(match.group(1))
            # Create a summary entity instead of individual placeholders
            entities.append({
                "type": _infer_entity_type(tool),
                "id": "search_summary",
                "title": f"{count} results found",
                "source": tool,
                "count": count,
                "content_preview": text[:200] + "..." if len(text) > 200 else text
            })
            break
    
    return entities


def _infer_entity_type(tool: str) -> str:
    """Infer entity type from tool name."""
    if 'trial' in tool or 'ct_gov' in tool:
        return "clinical_trial"
    elif 'code' in tool or 'nlm' in tool:
        return "medical_code"
    elif 'fda' in tool:
        return "regulatory_info"
    elif 'pubmed' in tool:
        return "literature"
    else:
        return "research_result"


def calculate_recency_score(date_str: Optional[str], max_age_years: int = 10) -> float:
    """Calculate a recency score (0-1) based on how recent a date is."""
    if not date_str:
        return 0.0
    
    try:
        # Parse various date formats
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                item_date = datetime.strptime(date_str[:len(fmt.replace('%', ''))], fmt).date()
                break
            except ValueError:
                continue
        else:
            return 0.0
        
        today = date.today()
        age_days = (today - item_date).days
        max_age_days = max_age_years * 365
        
        if age_days < 0:  # Future date
            return 1.0
        elif age_days > max_age_days:  # Too old
            return 0.0
        else:
            return 1.0 - (age_days / max_age_days)
    
    except (ValueError, TypeError):
        return 0.0


def is_expansion_worthwhile(current_hits: int, config) -> bool:
    """Determine if query expansion is worth attempting."""
    # Always expand for zero hits
    if current_hits == 0:
        return True
    
    # Expand if below minimum threshold
    if current_hits < config.min_ok:
        return True
    
    # Don't expand if we already have good results
    if config.min_ok <= current_hits <= config.max_ok:
        return False
    
    # For too many results, refinement is better than expansion
    return False


def is_refinement_needed(current_hits: int, config) -> bool:
    """Determine if query refinement is needed."""
    return current_hits > config.max_ok
