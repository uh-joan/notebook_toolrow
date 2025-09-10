/**
 * Types for chat components
 */

export type Source = {
	id: number;
	title: string;
	description: string;
	url: string;
	connectorType?: string;
};

export type Connector = {
	id: number;
	type: string;
	name: string;
	sources?: Source[];
};

export type StatusMessage = {
	id: number;
	message: string;
	type: "info" | "success" | "error" | "warning";
	timestamp: string;
};

export type ChatMessage = {
	id: string;
	role: "user" | "assistant";
	content: string;
	timestamp?: string;
};

// Define message types to match useChat() structure
export type MessageRole = "user" | "assistant" | "system" | "data";

export interface ToolInvocation {
	state: "call" | "result";
	toolCallId: string;
	toolName: string;
	args: any;
	result?: any;
}

export interface ToolInvocationUIPart {
	type: "tool-invocation";
	toolInvocation: ToolInvocation;
}

export type ResearchMode = "QNA" | "REPORT_GENERAL" | "REPORT_DEEP" | "REPORT_DEEPER";

export type DiscoveryMode = "BASIC" | "DEEP" | "COMPREHENSIVE";

// Toolrow MCP types for frontend
export interface ToolrowSource {
	id: string;
	provider: string;
	kind: string;
	canonical_id: string;
	title: string;
	uri?: string;
	metadata: Record<string, any>;
	last_updated?: string;
}

export interface ToolrowInvocation {
	tool: string;
	params: Record<string, any>;
	status: "pending" | "running" | "completed" | "failed";
	result?: any;
	error?: string;
	execution_time_ms?: number;
}

export interface ToolrowCoverage {
	rag_score: number;
	live_data_needed: boolean;
	recommended_tools: string[];
	confidence: number;
}
