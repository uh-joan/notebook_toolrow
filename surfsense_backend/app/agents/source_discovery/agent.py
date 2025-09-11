"""Source Discovery Agent using ToolRow.ai API integration."""

import asyncio
import json
import logging
import os
import subprocess
from typing import AsyncGenerator, Dict, List, Optional, Any

from mcp_use import MCPClient, MCPAgent
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import get_user_fast_llm, LLMRole

# Reasoning system imports
from .reasoning.orchestrator import ReasoningOrchestrator
from .reasoning.config import ReasoningConfig
from .reasoning.adapters import create_adapters
from .reasoning.models import FinalResponse

logger = logging.getLogger(__name__)


class SourceDiscoveryAgent:
    """Source Discovery Agent with ToolRow.ai integration."""
    
    def __init__(self, db_session: AsyncSession, user_id: str, reasoning_enabled: bool = None):
        self.db_session = db_session
        self.user_id = user_id
        self.mcp_client: Optional[MCPClient] = None
        self.agent: Optional[MCPAgent] = None
        self.llm = None
        self.toolrow_token: Optional[str] = None
        self._follow_up_questions = []
        
        # Reasoning system components - enabled by default for discovery agent
        self.reasoning_enabled = reasoning_enabled if reasoning_enabled is not None else os.getenv("REASONING_ENABLED", "true").lower() == "true"
        self.reasoning_orchestrator: Optional[ReasoningOrchestrator] = None
        self.reasoning_config: Optional[ReasoningConfig] = None
    
    async def _wait_for_tools_available(self, max_retries: int = 3, delay: float = 1.0) -> bool:
        """Wait for tools to be available in MCP sessions."""
        for attempt in range(max_retries):
            try:
                # Check direct tool availability
                direct_tools = await self._get_tools_via_direct_call()
                if direct_tools and len(direct_tools) > 0:
                    logger.info(f"Tools available: {len(direct_tools)} found")
                    return True
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                logger.debug(f"Tool availability check failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
        
        return False
    
    async def initialize(self, toolrow_api_token: Optional[str] = None) -> bool:
        """Initialize the MCP client and agent."""
        try:
            logger.info("Initializing Source Discovery Agent")
            
            # Get user's LLM configuration
            self.llm = await get_user_fast_llm(self.db_session, self.user_id)
            if not self.llm:
                logger.error("No LLM configuration found for user")
                return False
            
            # Store and set toolrow token
            self.toolrow_token = toolrow_api_token
            if toolrow_api_token:
                os.environ["TOOLROW_API_TOKEN"] = toolrow_api_token
                logger.info("Toolrow API token configured")
            
            # Load MCP configuration
            config_path = "/Users/joan.saez-pons/code/SurfSense/surfsense_backend/config/mcp_servers.json"
            
            # Create MCP client and sessions
            self.mcp_client = MCPClient.from_config_file(config_path)
            await self.mcp_client.create_all_sessions()
            logger.info("MCP client and sessions created")
            
            # Wait for tools to be available
            await self._wait_for_tools_available()
            
            # Initialize agent
            self.agent = MCPAgent(
                llm=self.llm,
                client=self.mcp_client,
                verbose=True
            )
            
            # Check if agent has tools (for fallback logic)
            has_tools = hasattr(self.agent, 'tools') and self.agent.tools
            if has_tools:
                logger.info(f"MCPAgent initialized with {len(self.agent.tools)} tools")
            else:
                logger.info("MCPAgent initialized - will use direct tool execution")
            
            # Initialize reasoning system if enabled
            if self.reasoning_enabled:
                await self._initialize_reasoning_system()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            # Create a minimal agent for fallback functionality
            self.agent = self._create_minimal_agent()
            return False
    
    async def _initialize_reasoning_system(self) -> None:
        """Initialize the reasoning system components."""
        try:
            logger.info("🧠 Initializing reasoning system...")
            
            # Create reasoning configuration
            self.reasoning_config = ReasoningConfig.from_env()
            
            # Create tool adapters
            adapters = create_adapters(toolrow_token=self.toolrow_token)
            
            # Create reasoning orchestrator
            self.reasoning_orchestrator = ReasoningOrchestrator(
                adapters=adapters,
                config=self.reasoning_config
            )
            
            logger.info(f"✅ Reasoning system initialized with {len(adapters)} tool adapters")
            
        except Exception as e:
            logger.error(f"Failed to initialize reasoning system: {e}")
            self.reasoning_enabled = False
    
    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """Fetch available tools from ToolRow.ai."""
        try:
            # Primary method: Direct call to ToolRow server
            tools = await self._get_tools_via_direct_call()
            if tools:
                logger.info(f"Found {len(tools)} tools via direct call")
                return tools
            
            # Fallback: Try MCP session if available
            if hasattr(self.mcp_client, 'get_session'):
                toolrow_session = self.mcp_client.get_session("toolrow-gateway")
                if toolrow_session:
                    try:
                        session_tools = await toolrow_session.list_tools()
                        if session_tools:
                            logger.info(f"Found {len(session_tools)} tools via session")
                            return [{"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema} for tool in session_tools]
                    except Exception as e:
                        logger.debug(f"Session tool listing failed: {e}")
            
            # Return empty list if no tools found
            logger.warning("No tools found via any method")
            return []
            
        except Exception as e:
            logger.error(f"Error listing available tools: {e}")
            return []

    async def _get_tools_via_direct_call(self) -> List[Dict[str, Any]]:
        """Get tools by calling Toolrow MCP server directly."""
        try:
            if "TOOLROW_API_TOKEN" not in os.environ:
                logger.warning("TOOLROW_API_TOKEN not available")
                return []

            # JSON-RPC request for tools list
            request = {
                "jsonrpc": "2.0", 
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
            
            # Call the Toolrow MCP server
            cmd = ["node", "toolrow_servers/toolrow_direct.js"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                env=dict(os.environ)
            )
            
            request_json = json.dumps(request) + "\n"
            stdout, stderr = await process.communicate(input=request_json.encode())
            
            if process.returncode == 0 and stdout:
                response = json.loads(stdout.decode().strip())
                if "result" in response and "tools" in response["result"]:
                    tools_data = response["result"]["tools"]
                    logger.info(f"Found {len(tools_data)} tools via direct call")
                    
                    tools = []
                    for tool_data in tools_data:
                        tool_info = {
                            "name": tool_data.get("name", "unknown"),
                            "description": tool_data.get("description", ""),
                            "inputSchema": tool_data.get("inputSchema", {})
                        }
                        tools.append(tool_info)
                    return tools
            
            logger.warning("Direct call failed or returned no tools")
            return []
            
        except Exception as e:
            logger.error(f"Direct Toolrow call failed: {e}")
            return []

        
    async def discover_sources(self, user_input: str, chat_history: Optional[List] = None) -> AsyncGenerator[str, None]:
        """Discover sources with streaming output."""
        try:
            if not self.agent:
                yield "❌ Agent not initialized\n"
                return
            
            # Debug logging for chat history
            if chat_history:
                logger.info(f"🔗 Received {len(chat_history)} messages in chat history")
                for i, msg in enumerate(chat_history):
                    logger.info(f"  Message {i}: {type(msg).__name__} - {msg.content[:100]}...")
            else:
                logger.info("📝 No chat history provided")
            
            # Check if reasoning system is enabled and available
            if self.reasoning_enabled and self.reasoning_orchestrator:
                logger.info("🧠 Using reasoning system for enhanced search")
                async for chunk in self._discover_sources_with_reasoning(user_input, chat_history):
                    yield chunk
                return
            
            yield f"🚀 Starting research for: '{user_input}'\n"
            yield "🔄 Connecting to research databases...\n"
            
            # Get available tools
            tools = await self.list_available_tools()
            yield f"✅ Connected to {len(tools)} research databases\n"
            
            if len(tools) == 0:
                yield "⚠️ Research databases temporarily unavailable\n"
                result = "I apologize, but the research databases are temporarily unavailable. Please try again in a few moments."
            else:
                # Show available tools in user-friendly terms
                tool_names = [tool['name'] for tool in tools]
                database_types = {
                    'ct_gov_studies': 'Clinical Trials',
                    'pubmed_articles': 'Medical Research',
                    'nlm_ct_codes': 'Medical Codes',
                    'fda_info': 'FDA Data',
                    'sec-edgar': 'SEC Filings',
                    'who-health': 'WHO Health Data'
                }
                
                friendly_names = [database_types.get(name, name) for name in tool_names[:3]]
                yield f"📊 Available databases: {', '.join(friendly_names)}{'...' if len(tool_names) > 3 else ''}\n"
                
                yield "🎯 Selecting best database for your query...\n"
                prompt = self._create_discovery_prompt(user_input, tools, chat_history)
                
                yield "🔍 Analyzing your request and executing search...\n"
                yield "─" * 50 + "\n"
                
                # Always show positive messaging when tools are available
                if tools and len(tools) > 0:
                    yield f"🚀 Executing search with {len(tools)} research tools\n"
                    
                    # Try MCPAgent first, fallback to direct execution
                    if hasattr(self.agent, 'tools') and self.agent.tools and len(self.agent.tools) > 0:
                        result = await self.agent.run(prompt)
                    else:
                        # Use direct tool execution with streaming feedback
                        async for chunk in self._execute_with_direct_tools_streaming(prompt, tools, user_input, chat_history):
                            yield chunk
                        return  # Exit early since we've already streamed everything
                else:
                    yield "❌ Research tools temporarily unavailable\n"
                    result = "I apologize, but the research tools are temporarily unavailable. Please try again in a few moments."
            
            yield "─" * 50 + "\n"
            yield "📋 Processing search results...\n"
            yield "📄 Research Results:\n\n"
            
            # Stream the result
            if isinstance(result, str):
                yield result
            else:
                yield str(result)
                
        except Exception as e:
            yield f"❌ Research error: Unable to complete your search at this time\n"
            yield "Please try again in a few moments or contact support if the issue persists.\n"
            logger.error(f"Discovery error: {e}", exc_info=True)
    
    def _create_discovery_prompt(self, user_input: str, tools: List[Dict[str, Any]], chat_history: Optional[List] = None) -> str:
        """Create discovery prompt with tool selection guidance."""
        tools_description = "\n".join([
            f"- {tool['name']}: {tool['description']}"
            for tool in tools
        ])
        
        history_context = ""
        if chat_history:
            history_messages = []
            for msg in chat_history[-3:]:  # Last 3 messages for context
                if hasattr(msg, 'content'):  # LangChain message object
                    role = "user" if type(msg).__name__ == "HumanMessage" else "assistant"
                    history_messages.append(f"{role}: {msg.content}")
                else:  # Dict format
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    history_messages.append(f"{role}: {content}")
            
            if history_messages:
                history_context = "\nConversation History:\n" + "\n".join(history_messages) + "\n"
        
        return f"""You are a source discovery agent with access to ToolRow research tools.

{history_context}
Current Request: {user_input}

Available Tools:
{tools_description}

Guidelines:
1. Select the most appropriate tool for the user's request
2. Use the tool with proper parameters
3. Provide comprehensive, accurate results
4. Format results clearly

Use the most relevant tool to provide authoritative results for: "{user_input}"
"""
    
    def _create_minimal_agent(self):
        """Create a minimal agent object for fallback functionality."""
        class MinimalAgent:
            def __init__(self):
                self.tools = []
                
            async def run(self, prompt: str):
                return "Minimal agent response - using direct tool access"
        
        return MinimalAgent()

    async def _execute_with_direct_tools(self, prompt: str, available_tools: List[Dict[str, Any]], user_input: str, chat_history: Optional[List] = None) -> str:
        """Execute discovery using direct tool access when MCPAgent fails."""
        try:
            logger.info(f"🔧 Direct tool execution with {len(available_tools)} tools")
            
            # For now, create a structured response based on the query and available tools
            tool_names = [tool['name'] for tool in available_tools]
            
            # Use LLM to intelligently select the most appropriate tool
            selected_tool = await self._select_tool_with_llm(user_input, available_tools, chat_history)
            
            if selected_tool:
                return await self._execute_selected_tool(selected_tool, user_input, chat_history)
            else:
                # If no specific tool selected, provide general guidance
                return await self._provide_general_guidance(user_input, available_tools)
            
        except Exception as e:
            logger.error(f"❌ Direct tool execution failed: {e}")
            return f"Unable to execute direct tool access: {str(e)}"

    async def _execute_with_direct_tools_streaming(self, prompt: str, available_tools: List[Dict[str, Any]], user_input: str, chat_history: Optional[List] = None) -> AsyncGenerator[str, None]:
        """Execute discovery using direct tool access with streaming feedback."""
        try:
            logger.info(f"🔧 Direct tool execution with {len(available_tools)} tools")
            
            # Step 1: Tool Selection
            yield "🎯 Analyzing your query to select the best research tool...\n"
            
            tool_names = [tool['name'] for tool in available_tools]
            selected_tool = await self._select_tool_with_llm(user_input, available_tools, chat_history)
            
            if selected_tool:
                yield f"✅ Selected: **{selected_tool['name']}** - {selected_tool.get('description', 'Specialized research tool')}\n"
                
                # Step 2: Search Strategy Analysis
                yield "🧠 Analyzing search strategy (precision vs. recall)...\n"
                
                search_strategy = await self._analyze_search_intent(user_input, selected_tool, chat_history)
                yield f"📊 Search approach: **{search_strategy['approach']}** - {search_strategy['reasoning']}\n"
                
                # Step 3: Parameter Extraction
                yield "⚙️ Extracting search parameters from your query...\n"
                
                params = await self._extract_tool_parameters(selected_tool, user_input, chat_history, search_strategy)
                
                # Show the parameters in a user-friendly way
                yield f"📋 Search parameters configured:\n"
                for key, value in params.items():
                    if isinstance(value, str) and len(value) > 50:
                        display_value = value[:47] + "..."
                    else:
                        display_value = value
                    yield f"  • {key}: {display_value}\n"
                
                # Step 3: Tool Execution
                yield "🔍 Executing search with configured parameters...\n"
                
                result = await self._call_tool_subprocess(selected_tool['name'], params)
                
                yield "─" * 50 + "\n"
                yield "📋 Processing search results...\n"
                yield "📄 Research Results:\n\n"
                
                # Format and stream the result with strategy analysis
                if result:
                    formatted_result = await self._format_tool_response(user_input, selected_tool['name'], result, chat_history, search_strategy)
                    yield formatted_result
                    
                    # Generate contextual follow-up questions
                    follow_up_questions = await self._generate_follow_up_questions(user_input, result, selected_tool, chat_history)
                    if follow_up_questions:
                        # Store questions for the route to handle with StreamingService
                        self._follow_up_questions = follow_up_questions
                    
                    # Analyze results and suggest alternatives if needed (only if poor results)
                    result_analysis = await self._analyze_search_results(result, search_strategy, user_input, selected_tool)
                    if result_analysis.get('suggest_alternatives'):
                        yield f"💡 **Search Strategy Suggestions:**\n{result_analysis['suggestions']}\n"
                else:
                    yield "No results found for your query.\n"
                    # Provide alternative strategy suggestions for zero results
                    alternative_suggestions = await self._suggest_alternative_strategies(search_strategy, user_input, selected_tool)
                    yield f"💡 **Alternative Search Strategies:**\n{alternative_suggestions}\n"
                
            else:
                yield "❌ Unable to select appropriate research tool\n"
                general_result = await self._provide_general_guidance(user_input, available_tools)
                yield general_result
            
        except Exception as e:
            logger.error(f"❌ Streaming tool execution failed: {e}")
            yield f"❌ Research error: {str(e)}\n"

    async def _analyze_search_intent(self, user_input: str, selected_tool: Dict[str, Any], chat_history: Optional[List] = None) -> Dict[str, str]:
        """Analyze user intent to determine optimal search strategy (precision vs recall)."""
        try:
            # Analyze the query characteristics
            intent_prompt = f"""Analyze this search query to determine the optimal search strategy.

User Query: "{user_input}"
Tool: {selected_tool['name']}
Tool Description: {selected_tool.get('description', '')}

INTENT ANALYSIS FRAMEWORK:
1. **High Precision** (exact/specific terms):
   - User uses technical terminology or specific identifiers
   - Precise mechanisms, codes, or exact names mentioned
   - Research-focused language ("specifically about", "exactly matching")
   - Narrow, well-defined concepts with little ambiguity

2. **High Recall** (broad/exploratory):
   - General terminology or category-level requests
   - Exploratory language ("find", "what's available", "search for")
   - Broad concepts that could have many related variations
   - Discovery-oriented queries seeking comprehensive coverage

3. **Balanced** (moderate expansion):
   - Mix of specific and general terms
   - Follow-up questions that refine previous searches
   - Reasonable specificity but open to related concepts

Respond with EXACTLY this JSON format:
{{"approach": "High Precision|High Recall|Balanced", "reasoning": "Brief explanation of why this approach is optimal for this query and database"}}"""

            response = await self.llm.ainvoke(intent_prompt)
            
            try:
                import json
                result = json.loads(response.content.strip())
                return result
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return {
                    "approach": "Balanced",
                    "reasoning": "Using balanced approach as fallback - will try exact terms first, then expand if needed"
                }
                
        except Exception as e:
            logger.error(f"❌ Search intent analysis failed: {e}")
            return {
                "approach": "Balanced", 
                "reasoning": "Using balanced approach due to analysis error"
            }

    async def _select_tool_with_llm(self, user_input: str, available_tools: List[Dict[str, Any]], chat_history: Optional[List] = None) -> Optional[Dict[str, Any]]:
        """Use LLM to intelligently select the most appropriate tool for the query."""
        try:
            # Create tool descriptions for LLM
            tool_descriptions = []
            for tool in available_tools:
                tool_descriptions.append(f"- {tool['name']}: {tool.get('description', 'No description available')}")
            
            tools_text = "\n".join(tool_descriptions)
            
            # Add conversation history context for tool selection
            history_context = ""
            if chat_history:
                # Check if previous query used a specific tool
                previous_tools_used = []
                for msg in chat_history[-3:]:
                    if hasattr(msg, 'content'):  # LangChain message object
                        content = msg.content
                    else:  # Dict format
                        content = msg.get('content', '')
                    
                    if 'Tool Used:' in content:
                        tool_match = content.split('Tool Used:')[1].split('\n')[0].strip()
                        if tool_match:
                            previous_tools_used.append(tool_match)
                
                if previous_tools_used:
                    history_context = f"\nConversation Context:\nPrevious tool used: {previous_tools_used[-1]}\n"
                    history_context += f"IMPORTANT: This appears to be a follow-up query. Use the SAME tool ({previous_tools_used[-1]}) to refine the search.\n"

            # Create a prompt for tool selection
            selection_prompt = f"""Given the user query and available tools, select the most appropriate tool to use.

User Query: "{user_input}"
{history_context}
Available Tools:
{tools_text}

Instructions:
- Respond with ONLY the tool name that best matches the query
- If no tool is clearly appropriate, respond with "NONE"
- CRITICAL: For follow-up queries like "only for X", "filter for Y", "narrow down to Z", use the SAME tool as before
- Consider the query intent and tool capabilities
- For refinement queries, maintain the same data source/tool

Tool Selection:"""

            # Use the LLM to select the tool
            response = await self.llm.ainvoke(selection_prompt)
            selected_tool_name = response.content.strip()
            
            # Find the selected tool in available tools
            for tool in available_tools:
                if tool['name'].lower() == selected_tool_name.lower():
                    logger.info(f"🎯 LLM selected tool: {selected_tool_name}")
                    return tool
            
            if selected_tool_name.upper() != "NONE":
                logger.warning(f"⚠️ LLM selected unknown tool: {selected_tool_name}")
            
            return None
        except Exception as e:
            logger.error(f"❌ Tool selection with LLM failed: {e}")
            return None

    async def _execute_selected_tool(self, tool: Dict[str, Any], user_input: str, chat_history: Optional[List] = None) -> str:
        """Execute the selected tool with appropriate parameters."""
        try:
            tool_name = tool['name']
            logger.info(f"🔧 Executing selected tool: {tool_name}")
            
            # Extract parameters based on tool type and query
            params = await self._extract_tool_parameters(tool, user_input, chat_history)
            
            # Call the tool
            result = await self._call_tool_subprocess(tool_name, params)
            
            if result and result.get('success'):
                # Extract text content from the response
                data = result.get('data', {})
                response_text = "No data returned"
                
                if isinstance(data, dict) and 'content' in data:
                    content = data['content']
                    if isinstance(content, list) and len(content) > 0:
                        first_content = content[0]
                        if isinstance(first_content, dict) and 'text' in first_content:
                            response_text = first_content['text']
                        else:
                            response_text = f"Tool response error: missing 'text' field. Got: {first_content}"
                    else:
                        response_text = f"Tool response error: content is not a list or is empty: {content}"
                elif isinstance(data, str):
                    response_text = data
                else:
                    response_text = f"Tool response error: unexpected data format: {data}"
                
                # Format the response intelligently using LLM
                formatted_response = await self._format_tool_response(
                    user_input, tool_name, response_text, chat_history
                )
                
                return formatted_response
            else:
                return f"""**Tool Execution Attempted**

Query: {user_input}
Tool Used: {tool_name}

Tool call attempted but no results returned. Error: {result.get('error', 'Unknown error')}

*Note: Tool connectivity issue - contact support*"""
                
        except Exception as e:
            logger.error(f"❌ Tool execution failed: {e}")
            return f"Error executing tool {tool.get('name', 'unknown')}: {e}"

    async def _extract_tool_parameters(self, tool: Dict[str, Any], user_input: str, chat_history: Optional[List] = None, search_strategy: Optional[Dict[str, str]] = None) -> dict:
        """Use LLM to extract appropriate parameters for the selected tool."""
        try:
            tool_name = tool['name']
            tool_description = tool.get('description', '')
            
            # Get the actual tool schema to provide accurate parameter names
            available_tools = await self.list_available_tools()
            tool_schema = None
            for tool in available_tools:
                if tool['name'] == tool_name:
                    tool_schema = tool.get('inputSchema', {})
                    break
            
            # Create schema information for the prompt
            schema_info = ""
            if tool_schema and 'properties' in tool_schema:
                schema_info = f"\nTool Parameters Schema:\n"
                for param_name, param_info in tool_schema['properties'].items():
                    description = param_info.get('description', 'No description')
                    param_type = param_info.get('type', 'unknown')
                    schema_info += f"- {param_name} ({param_type}): {description}\n"
            
            # Add conversation history context for follow-up questions
            history_context = ""
            if chat_history:
                logger.info(f"📝 Chat history available: {len(chat_history)} messages")
                history_messages = []
                for msg in chat_history[-3:]:  # Last 3 messages for context
                    if hasattr(msg, 'content'):  # LangChain message object
                        role = "user" if type(msg).__name__ == "HumanMessage" else "assistant"
                        history_messages.append(f"{role}: {msg.content}")
                    else:  # Dict format
                        role = msg.get('role', 'user')
                        content = msg.get('content', '')
                        history_messages.append(f"{role}: {content}")
                
                if history_messages:
                    history_context = "\nConversation History:\n" + "\n".join(history_messages) + "\n"
                
                # Add previous parameters if available for the same tool
                if hasattr(self, '_last_tool_params') and tool_name in self._last_tool_params:
                    prev_params = self._last_tool_params[tool_name]
                    history_context += f"\nPrevious Parameters for {tool_name}:\n{json.dumps(prev_params, indent=2)}\n"
                    logger.info(f"📝 Including previous parameters: {json.dumps(prev_params, indent=2)}")
                
                logger.info(f"📝 History context for parameter extraction: {history_context[:200]}...")
            else:
                logger.info("📝 No chat history available for parameter extraction")

            # Add search strategy context
            strategy_context = ""
            if search_strategy:
                strategy_context = f"""
Search Strategy: {search_strategy['approach']}
Strategy Reasoning: {search_strategy['reasoning']}

STRATEGY APPLICATION:
- High Precision: Use exact terms from user query, preserve technical specificity
- High Recall: Consider broader terms, synonyms, and category expansions
- Balanced: Start with user terms, be ready to adjust based on database response
"""

            # Create a prompt to extract parameters dynamically
            param_prompt = f"""Extract the appropriate parameters for calling this tool based on the user query and schema.

Tool: {tool_name}
Description: {tool_description}
{schema_info}
{strategy_context}
{history_context}
User Query: "{user_input}"

Instructions:
- Use the EXACT parameter names from the schema above
- Match parameter types exactly as specified in the schema
- For enum fields, use the exact values listed in the schema
- Extract relevant information from the user query that maps to the schema parameters
- CRITICAL: If previous parameters are provided, START with those and MODIFY them based on the new query
- For follow-up questions like "filter for X", "only Y", "narrow down to Z":
  * START with the previous parameters as your base
  * MODIFY only the relevant parameters based on the new criteria
  * KEEP all other parameters unchanged unless explicitly overridden
- Examples of parameter evolution:
  * Previous: {{"method": "icd-10-cm", "terms": "diabetes"}} 
  * Query: "only type 2" → {{"method": "icd-10-cm", "terms": "type 2 diabetes"}}
  * Previous: {{"condition": "obesity", "location": "California"}}
  * Query: "filter for GLP-1" → {{"condition": "obesity", "location": "California", "intervention": "GLP-1"}}
- If a parameter has a description, use that to understand what values to extract
- Return ONLY a valid JSON object with the extracted parameters
- Use proper data types (string, number, boolean, array) as specified in the schema

Parameters JSON:"""

            # Use LLM to extract parameters
            response = await self.llm.ainvoke(param_prompt)
            param_text = response.content.strip()
            
            try:
                import json
                # Try to parse as JSON first
                if param_text.startswith('{') and param_text.endswith('}'):
                    params = json.loads(param_text)
                else:
                    # Fallback: create basic parameters
                    params = self._create_basic_parameters(tool_name, user_input)
            except json.JSONDecodeError:
                # Fallback: create basic parameters
                params = self._create_basic_parameters(tool_name, user_input)
            
            logger.info(f"📋 Final extracted parameters for {tool_name}: {json.dumps(params, indent=2)}")
            logger.info(f"📝 Parameter extraction used history: {'YES' if chat_history else 'NO'}")
            
            # Store parameters in conversation context for future follow-ups
            if hasattr(self, '_last_tool_params'):
                self._last_tool_params[tool_name] = params
            else:
                self._last_tool_params = {tool_name: params}
            
            return params
            
        except Exception as e:
            logger.error(f"❌ Parameter extraction failed: {str(e)}")
            return self._create_basic_parameters(tool.get('name', ''), user_input)

    def _create_basic_parameters(self, tool_name: str, user_input: str) -> dict:
        """Create basic parameters when LLM extraction fails - using minimal assumptions."""
        # Extract the main topic/condition from the query dynamically
        condition = self._extract_medical_condition(user_input)
        
        # Return the most basic parameter structure that most tools would accept
        # This is the minimal fallback when we can't determine tool-specific parameters
        return {'query': condition}

    async def _provide_general_guidance(self, user_input: str, available_tools: List[Dict[str, Any]]) -> str:
        """Provide general guidance when no specific tool is selected."""
        tool_names = [tool['name'] for tool in available_tools]
        
        return f"""**Discovery Analysis Complete**

**Query**: {user_input}

**Available Discovery Tools**: {', '.join(tool_names)}

**Analysis**: I can help you find relevant information using the available discovery tools. Based on your query, you might want to try a more specific request.

**Suggestions**:
- For medical codes: "Find ICD-10 codes for [condition]"
- For clinical trials: "Find clinical trials for [condition]"  
- For research articles: "Find research about [topic]"
- For FDA information: "Find FDA data for [drug/device]"

**Available Tool Categories**: {len(available_tools)} specialized research tools are ready to help with your discovery needs."""


    def _extract_medical_condition(self, query: str) -> str:
        """Extract the medical condition from user query without hardcoding."""
        import re
        
        # Remove common query prefixes/suffixes to isolate the condition
        query_clean = query.lower()
        
        # Remove common patterns
        patterns_to_remove = [
            r'find\s+icd\s*-?\s*10\s+codes?\s+for\s+',
            r'what\s+about\s+for\s+',
            r'codes?\s+for\s+',
            r'icd\s*-?\s*10\s+for\s+',
            r'medical\s+codes?\s+for\s+',
            r'diagnosis\s+codes?\s+for\s+'
        ]
        
        for pattern in patterns_to_remove:
            query_clean = re.sub(pattern, '', query_clean)
        
        # Clean up extra whitespace and punctuation
        condition = re.sub(r'[^\w\s]', '', query_clean).strip()
        
        return condition if condition else "general condition"

    async def _call_tool_subprocess(self, tool_name: str, params: dict) -> dict:
        """Call a specific tool via subprocess to get real results."""
        try:
            import json
            import os
            
            # Prepare the JSON-RPC request
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": f"tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": params
                }
            }
            
            # Set up environment with the token
            env = os.environ.copy()
            env["TOOLROW_API_TOKEN"] = self.toolrow_token or ""
            
            # Call the Toolrow MCP server directly
            cmd = ["node", "toolrow_servers/toolrow_direct.js"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # Send request and get response
            request_json = json.dumps(request)
            stdout, stderr = await process.communicate(input=request_json.encode())
            
            if process.returncode == 0:
                stdout_str = stdout.decode()
                logger.debug(f"Tool subprocess raw output length: {len(stdout_str)}")
                logger.debug(f"Tool subprocess raw output: {stdout_str}")
                
                if not stdout_str.strip():
                    logger.error("Tool subprocess returned empty output")
                    return {"success": False, "error": "Empty response from tool"}
                    
                try:
                    response = json.loads(stdout_str)
                    logger.debug(f"Parsed response: {response}")
                    if 'result' in response:
                        logger.debug(f"Response result: {response['result']}")
                        return {"success": True, "data": response['result']}
                    else:
                        return {"success": False, "error": response.get('error', 'Unknown error')}
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}, Raw output: {stdout_str}")
                    return {"success": False, "error": f"JSON parse error: {e}"}
            else:
                logger.error(f"Tool subprocess failed: {stderr.decode()}")
                return {"success": False, "error": f"Subprocess failed: {stderr.decode()}"}
                    
        except Exception as e:
            logger.error(f"Failed to call tool subprocess: {e}")
            return {"success": False, "error": str(e)}


    async def _format_tool_response(self, user_query: str, tool_name: str, raw_response: str, chat_history: Optional[List] = None, search_strategy: Optional[Dict[str, str]] = None) -> str:
        """Use LLM to intelligently format tool responses for better user experience."""
        try:
            # Determine response type and format accordingly
            context = ""
            if chat_history:
                context = f"\nConversation Context: This is a follow-up to previous queries in this conversation.\n"
            
            formatting_prompt = f"""Transform this technical tool response into a natural, conversational answer for the user.

User's Question: "{user_query}"
Tool Used: {tool_name}
{context}
Raw Tool Response: {str(raw_response)[:3000]}...

FORMATTING GUIDELINES:
1. **Summary Section**: Start with clear overview of what was found (total counts, key categories)
2. **Categorized Results**: Group results by type/category when applicable  
3. **Structured Presentation**: Use clear headings, bullet points, numbered lists
4. **Tool-Specific Formatting**:
   - ICD Codes: "**E11.65** - Type 2 diabetes mellitus with hyperglycemia"
   - Clinical Trials: Include title, status, recruitment info, organized by treatment type
   - Research Papers: Include title, authors, journal, group by topic
   - Medical Codes: Group by code system/category
5. **Context & Reliability**: Brief note about data source and currency
6. **Next Steps Section**: Provide 3-4 specific actionable follow-up options
7. **Handle Zero Results**: Suggest alternative search strategies with specific examples

RESPONSE STRUCTURE:
# [Create a Clear, Specific Title Based on the Query]
[E.g., "ICD-10 Codes for Diabetes", "Clinical Trials for Obesity Treatment", "FDA-Approved T2D Medications"]

## Summary
[Brief overview with key statistics]

## Key Categories Identified
[Group results by treatment type, status, etc.]

## [Category 1]: 
[Relevant results with proper formatting]

## [Category 2]:
[More results organized logically]

## Context & Reliability
[Brief note about data source, currency, limitations]

## Next Steps
[3-4 specific actionable options for follow-up]

Make the response scannable, informative, and actionable. Start with a clear title that summarizes what was found. Use emojis sparingly for section headers only."""

            response = await self.llm.ainvoke(formatting_prompt)
            formatted_text = response.content.strip()
            
            # Add technical attribution
            formatted_text += f"\n\n*Source: {tool_name} • Real-time data*"
            
            return formatted_text
            
        except Exception as e:
            logger.error(f"❌ Response formatting failed: {e}")
            # Fallback to basic formatting
            return f"""**Tool Execution Results**

Query: {user_query}
Tool Used: {tool_name}

{raw_response}

*Real-time data from {tool_name} tool*"""

    async def cleanup(self):
        """Clean up resources."""
        if self.mcp_client:
            await self.mcp_client.close_all_sessions()

    async def _analyze_search_results(self, raw_response: str, search_strategy: Dict[str, str], user_query: str, selected_tool: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze search results to determine if alternative strategies should be suggested."""
        try:
            analysis_prompt = f"""Analyze these search results to determine if alternative search strategies should be suggested.

User Query: "{user_query}"
Search Strategy Used: {search_strategy['approach']} - {search_strategy['reasoning']}
Tool: {selected_tool['name']}
Results: {str(raw_response)[:1000]}...

ANALYSIS CRITERIA:
1. **Result Quality**: Do results directly address the user's intent?
2. **Result Quantity**: Are there too few results (suggest expanding) or too many irrelevant ones (suggest narrowing)?
3. **Strategy Mismatch**: Would a different approach (precision vs recall) yield better results?

Respond with EXACTLY this JSON format:
{{"suggest_alternatives": true/false, "suggestions": "Brief explanation of alternative approaches if suggest_alternatives is true, otherwise empty string"}}"""

            response = await self.llm.ainvoke(analysis_prompt)
            
            try:
                import json
                return json.loads(response.content.strip())
            except json.JSONDecodeError:
                return {"suggest_alternatives": False, "suggestions": ""}
                                
        except Exception as e:
            logger.error(f"❌ Result analysis failed: {e}")
            return {"suggest_alternatives": False, "suggestions": ""}

    async def _suggest_alternative_strategies(self, search_strategy: Dict[str, str], user_query: str, selected_tool: Dict[str, Any]) -> str:
        """Suggest alternative search strategies when no results are found."""
        try:
            suggestion_prompt = f"""The search returned zero results. Suggest alternative search strategies.

User Query: "{user_query}"
Strategy Attempted: {search_strategy['approach']} - {search_strategy['reasoning']}
Tool: {selected_tool['name']}

ALTERNATIVE STRATEGY FRAMEWORK:
- If attempted High Precision → suggest High Recall (broader terms, synonyms)
- If attempted High Recall → suggest High Precision (more specific terms) 
- If attempted Balanced → suggest both directions with examples

Provide 2-3 concrete alternative approaches with specific term suggestions.
Keep suggestions generic and applicable to any domain."""

            response = await self.llm.ainvoke(suggestion_prompt)
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"❌ Alternative strategy generation failed: {e}")
            return "Try adjusting your search terms or using broader/narrower terminology."

    async def _generate_follow_up_questions(self, user_query: str, raw_response: str, selected_tool: Dict[str, Any], chat_history: Optional[List] = None) -> List[str]:
        """Generate contextual follow-up questions based on the search results."""
        try:
            # Build context from chat history
            history_context = ""
            if chat_history:
                history_messages = []
                for msg in chat_history[-3:]:  # Last 3 messages for context
                    if hasattr(msg, 'content'):  # LangChain message object
                        role = "user" if type(msg).__name__ == "HumanMessage" else "assistant"
                        history_messages.append(f"{role}: {msg.content[:200]}")
                    else:  # Dict format
                        role = msg.get('role', 'user')
                        content = msg.get('content', '')[:200]
                        history_messages.append(f"{role}: {content}")
                
                if history_messages:
                    history_context = f"\nConversation History:\n" + "\n".join(history_messages) + "\n"

            follow_up_prompt = f"""Generate 3-4 contextual follow-up questions based on the search results and conversation.

User's Original Query: "{user_query}"
Tool Used: {selected_tool['name']}
Search Results Summary: {str(raw_response)[:1000]}...
{history_context}

FOLLOW-UP QUESTION GUIDELINES:
1. **Build on Current Results**: Questions should explore deeper aspects of the found data
2. **Explore Related Areas**: Suggest logical extensions or related topics
3. **Actionable Refinements**: Questions that help narrow/broaden/refine the search
4. **Practical Applications**: Questions about next steps or implementation

QUESTION TYPES TO GENERATE:
- Refinement questions (narrow down by criteria)
- Exploration questions (related topics)
- Comparison questions (vs other options)
- Implementation questions (how to use/apply results)

Return EXACTLY this JSON format:
{{
  "further_questions": [
    {{"id": 0, "question": "question 1"}},
    {{"id": 1, "question": "question 2"}},
    {{"id": 2, "question": "question 3"}},
    {{"id": 3, "question": "question 4"}}
  ]
}}

Keep questions conversational, specific, and directly relevant to the search domain."""

            response = await self.llm.ainvoke(follow_up_prompt)
            
            try:
                import json
                # Find JSON in response
                content = response.content.strip()
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    parsed_data = json.loads(json_str)
                    return parsed_data.get("further_questions", [])
                else:
                    return []
                    
            except json.JSONDecodeError:
                logger.error("Failed to parse follow-up questions JSON")
                return []
                
        except Exception as e:
            logger.error(f"❌ Follow-up question generation failed: {e}")
            return []

    def get_follow_up_questions(self) -> List[Dict[str, Any]]:
        """Get the last generated follow-up questions."""
        return getattr(self, '_follow_up_questions', [])

    def clear_follow_up_questions(self):
        """Clear the stored follow-up questions."""
        self._follow_up_questions = []
    
    async def _discover_sources_with_reasoning(self, user_input: str, chat_history: Optional[List] = None) -> AsyncGenerator[str, None]:
        """Discover sources using the reasoning system."""
        try:
            yield "🧠 **Reasoning Mode Activated**\n"
            yield f"🚀 Starting intelligent research for: '{user_input}'\n"
            yield "🔄 Analyzing query and planning search strategy...\n"
            
            # Prepare task for reasoning orchestrator
            task = {
                "query": user_input,
                "chat_history": chat_history,
                "user_id": self.user_id
            }
            
            # Execute reasoning
            result: FinalResponse = await self.reasoning_orchestrator.run(task)
            
            if not result.success:
                yield f"❌ Reasoning search failed: {result.answer.get('error', 'Unknown error')}\n"
                yield "🔄 Falling back to simple search...\n"
                
                # Fallback to simple search
                async for chunk in self._discover_sources_simple(user_input, chat_history):
                    yield chunk
                return
            
            # Stream reasoning trace events
            yield f"✅ Search completed in {result.total_duration_ms or 0}ms\n"
            yield f"📊 **Search Results**: {len(result.evidence)} sources found\n"
            
            if result.trace:
                yield f"🔍 **Reasoning Trace** ({len(result.trace)} steps):\n"
                for event in result.trace[-5:]:  # Show last 5 steps
                    yield f"  • {event.step}: {event.reason}\n"
            
            yield "──────────────────────────────────────────────────\n"
            
            # Format and yield the final answer
            answer = result.answer
            yield f"# 📋 **Research Results Summary**\n\n"
            
            if "summary" in answer:
                yield f"**Summary**: {answer['summary']}\n\n"
            
            if result.evidence:
                yield f"## 🎯 **Found Sources** ({len(result.evidence)})\n\n"
                for i, evidence in enumerate(result.evidence[:10], 1):  # Limit to top 10
                    yield f"**{i}. {evidence.title or 'Untitled'}**\n"
                    if evidence.source:
                        yield f"   📍 Source: {evidence.source}\n"
                    if evidence.id:
                        yield f"   🔗 ID: {evidence.id}\n"
                    if evidence.url:
                        yield f"   🌐 URL: {evidence.url}\n"
                    yield "\n"
            
            # Show strategy information
            if "strategies_used" in answer:
                strategies = answer["strategies_used"]
                if strategies:
                    yield f"## 🛠️ **Search Strategies Used**\n"
                    for strategy in strategies:
                        yield f"  • {strategy}\n"
                    yield "\n"
            
            # Show limitations
            if result.limitations:
                yield f"## ⚠️ **Limitations**\n"
                for limitation in result.limitations:
                    yield f"  • {limitation}\n"
                yield "\n"
            
            # Show next best actions
            if result.next_best_actions:
                yield f"## 💡 **Suggested Next Steps**\n"
                for action in result.next_best_actions:
                    yield f"  • {action}\n"
                yield "\n"
            
            # Generate follow-up questions based on results
            if result.evidence:
                yield "🤔 **Generating intelligent follow-up questions...**\n"
                await self._generate_reasoning_follow_ups(user_input, result)
            
            yield "✅ **Reasoning search completed successfully!**\n"
            
        except Exception as e:
            logger.error(f"Reasoning discovery failed: {e}")
            yield f"❌ Reasoning system error: {e}\n"
            yield "🔄 Falling back to simple search...\n"
            
            # Fallback to simple search
            async for chunk in self._discover_sources_simple(user_input, chat_history):
                yield chunk
    
    async def _discover_sources_simple(self, user_input: str, chat_history: Optional[List] = None) -> AsyncGenerator[str, None]:
        """Simple discovery method (existing logic)."""
        # This would contain the existing discovery logic
        # For now, just yield a placeholder
        yield f"🚀 Starting research for: '{user_input}'\n"
        yield "🔄 Connecting to research databases...\n"
        
        # Get available tools
        tools = await self.list_available_tools()
        yield f"✅ Connected to {len(tools)} research databases\n"
        
        if len(tools) == 0:
            yield "⚠️ Research databases temporarily unavailable\n"
            yield "I apologize, but the research databases are temporarily unavailable. Please try again in a few moments.\n"
        else:
            # Execute with direct tools streaming (existing logic)
            yield "🎯 Selecting best database for your query...\n"
            
            # Note: This is a simplified version - the full logic would need to be extracted
            # from the existing discover_sources method
            result = "Simple search completed - please check existing discover_sources method for full implementation."
            yield result
    
    async def _generate_reasoning_follow_ups(self, user_query: str, reasoning_result: FinalResponse) -> None:
        """Generate follow-up questions based on reasoning results."""
        try:
            # Create a summary of the reasoning result for the LLM
            evidence_summary = []
            for evidence in reasoning_result.evidence[:5]:  # Top 5 results
                evidence_summary.append(f"- {evidence.title} (from {evidence.source})")
            
            evidence_text = "\n".join(evidence_summary) if evidence_summary else "No specific evidence found"
            
            follow_up_prompt = f"""Based on this intelligent search result, generate 3-4 strategic follow-up questions.

Original Query: "{user_query}"
Search Strategy: Used reasoning system with {len(reasoning_result.trace)} analysis steps
Key Evidence Found:
{evidence_text}

Search Quality Metrics:
- Sources found: {len(reasoning_result.evidence)}
- Strategies used: {', '.join(reasoning_result.answer.get('strategies_used', []))}
- Search rounds: {reasoning_result.answer.get('search_rounds', 1)}

Generate follow-up questions that:
1. **Refine the search** - More specific criteria or constraints
2. **Expand the scope** - Related areas or broader context  
3. **Validate results** - Cross-reference or verify findings
4. **Apply insights** - Practical next steps or implementation

Return EXACTLY this JSON format:
{{
  "further_questions": [
    {{"id": 0, "question": "refinement question"}},
    {{"id": 1, "question": "expansion question"}},
    {{"id": 2, "question": "validation question"}},
    {{"id": 3, "question": "application question"}}
  ]
}}

Make questions specific, actionable, and leverage the reasoning capabilities."""

            response = await self.llm.ainvoke(follow_up_prompt)
            
            try:
                content = response.content.strip()
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_content = content[json_start:json_end]
                    follow_up_data = json.loads(json_content)
                    
                    if "further_questions" in follow_up_data:
                        self._follow_up_questions = follow_up_data["further_questions"]
                        logger.info(f"✅ Generated {len(self._follow_up_questions)} reasoning-based follow-up questions")
                    
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse reasoning follow-up questions: {e}")
                # Set basic follow-ups as fallback
                self._follow_up_questions = [
                    {"id": 0, "question": "Can you refine this search with more specific criteria?"},
                    {"id": 1, "question": "What related topics should I explore?"},
                    {"id": 2, "question": "How can I validate these findings?"},
                    {"id": 3, "question": "What are the practical next steps?"}
                ]
                    
        except Exception as e:
            logger.error(f"Failed to generate reasoning follow-up questions: {e}")
            self._follow_up_questions = []


async def create_discovery_agent(db_session: AsyncSession, user_id: str, toolrow_api_token: Optional[str] = None, reasoning_enabled: bool = None) -> SourceDiscoveryAgent:
    """Create and initialize a discovery agent."""
    agent = SourceDiscoveryAgent(db_session, user_id, reasoning_enabled=reasoning_enabled)
    try:
        success = await agent.initialize(toolrow_api_token)
        if not success:
            logger.warning("⚠️ Agent initialization returned False, but proceeding with limited functionality")
    except Exception as init_error:
        logger.error(f"❌ Agent initialization failed: {init_error}")
        logger.info("🔄 Proceeding with fallback agent functionality")
        # Ensure agent has minimal functionality even if initialization fails
        if not hasattr(agent, 'agent') or agent.agent is None:
            agent.agent = agent._create_minimal_agent()
    
    # Double-check that we have a working agent
    if not hasattr(agent, 'agent') or agent.agent is None:
        logger.warning("🔧 Creating minimal agent as final fallback")
        agent.agent = agent._create_minimal_agent()
    
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
