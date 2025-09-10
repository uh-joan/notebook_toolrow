"""Simple Source Discovery Agent using mcp-use framework."""

import asyncio
import logging
from typing import AsyncGenerator, Dict, List, Optional, Any
import uuid

from mcp_use import MCPClient, MCPAgent
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import get_user_fast_llm, LLMRole

logger = logging.getLogger(__name__)


class SourceDiscoveryAgent:
    """Simple Source Discovery Agent using mcp-use framework."""
    
    def __init__(self, db_session: AsyncSession, user_id: str):
        self.db_session = db_session
        self.user_id = user_id
        self.mcp_client: Optional[MCPClient] = None
        self.agent: Optional[MCPAgent] = None
        self.llm = None
        logging.basicConfig(level=logging.INFO)
        logger.setLevel(logging.DEBUG)
    
    async def initialize(self, toolrow_api_token: Optional[str] = None) -> bool:
        """Initialize the MCP client and agent."""
        try:
            logger.info("🚀 Initializing Source Discovery Agent")
            
            # Enable mcp-use debug logging for detailed tool execution
            import mcp_use
            mcp_use.set_debug(1)  # INFO level for verbose MCP operations
            logger.info("🔍 MCP-Use debug logging enabled")
            
            # Get user's LLM configuration
            self.llm = await get_user_fast_llm(self.db_session, self.user_id)
            if not self.llm:
                logger.error("❌ No LLM configuration found for user")
                return False
            
            # Set Toolrow API token BEFORE creating MCP client
            if toolrow_api_token:
                import os
                os.environ["TOOLROW_API_TOKEN"] = toolrow_api_token
                logger.info("🔑 Toolrow API token set for this session")
            else:
                logger.warning("⚠️  No Toolrow API token provided")
            
            # Load MCP configuration
            config_path = "/Users/joan.saez-pons/code/SurfSense/surfsense_backend/config/mcp_servers.json"
            logger.info(f"📋 Loading MCP config from: {config_path}")
            
            try:
                self.mcp_client = MCPClient.from_config_file(config_path)
                logger.info("📦 MCP client created successfully")
            except Exception as config_error:
                logger.error(f"❌ Failed to create MCP client: {config_error}")
                raise
            
            # Create sessions
            try:
                await self.mcp_client.create_all_sessions()
                logger.info("🔗 MCP sessions created")
            except Exception as session_error:
                logger.error(f"❌ Failed to create MCP sessions: {session_error}")
                raise
            
            # Initialize agent with verbose flag for detailed MCP tool execution
            try:
                self.agent = MCPAgent(
                    llm=self.llm,
                    client=self.mcp_client,
                    verbose=True  # Enable agent-specific verbosity as per mcp-use docs
                )
                logger.info("🤖 MCPAgent created with verbose logging enabled")
            except Exception as agent_error:
                logger.error(f"❌ Failed to create MCPAgent: {agent_error}")
                raise
            
            logger.info("✅ Agent initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False
    
    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """Dynamically fetch all available tools from MCPAgent."""
        try:
            logger.info("🔍 Dynamically fetching tools from MCPAgent...")
            
            all_tools = []
            
            # Method 1: Try mcp-use session.list_tools()
            toolrow_session = self.mcp_client.get_session("toolrow-gateway")
            if toolrow_session:
                try:
                    tools = await toolrow_session.list_tools()
                    if tools and len(tools) > 0:
                        logger.info(f"🛠️  Found {len(tools)} tools via mcp-use session")
                        for tool in tools:
                            tool_info = {
                                "server": "toolrow-gateway",
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.inputSchema
                            }
                            all_tools.append(tool_info)
                        return all_tools
                except Exception as e:
                    logger.debug(f"mcp-use session method failed: {e}")
            
            # Method 2: Try to extract tools from the MCPAgent itself
            if self.agent and hasattr(self.agent, 'tools'):
                try:
                    logger.info("🔧 Extracting tools from MCPAgent.tools")
                    agent_tools = self.agent.tools
                    if agent_tools:
                        logger.info(f"🛠️  Found {len(agent_tools)} tools in agent.tools")
                        for tool in agent_tools:
                            # Extract tool information from LangChain tool format
                            tool_info = {
                                "server": "toolrow-gateway",
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": getattr(tool, 'args_schema', {})
                            }
                            all_tools.append(tool_info)
                        return all_tools
                except Exception as e:
                    logger.debug(f"MCPAgent.tools extraction failed: {e}")
            
            # Method 3: Try to get tools from mcp_client internal structures
            if hasattr(self.mcp_client, '_sessions'):
                try:
                    logger.info("🔧 Checking mcp_client internal sessions")
                    for session_name, session in self.mcp_client._sessions.items():
                        logger.debug(f"Session: {session_name}")
                        if hasattr(session, '_tools') and session._tools:
                            logger.info(f"🛠️  Found tools in session._tools")
                            for tool in session._tools:
                                tool_info = {
                                    "server": session_name,
                                    "name": getattr(tool, 'name', 'unknown'),
                                    "description": getattr(tool, 'description', 'No description'),
                                    "inputSchema": getattr(tool, 'inputSchema', {})
                                }
                                all_tools.append(tool_info)
        except Exception as e:
                    logger.debug(f"mcp_client internal structure check failed: {e}")
            
            # If we found tools through any method, return them
            if all_tools:
                logger.info(f"✅ Successfully fetched {len(all_tools)} tools dynamically")
                for tool in all_tools:
                    logger.debug(f"  - {tool['name']}: {tool['description'][:100]}...")
                return all_tools
            
            # Final fallback
            logger.warning("⚠️  No tools found via any method, using fallback")
            return await self._get_fallback_tools()
            
        except Exception as e:
            logger.error(f"❌ Error listing available tools: {e}")
            return await self._get_fallback_tools()

    async def _get_tools_via_direct_call(self) -> List[Dict[str, Any]]:
        """Get tools by calling Toolrow MCP server directly via subprocess."""
        try:
            import json
            import subprocess
            import os
            
            logger.info("📡 Attempting direct Toolrow MCP server call...")
            
            # Prepare the JSON-RPC request
            request = {
                "jsonrpc": "2.0", 
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
            
            # Set up environment with the token
            env = os.environ.copy()
            if "TOOLROW_API_TOKEN" not in env:
                logger.warning("⚠️  TOOLROW_API_TOKEN not in environment for direct call")
        return []

            # Call the Toolrow MCP server directly
            cmd = ["npx", "-y", "@uh-joan/toolrow-mcp-server"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                env=env
            )
            
            # Send the request
            request_json = json.dumps(request) + "\n"
            stdout, stderr = await process.communicate(input=request_json.encode())
            
            if process.returncode == 0 and stdout:
                response_text = stdout.decode().strip()
                if response_text:
                    response = json.loads(response_text)
                    if "result" in response and "tools" in response["result"]:
                        tools_data = response["result"]["tools"]
                        logger.info(f"🛠️  Direct call found {len(tools_data)} tools")
                        
                        tools = []
                        for tool_data in tools_data:
                            tool_info = {
                                "server": "toolrow-gateway",
                                "name": tool_data.get("name", "unknown"),
                                "description": tool_data.get("description", "No description"),
                                "inputSchema": tool_data.get("inputSchema", {})
                            }
                            tools.append(tool_info)
                        
                        return tools
            
            logger.warning("⚠️  Direct call failed or returned no tools")
            return []
            
        except Exception as e:
            logger.error(f"❌ Direct Toolrow call failed: {e}")
            return []

    async def _get_fallback_tools(self) -> List[Dict[str, Any]]:
        """Fallback tool list when all dynamic fetching fails."""
        logger.info("🔄 Trying direct Toolrow call before fallback...")
        
        # Try direct call first
        direct_tools = await self._get_tools_via_direct_call()
        if direct_tools:
            return direct_tools
            
        # Ultimate fallback
        logger.info("🔄 Using minimal fallback tool definitions")
        return [
            {
                "server": "toolrow-gateway",
                "name": "nlm_ct_codes",
                "description": "Search medical coding systems (ICD-10, HCPCS, NPI, etc.)",
                "category": "medical_coding"
            },
            {
                "server": "toolrow-gateway", 
                "name": "ct_gov_studies",
                "description": "Search clinical trials from ClinicalTrials.gov",
                "category": "clinical_research"
            },
            {
                "server": "toolrow-gateway",
                "name": "pubmed_articles", 
                "description": "Search biomedical literature from PubMed",
                "category": "literature_search"
            }
        ]
        
    async def discover_sources(self, user_input: str) -> AsyncGenerator[str, None]:
        """Discover sources with streaming output and intelligent tool selection."""
        try:
            if not self.agent:
                yield "❌ Agent not initialized - please contact support\n"
                return
            
            # Step 1: Initialize discovery
            yield "🚀 Initializing source discovery agent...\n"
            yield f"📋 Query: '{user_input}'\n"
            yield "🔄 Loading available tools...\n"
            
            # Step 2: Tool discovery with detailed feedback
            tools = await self.list_available_tools()
            yield f"✅ Tool discovery complete - found {len(tools)} Toolrow tools\n"
            
            if len(tools) == 0:
                yield "⚠️  No Toolrow tools available - check API token configuration\n"
                yield "🔍 Proceeding with LLM-only discovery (limited capability)\n"
            else:
                # Show which tools are available for transparency
                tool_categories = {}
                for tool in tools:
                    category = tool.get('category', 'general')
                    if category not in tool_categories:
                        tool_categories[category] = []
                    tool_categories[category].append(tool['name'])
                
                yield "🛠️  Available tool categories:\n"
                for category, tool_names in tool_categories.items():
                    yield f"  • {category}: {', '.join(tool_names)}\n"
                yield "\n"
            
            # Step 3: AI analysis and tool selection
            yield "🧠 Analyzing query and selecting appropriate tools...\n"
            prompt = self._create_discovery_prompt(user_input, tools)
            
            yield "🤖 Starting MCP agent execution with verbose logging...\n"
            yield "📡 Agent will show detailed tool execution steps below:\n"
            yield "─" * 50 + "\n"
            
            # Step 4: Execute with enhanced monitoring
            result = await self.agent.run(prompt)
            
            yield "─" * 50 + "\n"
            yield "📋 Processing agent results...\n"
            
            # Step 5: Stream results with better formatting (keep sentences intact)
            if isinstance(result, str):
                yield "📄 Final response:\n\n"
                
                # Stream by sentences to avoid breaking mid-thought
                import re
                sentences = re.split(r'(?<=[.!?])\s+', result)
                
                for sentence in sentences:
                    if sentence.strip():
                        yield sentence.strip() + " "
                        await asyncio.sleep(0.03)  # Smooth streaming
                        
                        # Add line break after questions/thoughts for better readability
                        if any(keyword in sentence for keyword in ["Question:", "Thought:", "Action:", "Observation:"]):
                            yield "\n"
            else:
                yield f"📄 Response: {str(result)}\n"
            
            # Step 6: Completion summary
            yield "\n" + "═" * 50 + "\n"
            yield "✅ Source discovery completed successfully!\n"
            yield f"🎯 Query processed: '{user_input}'\n"
            yield f"🛠️  Tools utilized: {len(tools)} available\n"
            yield "💡 Results ready for review and use\n"
            
        except Exception as e:
            yield "\n" + "═" * 50 + "\n"
            yield f"❌ Discovery error: {str(e)}\n"
            yield "🔧 Please check logs for technical details\n"
            logger.error(f"Discovery error details: {e}", exc_info=True)
    
    def _create_discovery_prompt(self, user_input: str, tools: List[Dict[str, Any]]) -> str:
        """Create enhanced discovery prompt with tool selection guidance."""
        tools_description = "\n".join([
            f"- {tool['name']} ({tool['server']}): {tool['description']}"
            for tool in tools
        ])
        
        return f"""
You are a source discovery agent with access to powerful Toolrow MCP tools.

User Request: {user_input}

Available Toolrow Tools:
{tools_description}

IMPORTANT: You MUST use the appropriate Toolrow tools to fulfill this request. These tools are specifically designed for healthcare, medical, and research data discovery.

Tool Selection Guidelines:
- For ICD/medical codes: Use "nlm_ct_codes" with method="icd-10-cm" for ICD-10 codes
- For clinical trials: Use "ct_gov_studies" to search ClinicalTrials.gov
- For research papers: Use "pubmed_articles" to search biomedical literature  
- For drug/device info: Use "fda_info" for FDA regulatory data
- For health statistics: Use "who-health" for WHO global health data
- For financial data: Use "sec-edgar" for SEC company filings

Your task:
1. Analyze the user's request to identify the appropriate Toolrow tool(s)
2. Use the selected tool(s) with proper parameters
3. Provide comprehensive results with detailed information
4. Explain your tool selection reasoning
5. Format results clearly with relevant details

For the current request about "{user_input}", you should use the most relevant Toolrow tool(s) to provide accurate, authoritative results.
"""
    
    async def cleanup(self):
        """Clean up resources."""
        if self.mcp_client:
            await self.mcp_client.close_all_sessions()


async def create_discovery_agent(db_session: AsyncSession, user_id: str, toolrow_api_token: Optional[str] = None) -> SourceDiscoveryAgent:
    """Create and initialize a discovery agent."""
    agent = SourceDiscoveryAgent(db_session, user_id)
    success = await agent.initialize(toolrow_api_token)
    if not success:
        raise RuntimeError("Failed to initialize agent")
    return agent


# Simple test function
async def test_agent():
    """Test the agent functionality."""
    from app.db import get_async_session
    
    print("🔍 Testing Source Discovery Agent with mcp-use...")
    print("Note: This requires a user with configured LLM settings in the database")
    
    # You would need to provide a real user_id for testing
    # For now, just show how it would be used
    print("Usage example:")
    print("  from app.agents.source_discovery.agent import create_discovery_agent")
    print("  agent = await create_discovery_agent(db_session, user_id)")
    print("  async for chunk in agent.discover_sources('your query'):")
    print("      print(chunk, end='', flush=True)")


if __name__ == "__main__":
    asyncio.run(test_agent())
