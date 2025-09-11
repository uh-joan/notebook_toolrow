"""
Tool adapters for the reasoning system.

Provides timeout-safe, typed wrappers around MCP tools with standardized
error handling and result formatting.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from abc import ABC, abstractmethod

from .models import ToolResult
from .utils import extract_hit_count, extract_entities_from_result

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Base class for all tool adapters."""
    
    def __init__(self, tool_name: str, timeout_s: int = 20, toolrow_token: Optional[str] = None):
        self.tool_name = tool_name
        self.timeout_s = timeout_s
        self.toolrow_token = toolrow_token or os.getenv("TOOLROW_API_TOKEN")
        
    @abstractmethod
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    async def _call_tool_subprocess(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via subprocess (adapted from existing agent)."""
        try:
            start_time = time.time()
            
            # Prepare the JSON-RPC request
            request = {
                "jsonrpc": "2.0", 
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": params
                }
            }
            
            # Set up environment with the token
            env = os.environ.copy()
            if self.toolrow_token:
                env["TOOLROW_API_TOKEN"] = self.toolrow_token
                
            # Call the Toolrow MCP server directly
            cmd = ["node", "toolrow_servers/toolrow_direct.js"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # Send request and get response with timeout
            request_json = json.dumps(request)
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=request_json.encode()),
                    timeout=self.timeout_s
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration_ms = int((time.time() - start_time) * 1000)
                return {
                    "success": False,
                    "error": f"Tool call timed out after {self.timeout_s}s",
                    "duration_ms": duration_ms
                }
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if process.returncode == 0:
                stdout_str = stdout.decode()
                logger.debug(f"Tool {tool_name} raw output: {stdout_str[:500]}...")
                
                if not stdout_str.strip():
                    return {
                        "success": False,
                        "error": "Empty response from tool",
                        "duration_ms": duration_ms
                    }
                
                try:
                    response = json.loads(stdout_str)
                    if 'result' in response:
                        return {
                            "success": True,
                            "data": response['result'],
                            "duration_ms": duration_ms
                        }
                    else:
                        return {
                            "success": False,
                            "error": response.get('error', 'Unknown error'),
                            "duration_ms": duration_ms
                        }
                except json.JSONDecodeError as e:
                    return {
                        "success": False,
                        "error": f"JSON parse error: {e}",
                        "duration_ms": duration_ms
                    }
            else:
                error_msg = stderr.decode()
                return {
                    "success": False,
                    "error": f"Subprocess failed: {error_msg}",
                    "duration_ms": duration_ms
                }
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
            return {
                "success": False,
                "error": str(e),
                "duration_ms": duration_ms
            }


class CtGovAdapter(BaseAdapter):
    """Adapter for ClinicalTrials.gov studies search."""
    
    def __init__(self, timeout_s: int = 20, toolrow_token: Optional[str] = None):
        super().__init__("ct_gov_studies", timeout_s, toolrow_token)
    
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute ClinicalTrials.gov search."""
        try:
            # Prepare parameters for ct_gov_studies tool
            tool_params = {
                "method": "search",
                **params
            }
            
            result = await self._call_tool_subprocess(self.tool_name, tool_params)
            
            if result.get("success"):
                data = result.get("data")
                hits = extract_hit_count(data)
                
                return ToolResult(
                    tool=self.tool_name,
                    ok=True,
                    hits=hits,
                    data=data,
                    duration_ms=result.get("duration_ms")
                )
            else:
                return ToolResult(
                    tool=self.tool_name,
                    ok=False,
                    hits=0,
                    data=None,
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms")
                )
                
        except Exception as e:
            logger.error(f"CtGovAdapter error: {e}")
            return ToolResult(
                tool=self.tool_name,
                ok=False,
                hits=0,
                data=None,
                error=str(e)
            )


class CtGovSuggestAdapter(BaseAdapter):
    """Adapter for ClinicalTrials.gov suggestion endpoint."""
    
    def __init__(self, timeout_s: int = 10, toolrow_token: Optional[str] = None):
        super().__init__("ct_gov_studies", timeout_s, toolrow_token)
    
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute ClinicalTrials.gov suggest."""
        try:
            tool_params = {
                "method": "suggest",
                **params
            }
            
            result = await self._call_tool_subprocess(self.tool_name, tool_params)
            
            if result.get("success"):
                data = result.get("data")
                # Suggestions typically return a list of terms
                hits = len(data) if isinstance(data, list) else 1 if data else 0
                
                return ToolResult(
                    tool=self.tool_name,
                    ok=True,
                    hits=hits,
                    data=data,
                    duration_ms=result.get("duration_ms")
                )
            else:
                return ToolResult(
                    tool=self.tool_name,
                    ok=False,
                    hits=0,
                    data=None,
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms")
                )
                
        except Exception as e:
            logger.error(f"CtGovSuggestAdapter error: {e}")
            return ToolResult(
                tool=self.tool_name,
                ok=False,
                hits=0,
                data=None,
                error=str(e)
            )


class NlmCodesAdapter(BaseAdapter):
    """Adapter for NLM Clinical Tables (ICD-10, HCPCS, etc.)."""
    
    def __init__(self, timeout_s: int = 10, toolrow_token: Optional[str] = None):
        super().__init__("nlm_ct_codes", timeout_s, toolrow_token)
    
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute NLM codes search."""
        try:
            result = await self._call_tool_subprocess(self.tool_name, params)
            
            if result.get("success"):
                data = result.get("data")
                hits = extract_hit_count(data)
                
                return ToolResult(
                    tool=self.tool_name,
                    ok=True,
                    hits=hits,
                    data=data,
                    duration_ms=result.get("duration_ms")
                )
            else:
                return ToolResult(
                    tool=self.tool_name,
                    ok=False,
                    hits=0,
                    data=None,
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms")
                )
                
        except Exception as e:
            logger.error(f"NlmCodesAdapter error: {e}")
            return ToolResult(
                tool=self.tool_name,
                ok=False,
                hits=0,
                data=None,
                error=str(e)
            )


class FdaAdapter(BaseAdapter):
    """Adapter for FDA information lookups."""
    
    def __init__(self, timeout_s: int = 20, toolrow_token: Optional[str] = None):
        super().__init__("fda_info", timeout_s, toolrow_token)
    
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute FDA information lookup."""
        try:
            result = await self._call_tool_subprocess(self.tool_name, params)
            
            if result.get("success"):
                data = result.get("data")
                hits = extract_hit_count(data)
                
                return ToolResult(
                    tool=self.tool_name,
                    ok=True,
                    hits=hits,
                    data=data,
                    duration_ms=result.get("duration_ms")
                )
            else:
                return ToolResult(
                    tool=self.tool_name,
                    ok=False,
                    hits=0,
                    data=None,
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms")
                )
                
        except Exception as e:
            logger.error(f"FdaAdapter error: {e}")
            return ToolResult(
                tool=self.tool_name,
                ok=False,
                hits=0,
                data=None,
                error=str(e)
            )


class PubMedAdapter(BaseAdapter):
    """Adapter for PubMed literature search."""
    
    def __init__(self, timeout_s: int = 20, toolrow_token: Optional[str] = None):
        super().__init__("pubmed_articles", timeout_s, toolrow_token)
    
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute PubMed search."""
        try:
            result = await self._call_tool_subprocess(self.tool_name, params)
            
            if result.get("success"):
                data = result.get("data")
                hits = extract_hit_count(data)
                
                return ToolResult(
                    tool=self.tool_name,
                    ok=True,
                    hits=hits,
                    data=data,
                    duration_ms=result.get("duration_ms")
                )
            else:
                return ToolResult(
                    tool=self.tool_name,
                    ok=False,
                    hits=0,
                    data=None,
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms")
                )
                
        except Exception as e:
            logger.error(f"PubMedAdapter error: {e}")
            return ToolResult(
                tool=self.tool_name,
                ok=False,
                hits=0,
                data=None,
                error=str(e)
            )


class SecAdapter(BaseAdapter):
    """Adapter for SEC EDGAR company/filing search."""
    
    def __init__(self, timeout_s: int = 20, toolrow_token: Optional[str] = None):
        super().__init__("sec_edgar", timeout_s, toolrow_token)
    
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute SEC EDGAR search."""
        try:
            result = await self._call_tool_subprocess(self.tool_name, params)
            
            if result.get("success"):
                data = result.get("data")
                hits = extract_hit_count(data)
                
                return ToolResult(
                    tool=self.tool_name,
                    ok=True,
                    hits=hits,
                    data=data,
                    duration_ms=result.get("duration_ms")
                )
            else:
                return ToolResult(
                    tool=self.tool_name,
                    ok=False,
                    hits=0,
                    data=None,
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms")
                )
                
        except Exception as e:
            logger.error(f"SecAdapter error: {e}")
            return ToolResult(
                tool=self.tool_name,
                ok=False,
                hits=0,
                data=None,
                error=str(e)
            )


class WhoAdapter(BaseAdapter):
    """Adapter for WHO health data."""
    
    def __init__(self, timeout_s: int = 20, toolrow_token: Optional[str] = None):
        super().__init__("who_health", timeout_s, toolrow_token)
    
    async def call(self, params: Dict[str, Any]) -> ToolResult:
        """Execute WHO health data lookup."""
        try:
            result = await self._call_tool_subprocess(self.tool_name, params)
            
            if result.get("success"):
                data = result.get("data")
                hits = extract_hit_count(data)
                
                return ToolResult(
                    tool=self.tool_name,
                    ok=True,
                    hits=hits,
                    data=data,
                    duration_ms=result.get("duration_ms")
                )
            else:
                return ToolResult(
                    tool=self.tool_name,
                    ok=False,
                    hits=0,
                    data=None,
                    error=result.get("error"),
                    duration_ms=result.get("duration_ms")
                )
                
        except Exception as e:
            logger.error(f"WhoAdapter error: {e}")
            return ToolResult(
                tool=self.tool_name,
                ok=False,
                hits=0,
                data=None,
                error=str(e)
            )


# Factory function to create all adapters
def create_adapters(toolrow_token: Optional[str] = None) -> Dict[str, BaseAdapter]:
    """Create a dictionary of all available adapters."""
    return {
        "ct_gov_studies.search": CtGovAdapter(timeout_s=20, toolrow_token=toolrow_token),
        "ct_gov_studies.suggest": CtGovSuggestAdapter(timeout_s=10, toolrow_token=toolrow_token),
        "nlm_ct_codes": NlmCodesAdapter(timeout_s=10, toolrow_token=toolrow_token),
        "fda_info": FdaAdapter(timeout_s=20, toolrow_token=toolrow_token),
        "pubmed_articles": PubMedAdapter(timeout_s=20, toolrow_token=toolrow_token),
        "sec_edgar": SecAdapter(timeout_s=20, toolrow_token=toolrow_token),
        "who_health": WhoAdapter(timeout_s=20, toolrow_token=toolrow_token)
    }
