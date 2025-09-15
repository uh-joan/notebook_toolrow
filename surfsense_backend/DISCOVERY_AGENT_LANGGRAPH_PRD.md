# PRD: LangGraph-Based Discovery Agent

## Overview
Refactor the current Discovery Agent from a stateless Claude API-based implementation to a stateful LangGraph workflow, ensuring proper conversation continuity and eliminating the need for timing-based hacks.

## Problem Statement

### Current Issues
1. **Conversation Continuity Problem**: Follow-up questions create new Chat records instead of continuing existing conversations
2. **Timing-Based Hack**: Current solution uses arbitrary 10-minute windows to detect follow-ups - unintuitive and fragile
3. **Architectural Inconsistency**: Discovery Agent uses direct Claude API while Research Agent uses LangGraph with proper state management
4. **Frontend Complexity**: Current approach requires complex frontend state management that doesn't work reliably

### Root Cause
The Discovery Agent is **stateless** - each request is independent without persistent conversation context, unlike the Research Agent which maintains state through LangGraph.

## Goals

### Primary Goals
1. **Eliminate duplicate Chat creation** - Follow-up questions should continue existing conversations
2. **Remove timing-based hack** - Replace with proper stateful conversation management
3. **Architectural consistency** - Align Discovery Agent with Research Agent's proven LangGraph approach
4. **Conversation persistence** - Maintain chat history across multiple turns naturally

### Secondary Goals
1. **Improved maintainability** - Structured workflow easier to extend and debug
2. **Better error handling** - LangGraph provides better state management for error recovery
3. **Enhanced extensibility** - Easy to add new discovery workflow steps

## Solution: LangGraph-Based Discovery Agent

### Architecture Overview
Transform Discovery Agent from:
```
Direct Claude API → Manual Session Management → Timing-based Follow-up Detection
```

To:
```
LangGraph StateGraph → Persistent State → Natural Conversation Continuity
```

### Key Components

#### 1. State Management
```python
class DiscoveryState:
    # Conversation context
    chat_history: List[MessageParam] = field(default_factory=list)
    session_id: str = None
    
    # Current request
    user_query: str = None
    search_space_id: int = None
    selected_tools: List[str] = field(default_factory=list)
    
    # Discovery results
    discovered_sources: List[Dict] = field(default_factory=list)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    
    # Output
    formatted_response: str = None
    follow_up_questions: List[str] = field(default_factory=list)
```

#### 2. Workflow Nodes
1. **Initialize Session** - Set up conversation context
2. **Process Query** - Classify and prepare user query  
3. **Tool Discovery** - Select appropriate tools based on query
4. **Execute Tools** - Run selected tools (clinical trials, FDA, etc.)
5. **Format Response** - Structure results for frontend
6. **Generate Follow-ups** - Create relevant follow-up questions

#### 3. State Persistence
- **Session Storage**: Use LangGraph's built-in state persistence
- **Database Integration**: Save final results to Chat model
- **Conversation Threading**: Automatic conversation continuity

### Technical Implementation

#### Phase 1: Core LangGraph Structure
1. Create `DiscoveryState` class
2. Build basic `StateGraph` with essential nodes
3. Implement state persistence configuration
4. Create graph compilation and execution logic

#### Phase 2: Node Implementation  
1. Port existing tool discovery logic to graph nodes
2. Integrate Claude API calls within LangGraph context
3. Maintain existing Toolrow MCP tool integrations
4. Implement response formatting as graph node

#### Phase 3: Integration & Testing
1. Update discovery routes to use new LangGraph agent
2. Ensure conversation persistence works correctly
3. Remove timing-based follow-up detection
4. Test conversation continuity across multiple turns

#### Phase 4: Cleanup & Documentation
1. Remove old stateless Discovery Agent code
2. Update API documentation
3. Add comprehensive tests
4. Performance optimization

## Success Criteria

### Functional Requirements
- ✅ **No duplicate chats**: Follow-up questions continue existing conversations
- ✅ **Natural conversation flow**: Multi-turn conversations work seamlessly  
- ✅ **Tool integration preserved**: All existing Toolrow MCP tools work
- ✅ **Response format maintained**: Frontend receives same data structure
- ✅ **Performance maintained**: Response times comparable to current implementation

### Technical Requirements
- ✅ **LangGraph integration**: Uses StateGraph for workflow management
- ✅ **State persistence**: Conversation history maintained across requests
- ✅ **Error handling**: Robust error recovery through state management
- ✅ **Code consistency**: Follows same patterns as Research Agent
- ✅ **Clean architecture**: Removes all timing-based hacks

### User Experience
- ✅ **Transparent transition**: No changes needed in frontend interface
- ✅ **Improved reliability**: Conversation continuity works consistently
- ✅ **Better performance**: No arbitrary time-based restrictions

## Non-Goals
- Changing the Discovery Agent's core functionality
- Modifying the existing tool integrations (Toolrow MCP)
- Altering the frontend interface
- Performance improvements beyond maintaining current levels

## Risks & Mitigations

### Technical Risks
1. **LangGraph Learning Curve**
   - *Mitigation*: Follow Research Agent patterns closely
   
2. **Tool Integration Compatibility**
   - *Mitigation*: Port tools incrementally, test thoroughly
   
3. **State Persistence Complexity**
   - *Mitigation*: Use LangGraph's built-in persistence mechanisms

### User Experience Risks
1. **Regression in Functionality** 
   - *Mitigation*: Comprehensive testing, gradual rollout
   
2. **Performance Degradation**
   - *Mitigation*: Profile and optimize critical paths

## Timeline Estimate

### Phase 1: Core Structure (2-3 hours)
- State class definition
- Basic graph setup
- Compilation logic

### Phase 2: Node Implementation (4-5 hours) 
- Tool discovery nodes
- Claude API integration
- Response formatting

### Phase 3: Integration (2-3 hours)
- Route updates
- Testing conversation continuity
- Remove old code

### Phase 4: Cleanup (1-2 hours)
- Documentation
- Final testing
- Code cleanup

**Total Estimate: 9-13 hours**

## Implementation Plan

### Immediate Next Steps
1. Create `DiscoveryState` class based on Research Agent patterns
2. Set up basic `StateGraph` structure
3. Port the simplest node (query processing) first
4. Test basic graph execution

### Validation Approach
- Test conversation continuity with multiple follow-up questions
- Verify no duplicate Chat records are created  
- Confirm all existing tools still work
- Performance benchmarking against current implementation

## Approval & Sign-off

This PRD provides a clear path to eliminate the timing-based hack and implement proper conversation continuity through proven LangGraph patterns. The implementation follows established architecture from the Research Agent, reducing risk and ensuring consistency.

**Ready to proceed with Phase 1 implementation?**