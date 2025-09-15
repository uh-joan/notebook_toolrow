"""Claude-powered Source Discovery Agent using Anthropic Messages API."""

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
import uuid
from datetime import datetime, timedelta

import anthropic
from anthropic.types import ToolUseBlock, MessageParam, ToolResultBlockParam
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import get_user_fast_llm, LLMRole
from app.toolrow_mcp.types import EntityRecord, ToolCall
from app.toolrow_mcp.client import toolrow_mcp_manager
from .claude_tools import ClaudeToolMapper, ClaudeToolRegistry
from .response_formatter import ResponseFormatter
from .performance_monitor import PerformanceMonitor, performance_monitor
from .advanced_prompting import AdvancedPromptGenerator, advanced_prompt_generator

logger = logging.getLogger(__name__)


class ConversationSession:
    """Manages conversation history and session state for Discovery Agent."""
    
    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.chat_history: List[Dict[str, Any]] = []
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self._follow_up_questions: List[Dict[str, Any]] = []
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation history."""
        self.chat_history.append({
            "role": "user",
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.last_activity = datetime.utcnow()
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation history."""
        self.chat_history.append({
            "role": "assistant", 
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.last_activity = datetime.utcnow()
    
    def get_recent_history(self, max_messages: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation history."""
        return self.chat_history[-max_messages:] if self.chat_history else []
    
    def set_follow_up_questions(self, questions: List[Dict[str, Any]]) -> None:
        """Store follow-up questions for this session."""
        self._follow_up_questions = questions
        self.last_activity = datetime.utcnow()
    
    def get_follow_up_questions(self) -> List[Dict[str, Any]]:
        """Get stored follow-up questions."""
        return self._follow_up_questions
    
    def is_expired(self, max_age_hours: int = 24) -> bool:
        """Check if session is expired."""
        return datetime.utcnow() - self.last_activity > timedelta(hours=max_age_hours)


class ConversationManager:
    """Global conversation session manager."""
    
    _sessions: Dict[str, ConversationSession] = {}
    
    @classmethod
    def create_session(cls, user_id: str, session_id: Optional[str] = None) -> ConversationSession:
        """Create or retrieve a conversation session."""
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        # Clean up expired sessions
        cls._cleanup_expired_sessions()
        
        if session_id not in cls._sessions:
            cls._sessions[session_id] = ConversationSession(session_id, user_id)
        
        return cls._sessions[session_id]
    
    @classmethod
    def get_session(cls, session_id: str) -> Optional[ConversationSession]:
        """Get an existing conversation session."""
        return cls._sessions.get(session_id)
    
    @classmethod
    def _cleanup_expired_sessions(cls) -> None:
        """Remove expired conversation sessions."""
        expired_ids = [
            session_id for session_id, session in cls._sessions.items() 
            if session.is_expired()
        ]
        for session_id in expired_ids:
            del cls._sessions[session_id]
    
    @classmethod
    def get_user_sessions(cls, user_id: str) -> List[ConversationSession]:
        """Get all active sessions for a user."""
        cls._cleanup_expired_sessions()
        return [session for session in cls._sessions.values() if session.user_id == user_id]


class ClaudeToolExecutor:
    """Execute Claude's tool requests using Toolrow MCP integration."""
    
    def __init__(self, toolrow_token: str):
        self.toolrow_token = toolrow_token
        self.tool_handlers = self._register_tool_handlers()
    
    def _register_tool_handlers(self) -> Dict[str, Any]:
        """Register available tool handlers."""
        return {
            'ct_gov_studies': self._execute_ct_gov_studies,
            'nlm_ct_codes': self._execute_nlm_ct_codes,
            'pubmed_articles': self._execute_pubmed_articles,
            'fda_info': self._execute_fda_drug_info,
            'sec-edgar': self._execute_sec_filings,
            'who-health': self._execute_who_health_data,
        }
    
    async def execute_tool(self, tool_use: ToolUseBlock) -> anthropic.types.ToolResultBlockParam:
        """Execute Claude's tool request and return formatted result with robust error handling."""
        handler = self.tool_handlers.get(tool_use.name)
        if not handler:
            logger.warning(f"Tool '{tool_use.name}' not found in handlers")
            return {
                "tool_use_id": tool_use.id,
                "type": "tool_result",
                "content": f"Tool '{tool_use.name}' is not available. Please try a different research approach.",
                "is_error": True
            }
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                handler(tool_use.input), 
                timeout=60.0  # 1 minute timeout
            )
            
            if result.get('success'):
                formatted_result = self._format_tool_result(result, tool_use.name)
                return {
                    "tool_use_id": tool_use.id,
                    "type": "tool_result", 
                    "content": formatted_result
                }
            else:
                error_msg = result.get('error', 'Unknown tool error')
                logger.warning(f"Tool {tool_use.name} returned error: {error_msg}")
                return {
                    "tool_use_id": tool_use.id,
                    "type": "tool_result",
                    "content": f"Tool execution failed: {error_msg}. You may want to try a different search approach or rephrase your query.",
                    "is_error": True
                }
                
        except asyncio.TimeoutError:
            logger.error(f"Tool {tool_use.name} timed out after 60 seconds")
            return {
                "tool_use_id": tool_use.id,
                "type": "tool_result",
                "content": f"Tool '{tool_use.name}' timed out. The research database may be experiencing high load. Please try again or use a different tool.",
                "is_error": True
            }
        except Exception as e:
            logger.error(f"Tool execution error for {tool_use.name}: {e}", exc_info=True)
            return {
                "tool_use_id": tool_use.id,
                "type": "tool_result",
                "content": f"Unexpected error during research: {str(e)}. Please try rephrasing your query or using a different research approach.",
                "is_error": True
            }
    
    async def _execute_ct_gov_studies(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute clinical trials search."""
        return await self._call_toolrow_subprocess("ct_gov_studies", params)
    
    async def _execute_nlm_ct_codes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute medical codes search.""" 
        return await self._call_toolrow_subprocess("nlm_ct_codes", params)
    
    async def _execute_pubmed_articles(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute PubMed literature search."""
        return await self._call_toolrow_subprocess("pubmed_articles", params)
    
    async def _execute_fda_drug_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute FDA drug information search."""
        return await self._call_toolrow_subprocess("fda_info", params)
    
    async def _execute_sec_filings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SEC filings search."""
        return await self._call_toolrow_subprocess("sec-edgar", params)
    
    async def _execute_who_health_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute WHO health data search."""
        return await self._call_toolrow_subprocess("who-health", params)
    
    async def _call_toolrow_subprocess(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call Toolrow MCP server using the existing MCP client infrastructure."""
        try:
            logger.info(f"🔧 Calling MCP tool {tool_name} via toolrow_mcp_manager with params: {params}")
            
            # Use the existing MCP manager to invoke the tool
            result = await toolrow_mcp_manager.invoke_toolrow_tool(tool_name, params)
            
            logger.info(f"✅ MCP tool {tool_name} returned result: {str(result)[:200]}...")
            return {"success": True, "data": result}
            
        except Exception as e:
            logger.error(f"❌ Failed to invoke MCP tool {tool_name}: {type(e).__name__}: {e}")
            return {"success": False, "error": f"Tool execution failed: {str(e)}"}
    
    def _format_tool_result(self, result: Dict[str, Any], tool_name: str) -> str:
        """Format tool result for Claude."""
        if not result.get('success'):
            return f"Error executing {tool_name}: {result.get('error', 'Unknown error')}"
        
        data = result.get('data', {})
        
        # Extract text content from the response
        if isinstance(data, dict) and 'content' in data:
            content = data['content']
            if isinstance(content, list) and len(content) > 0:
                first_content = content[0]
                if isinstance(first_content, dict) and 'text' in first_content:
                    return first_content['text']
        elif isinstance(data, str):
            return data
        
        return json.dumps(data, indent=2)


class ClaudeDiscoveryAgent:
    """Claude-powered Source Discovery Agent with conversation persistence."""
    
    def __init__(self, db_session: AsyncSession, user_id: str):
        self.db_session = db_session
        self.user_id = user_id
        self.anthropic_client: Optional[anthropic.AsyncAnthropic] = None
        self.tool_executor: Optional[ClaudeToolExecutor] = None
        self.tool_mapper: Optional[ClaudeToolMapper] = None
        self.available_tools: List[Dict[str, Any]] = []
        self.response_formatter = ResponseFormatter()
        self._current_query: str = ""
        self._all_tool_results: List[Dict[str, Any]] = []
        self._all_tool_uses: List[Dict[str, Any]] = []
        self._session_id: Optional[str] = None
        self._conversation_session: Optional[ConversationSession] = None
    
    async def initialize(self, toolrow_api_token: Optional[str] = None, anthropic_api_key: Optional[str] = None) -> bool:
        """Initialize the Claude client and tool executor."""
        try:
            logger.info("Initializing Claude Discovery Agent")
            
            # Initialize Anthropic client
            api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY not found")
                return False
            
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
            logger.info("Claude API client initialized")
            
            # Initialize tool mapper and executor
            if toolrow_api_token:
                self.tool_mapper = ClaudeToolMapper(toolrow_api_token)
                self.tool_executor = ClaudeToolExecutor(toolrow_api_token)
                logger.info("Toolrow tool mapper and executor initialized")
                
                # Load available tools
                await self._load_available_tools()
            else:
                # Use fallback tools if no Toolrow token
                self.available_tools = ClaudeToolRegistry.get_fallback_tools()
                logger.warning("Using fallback tools - no Toolrow token provided")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Claude Discovery Agent: {e}")
            return False
    
    async def _load_available_tools(self, query: str = "") -> None:
        """Load available tools using the tool mapper, optimized for the query."""
        try:
            if self.tool_mapper:
                self.available_tools = await self.tool_mapper.get_claude_tools(query=query)
            else:
                self.available_tools = ClaudeToolRegistry.get_fallback_tools()
                
        except Exception as e:
            logger.error(f"Failed to load available tools: {e}")
            # Fallback to static tools
            self.available_tools = ClaudeToolRegistry.get_fallback_tools()
    
    
    async def discover_sources(self, user_input: str, session_id: Optional[str] = None, chat_history: Optional[List] = None) -> AsyncGenerator[str, None]:
        """Discover sources using Claude with streaming output and robust error handling."""
        try:
            # Validate initialization
            if not self.anthropic_client:
                logger.error("Claude API client not initialized")
                yield "❌ Claude API client not initialized. Please check the ANTHROPIC_API_KEY configuration.\n"
                return
            
            if not self.available_tools:
                logger.warning("No tools available - using fallback mode")
                self.available_tools = ClaudeToolRegistry.get_fallback_tools()
                yield "⚠️ Using limited research tools - some Toolrow services may be unavailable\n"
            
            # Validate user input
            if not user_input or not user_input.strip():
                yield "❌ Please provide a research query.\n"
                return
            
            self._current_query = user_input
            self._all_tool_results = []
            self._all_tool_uses = []
            
            # Initialize conversation session
            self._conversation_session = ConversationManager.create_session(self.user_id, session_id)
            self._session_id = self._conversation_session.session_id
            
            # Add user message to session history
            self._conversation_session.add_user_message(user_input)
            
            # Use session chat history if no external history provided
            if chat_history is None:
                chat_history = self._conversation_session.get_recent_history()
            
            # Optimize available tools for this specific query
            if self.tool_mapper:
                await self._load_available_tools(user_input)
            
            # Start performance monitoring
            import uuid
            self._session_id = str(uuid.uuid4())
            session_metrics = performance_monitor.start_session(self._session_id, user_input)
            
            query_preview = user_input[:100] + "..." if len(user_input) > 100 else user_input
            yield f"🚀 Starting Claude-powered research for: '{query_preview}'\n"
            yield f"🔄 Connected to {len(self.available_tools)} research databases via Claude\n"
            
            # Build messages for Claude with error handling
            try:
                messages = self._build_messages(user_input, chat_history)
            except Exception as e:
                logger.error(f"Failed to build messages: {e}")
                yield f"❌ Error preparing research query: {e}\n"
                return
            
            yield "🧠 Claude is analyzing your query and selecting tools...\n"
            yield "─" * 50 + "\n"
            
            # Stream Claude's response with tool use
            claude_text_response = ""
            try:
                chunk_count = 0
                async for chunk in self._stream_claude_response(messages):
                    # Record streaming metrics
                    if chunk_count == 0:
                        performance_monitor.record_first_chunk(self._session_id)
                    performance_monitor.record_streaming_chunk(self._session_id, len(chunk))
                    chunk_count += 1
                    
                    yield chunk
                    # Collect Claude's text for final formatting
                    claude_text_response += chunk
                
                # Generate formatted response with citations if we have results
                if self._all_tool_results:
                    yield "\n" + "─" * 50 + "\n"
                    yield "📄 **Generating formatted response with citations...**\n"
                    
                    try:
                        formatted_response, citations_list = self.response_formatter.format_research_response(
                            self._current_query,
                            claude_text_response,
                            self._all_tool_results,
                            self._all_tool_uses
                        )
                        
                        if formatted_response != claude_text_response:
                            yield "\n## 📋 Enhanced Research Summary\n\n"
                            yield formatted_response
                    
                    except Exception as e:
                        logger.error(f"Response formatting failed: {e}")
                        yield f"\n⚠️ Response formatting encountered an issue, showing original results.\n"
                    
                    yield "\n" + "─" * 50 + "\n"
                    yield "✨ **Generating follow-up questions based on your search results...**\n"
                    
                    follow_up_questions = await self._generate_follow_up_questions(
                        user_input, self._all_tool_results, chat_history
                    )
                    
                    if follow_up_questions:
                        # Store follow-up questions in conversation session
                        self._conversation_session.set_follow_up_questions(follow_up_questions)
                        
                        yield "\n**💡 Explore these related topics:**\n\n"
                        for i, q in enumerate(follow_up_questions, 1):
                            yield f"{i}. {q['question']}\n"
                    
                    # Add assistant's response to conversation session
                    if claude_text_response.strip():
                        self._conversation_session.add_assistant_message(claude_text_response.strip())
                    
                    # Record response quality metrics
                    performance_monitor.record_response_quality(
                        self._session_id,
                        len(claude_text_response),
                        len(citations_list) if 'citations_list' in locals() else 0,
                        len(follow_up_questions)
                    )
                    
                    yield "\n" + "─" * 50 + "\n"
            except anthropic.APIConnectionError as e:
                error_msg = f"Claude API connection error: {e}"
                logger.error(error_msg)
                performance_monitor.record_error(self._session_id, error_msg)
                yield f"❌ Unable to connect to Claude API. Please check your internet connection and try again.\n"
            except anthropic.AuthenticationError as e:
                error_msg = f"Claude API authentication error: {e}"
                logger.error(error_msg)
                performance_monitor.record_error(self._session_id, error_msg)
                yield f"❌ Claude API authentication failed. Please check the ANTHROPIC_API_KEY configuration.\n"
            except anthropic.RateLimitError as e:
                error_msg = f"Claude API rate limit error: {e}"
                logger.error(error_msg)
                performance_monitor.record_error(self._session_id, error_msg)
                yield f"🔄 **API Rate Limit Reached**\n\nThe research system is currently experiencing high usage. Your request will be retried automatically.\n\n💡 **What's happening:** Anthropic's API has usage limits to ensure fair access for all users.\n\n⏰ **Next steps:** Please wait a moment - the system will complete your request once capacity is available.\n"
            except Exception as e:
                error_msg = f"Claude streaming error: {str(e)}"
                logger.error(error_msg, exc_info=True)
                performance_monitor.record_error(self._session_id, error_msg)
                
                # Provide more helpful error messages based on error type
                error_str = str(e).lower()
                if "rate_limit" in error_str or "429" in error_str or "maximum usage" in error_str:
                    yield f"🔄 **API Rate Limit Reached**\n\nThe research system is experiencing high usage. Your request is being retried automatically, but you may see delays.\n\n💡 **What's happening:** Anthropic's API has usage limits to ensure fair access for all users.\n\n⏰ **Next steps:** Please wait a moment - the system will complete your request once capacity is available.\n"
                elif "authentication" in error_str or "401" in error_str:
                    yield f"❌ Authentication error with AI service. Please contact support.\n"
                elif "connection" in error_str or "network" in error_str:
                    yield f"❌ Connection error. Please check your internet connection and try again.\n"
                else:
                    yield f"❌ Research error: {str(e)}\nPlease try rephrasing your query or try again later.\n"
            
            finally:
                # Always finalize performance monitoring
                if self._session_id:
                    final_metrics = performance_monitor.end_session(self._session_id)
                    if final_metrics:
                        logger.info(f"📊 Session completed: {final_metrics.get_summary()}")
                
        except Exception as e:
            error_msg = f"Unexpected error during research: {str(e)}"
            yield f"❌ {error_msg}\n"
            logger.error(f"Claude discovery error: {e}", exc_info=True)
            if self._session_id:
                performance_monitor.record_error(self._session_id, error_msg)
                performance_monitor.end_session(self._session_id)
    
    def _build_messages(self, user_input: str, chat_history: Optional[List] = None) -> List[Dict[str, Any]]:
        """Build message history for Claude with enhanced context management."""
        messages = []
        
        # Add conversation history with smart filtering
        if chat_history:
            # Take last 6 messages (3 exchanges) for better context
            recent_history = chat_history[-6:]
            
            for msg in recent_history:
                if hasattr(msg, 'content'):  # LangChain message object
                    role = "user" if type(msg).__name__ == "HumanMessage" else "assistant"
                    content = msg.content
                    
                    # Truncate very long assistant messages to preserve context space
                    if role == "assistant" and len(content) > 1500:
                        content = content[:1500] + "\n\n[Response truncated for context management]"
                    
                    messages.append({
                        "role": role,
                        "content": content
                    })
                else:  # Dict format
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    
                    # Same truncation for dict format
                    if role == "assistant" and len(content) > 1500:
                        content = content[:1500] + "\n\n[Response truncated for context management]"
                    
                    messages.append({
                        "role": role,
                        "content": content
                    })
            
            # Add context summary if we have history
            if messages:
                context_note = self._create_context_summary(recent_history)
                if context_note:
                    # Prepend context to the current query
                    user_input = f"{context_note}\n\nCurrent question: {user_input}"
        
        # Add current query
        messages.append({
            "role": "user", 
            "content": user_input
        })
        
        return messages
    
    def _create_context_summary(self, chat_history: List) -> Optional[str]:
        """Create a brief context summary from chat history."""
        if not chat_history:
            return None
        
        # Extract topics and themes from recent conversation
        topics = set()
        user_queries = []
        
        for msg in chat_history:
            if hasattr(msg, 'content'):
                content = msg.content.lower()
                if type(msg).__name__ == "HumanMessage":
                    user_queries.append(msg.content)
            else:
                content = msg.get('content', '').lower()
                if msg.get('role') == 'user':
                    user_queries.append(msg.get('content', ''))
            
            # Extract key topics
            medical_terms = ['diabetes', 'cancer', 'treatment', 'clinical', 'trial', 'drug', 'patient']
            for term in medical_terms:
                if term in content:
                    topics.add(term)
        
        if user_queries:
            recent_query = user_queries[-1] if user_queries else ""
            context_prefix = f"[Context: Continuing conversation about {', '.join(list(topics)[:3]) if topics else 'research topics'}. Previous query: '{recent_query[:100]}...']"
            return context_prefix
        
        return None
    
    async def _stream_claude_response(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Stream Claude's response with parallel tool execution and enhanced orchestration."""
        try:
            # Extract context from conversation history
            context_summary = None
            if len(messages) > 1:
                recent_context = " ".join([msg.get("content", "")[:200] for msg in messages[-3:-1] if msg.get("role") == "user"])
                if recent_context:
                    context_summary = f"Recent conversation context: {recent_context[:300]}..."
            
            # Generate optimized system prompt based on current query
            current_query = messages[-1].get("content", "") if messages else ""
            system_prompt = self._get_system_prompt(current_query, context_summary)
            
            # Convert messages to proper format
            claude_messages = []
            for msg in messages:
                claude_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            conversation_round = 1
            
            while True:
                logger.info(f"🔄 Claude conversation round {conversation_round}")
                
                # Debug log the tools being sent to Claude API
                logger.info(f"🔧 Sending {len(self.available_tools)} tools to Claude API")
                for i, tool in enumerate(self.available_tools[:2]):  # Log first 2 tools for debugging
                    logger.info(f"🔧 Tool {i}: {tool.get('name')} - Type: {tool.get('type')} - Has custom: {'custom' in tool}")
                    if 'custom' in tool and 'input_schema' in tool['custom']:
                        schema = tool['custom']['input_schema']
                        logger.info(f"🔧 Tool {i} input_schema keys: {list(schema.keys()) if isinstance(schema, dict) else 'NOT_DICT'}")
                
                # Start streaming with Claude using latest optimizations
                response = await self.anthropic_client.beta.messages.create(
                    model="claude-sonnet-4-20250514",  # Use Claude Sonnet 4 for optimal performance
                    max_tokens=4096,
                    temperature=0.1,
                    system=system_prompt,
                    messages=claude_messages,
                    tools=self.available_tools,
                    betas=[
                        "token-efficient-tools-2025-02-19",  # Save up to 70% tokens
                        "fine-grained-tool-streaming-2025-05-14"  # Faster tool parameter streaming
                    ]
                )
                
                # Process the response
                tool_uses = []
                text_content = ""
                
                for content_block in response.content:
                    if content_block.type == "text":
                        text_content += content_block.text
                        yield content_block.text
                    elif content_block.type == "tool_use":
                        tool_uses.append(content_block)
                        
                        # Store tool use info for formatting
                        tool_use_info = {
                            "name": content_block.name,
                            "input": content_block.input if hasattr(content_block, 'input') else {}
                        }
                        self._all_tool_uses.append(tool_use_info)
                
                # If no tool uses, we're done
                if not tool_uses:
                    break
                
                # Enhanced parallel tool execution
                if len(tool_uses) > 1:
                    yield f"\n\n🚀 **Executing {len(tool_uses)} tools in parallel:**\n"
                    for tool_use in tool_uses:
                        yield f"• **{tool_use.name}**: {json.dumps(tool_use.input, indent=2)[:100]}...\n"
                else:
                    yield f"\n\n🔧 **Using tool: {tool_uses[0].name}**\n"
                    yield f"Parameters: {json.dumps(tool_uses[0].input, indent=2)}\n"
                
                yield "\n🔍 **Executing research tools...**\n"
                
                # Add assistant message with tool uses
                claude_messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                
                # Execute tools in parallel for better performance
                tool_results = await self._execute_tools_parallel(tool_uses)
                
                # Store results for follow-up question generation and formatting
                self._last_tool_results = tool_results
                self._all_tool_results.extend(tool_results)
                
                # Stream results as they become available
                for i, (tool_use, result) in enumerate(zip(tool_uses, tool_results)):
                    yield f"\n📊 **{tool_use.name}** results:\n"
                    
                    if result.get("content") and not result.get("is_error"):
                        preview = str(result["content"])[:300] + "..." if len(str(result["content"])) > 300 else str(result["content"])
                        yield f"✅ {preview}\n"
                    elif result.get("is_error"):
                        yield f"❌ Error: {result.get('content', 'Unknown error')}\n"
                
                # Add tool results to conversation
                claude_messages.append({
                    "role": "user", 
                    "content": tool_results
                })
                
                yield f"\n🧠 **Claude is synthesizing results from {len(tool_uses)} sources...**\n"
                conversation_round += 1
                
                # Prevent infinite loops
                if conversation_round > 5:
                    yield f"\n⚠️ Maximum conversation rounds reached. Finalizing response...\n"
                    break
                
        except Exception as e:
            yield f"\n❌ Error in Claude streaming: {str(e)}\n"
            logger.error(f"Claude streaming error: {e}")
    
    async def _execute_tools_parallel(self, tool_uses: List[ToolUseBlock]) -> List[Dict[str, Any]]:
        """Execute multiple tools in parallel with performance monitoring."""
        try:
            # Create tasks for parallel execution with monitoring
            tasks = []
            for tool_use in tool_uses:
                async def monitored_tool_execution(tu=tool_use):
                    async with performance_monitor.monitor_tool_execution(
                        self._session_id, tu.name, is_parallel=len(tool_uses) > 1
                    ):
                        return await self.tool_executor.execute_tool(tu)
                
                task = asyncio.create_task(monitored_tool_execution())
                tasks.append(task)
            
            # Wait for all tools to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Parallel tool execution failed for {tool_uses[i].name}: {result}")
                    processed_results.append({
                        "tool_use_id": tool_uses[i].id,
                        "type": "tool_result",
                        "content": f"Tool execution failed: {str(result)}",
                        "is_error": True
                    })
                else:
                    processed_results.append(result)
            
            logger.info(f"✅ Executed {len(tool_uses)} tools in parallel")
            return processed_results
            
        except Exception as e:
            logger.error(f"Parallel tool execution error: {e}")
            # Return error results for all tools
            return [
                {
                    "tool_use_id": tool_use.id,
                    "type": "tool_result", 
                    "content": f"Parallel execution error: {str(e)}",
                    "is_error": True
                }
                for tool_use in tool_uses
            ]
    
    
    def _get_system_prompt(self, query: Optional[str] = None, context: Optional[str] = None) -> str:
        """Get optimized system prompt based on query analysis."""
        if query:
            # Analyze query for optimization
            query_type, complexity = advanced_prompt_generator.analyze_query(query)
            
            # Generate optimized prompt
            optimized_prompt = advanced_prompt_generator.generate_system_prompt(
                query_type=query_type,
                complexity=complexity,
                available_tools=self.available_tools,
                context=context
            )
            
            logger.info(f"🎯 Query classified as {query_type.value} with {complexity.value} complexity")
            return optimized_prompt
        else:
            # Fallback to generic prompt
            available_tools_desc = ClaudeToolRegistry.get_system_prompt_tools_section(self.available_tools)
            
            return f"""You are SourceBook Discover, an expert research assistant specializing in finding and analyzing information from authoritative sources including clinical trials, medical codes, FDA databases, PubMed literature, and regulatory filings.

RESEARCH STRATEGY:
1. **Query Analysis**: Determine if the query requires single or multiple data sources
2. **Parallel Tool Use**: For comprehensive queries, use multiple tools simultaneously to gather diverse perspectives
3. **Tool Chaining**: Use results from one tool to inform parameters for subsequent tools when appropriate
4. **Synthesis**: Combine results from multiple sources into coherent, well-cited responses

Available research tools:
{available_tools_desc}

RESPONSE FORMATTING:
- **Executive Summary**: Start with key findings across all sources
- **Source-Specific Results**: Organize results by tool/database used
- **Cross-References**: Highlight connections between different sources
- **Citations**: Include proper source attribution with URLs when available
- **Next Steps**: Suggest logical follow-up queries based on findings

QUALITY STANDARDS:
- Prioritize authoritative, primary sources
- Include publication dates, study phases, and reliability indicators
- Provide direct links to source materials when available
- Maintain clear separation between different data sources
- Generate relevant follow-up questions that build on current findings
- Use parallel tool execution to provide comprehensive coverage when appropriate"""
    
    async def _generate_follow_up_questions(self, user_query: str, tool_results: List[Dict[str, Any]], chat_history: Optional[List] = None) -> List[Dict[str, Any]]:
        """Generate contextual follow-up questions based on search results and conversation history."""
        try:
            # Build context from tool results
            results_summary = []
            tools_used = []
            
            for result in tool_results:
                if not result.get("is_error") and result.get("content"):
                    # Extract tool name from tool_use_id pattern or content
                    content_preview = str(result["content"])[:300]
                    results_summary.append(content_preview)
                    
                    # Try to determine which tool was used
                    tool_id = result.get("tool_use_id", "")
                    if "ct_gov" in content_preview.lower():
                        tools_used.append("Clinical Trials")
                    elif "icd" in content_preview.lower():
                        tools_used.append("Medical Codes")
                    elif "pubmed" in content_preview.lower():
                        tools_used.append("Literature")
                    elif "fda" in content_preview.lower():
                        tools_used.append("FDA Data")
                    elif "sec" in content_preview.lower():
                        tools_used.append("SEC Data")
                    elif "who" in content_preview.lower():
                        tools_used.append("WHO Data")
            
            # Build conversation context
            history_context = ""
            if chat_history:
                recent_queries = []
                for msg in chat_history[-3:]:
                    if hasattr(msg, 'content') and type(msg).__name__ == "HumanMessage":
                        recent_queries.append(msg.content)
                
                if recent_queries:
                    history_context = f"Previous queries: {', '.join(recent_queries)}"
            
            # Create prompt for follow-up question generation
            follow_up_prompt = f"""Based on the research results, generate 4 relevant follow-up questions that would help the user explore related topics or dive deeper into specific aspects.

Original Query: "{user_query}"
{history_context}

Tools Used: {', '.join(set(tools_used)) if tools_used else 'Multiple research databases'}

Research Results Summary:
{'. '.join(results_summary[:3]) if results_summary else 'Various research data retrieved'}

Generate questions that:
1. **Refine/Filter**: Help narrow down or filter the current results
2. **Expand Scope**: Explore related topics or broader context  
3. **Deep Dive**: Focus on specific technical aspects or details
4. **Practical Application**: How to use or apply the findings

Return EXACTLY this JSON format:
{{
  "further_questions": [
    {{"id": 0, "question": "question 1"}},
    {{"id": 1, "question": "question 2"}},
    {{"id": 2, "question": "question 3"}},
    {{"id": 3, "question": "question 4"}}
  ]
}}"""

            # Use Claude to generate contextual follow-up questions  
            response = await self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": follow_up_prompt}]
            )
            
            response_text = response.content[0].text if response.content else "{}"
            
            # Parse the JSON response
            try:
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    parsed_data = json.loads(json_str)
                    questions = parsed_data.get("further_questions", [])
                    
                    # Store for later retrieval
                    self._follow_up_questions = questions
                    logger.info(f"✨ Generated {len(questions)} follow-up questions")
                    return questions
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse follow-up questions JSON: {e}")
            
            return []
                
        except Exception as e:
            logger.error(f"Follow-up question generation failed: {e}")
            return []
    
    def get_follow_up_questions(self) -> List[Dict[str, Any]]:
        """Get the last generated follow-up questions."""
        if self._conversation_session:
            return self._conversation_session.get_follow_up_questions()
        return []
    
    def clear_follow_up_questions(self) -> None:
        """Clear the stored follow-up questions."""
        if self._conversation_session:
            self._conversation_session.set_follow_up_questions([])
    
    def get_session_id(self) -> Optional[str]:
        """Get the current conversation session ID."""
        return self._session_id
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the current conversation history."""
        if self._conversation_session:
            return self._conversation_session.chat_history
        return []
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.anthropic_client:
            await self.anthropic_client.close()


async def create_claude_discovery_agent(
    db_session: AsyncSession, 
    user_id: str, 
    toolrow_api_token: Optional[str] = None,
    anthropic_api_key: Optional[str] = None
) -> ClaudeDiscoveryAgent:
    """Create and initialize a Claude discovery agent."""
    agent = ClaudeDiscoveryAgent(db_session, user_id)
    
    success = await agent.initialize(toolrow_api_token, anthropic_api_key)
    if not success:
        logger.warning("⚠️ Claude agent initialization failed")
        raise Exception("Failed to initialize Claude Discovery Agent")
    
    return agent