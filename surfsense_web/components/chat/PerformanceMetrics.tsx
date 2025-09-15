"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BarChart3, Clock, Cpu, Zap, TrendingUp, ChevronDown, ChevronUp } from "lucide-react";

interface PerformanceMetrics {
	session_id?: string;
	total_duration_ms?: number;
	token_usage?: {
		input: number;
		output: number;
		total: number;
		efficiency_ratio: number;
	};
	tool_metrics?: {
		tools_used: number;
		parallel_calls: number;
		sequential_calls: number;
		avg_tool_time: number;
		fastest_tool: number;
		slowest_tool: number;
	};
	response_quality?: {
		response_length: number;
		citations: number;
		follow_ups: number;
	};
	streaming?: {
		first_chunk_latency: number;
		total_chunks: number;
	};
	success_rate?: number;
	query_type?: string;
	complexity?: string;
	optimization_recommendations?: string[];
}

interface Message {
	id: string;
	role: "user" | "assistant";
	content: string | Array<{type: string; text: string}>;
	data?: {
		performance_metrics?: PerformanceMetrics;
		[key: string]: any;
	};
}

interface PerformanceMetricsProps {
	message: Message;
	compact?: boolean;
}

export default function PerformanceMetrics({ message, compact = false }: PerformanceMetricsProps) {
	const [isExpanded, setIsExpanded] = useState(false);

	if (!message || message.role !== "assistant" || !message.data?.performance_metrics) {
		return null;
	}

	const metrics = message.data.performance_metrics;

	// Format duration in a human-readable way
	const formatDuration = (ms: number | undefined): string => {
		if (!ms) return "N/A";
		if (ms < 1000) return `${Math.round(ms)}ms`;
		return `${(ms / 1000).toFixed(1)}s`;
	};

	// Get performance status color based on metrics
	const getPerformanceStatus = (): { color: string; status: string; icon: React.ReactNode } => {
		const duration = metrics.total_duration_ms || 0;
		const success_rate = metrics.success_rate || 0;
		
		if (success_rate > 0.95 && duration < 5000) {
			return { color: "text-green-600", status: "Excellent", icon: <TrendingUp className="w-4 h-4" /> };
		} else if (success_rate > 0.9 && duration < 10000) {
			return { color: "text-blue-600", status: "Good", icon: <BarChart3 className="w-4 h-4" /> };
		} else if (success_rate > 0.8 && duration < 15000) {
			return { color: "text-yellow-600", status: "Fair", icon: <Clock className="w-4 h-4" /> };
		} else {
			return { color: "text-red-600", status: "Poor", icon: <Zap className="w-4 h-4" /> };
		}
	};

	const performanceStatus = getPerformanceStatus();

	if (compact) {
		return (
			<div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
				<div className={`flex items-center gap-1 ${performanceStatus.color}`}>
					{performanceStatus.icon}
					<span>{performanceStatus.status}</span>
				</div>
				<span>•</span>
				<span>{formatDuration(metrics.total_duration_ms)}</span>
				{metrics.token_usage && (
					<>
						<span>•</span>
						<span>{metrics.token_usage.total} tokens</span>
					</>
				)}
				{metrics.tool_metrics && (
					<>
						<span>•</span>
						<span>{metrics.tool_metrics.tools_used} tools</span>
					</>
				)}
			</div>
		);
	}

	return (
		<Card className="mt-4 bg-slate-50 border-slate-200">
			<CardHeader className="pb-3">
				<div className="flex items-center justify-between">
					<CardTitle className="text-sm font-medium flex items-center gap-2">
						<Cpu className="w-4 h-4 text-blue-600" />
						Claude Performance Metrics
						<Badge variant="outline" className={`text-xs ${performanceStatus.color}`}>
							{performanceStatus.status}
						</Badge>
					</CardTitle>
					<Button
						variant="ghost"
						size="sm"
						onClick={() => setIsExpanded(!isExpanded)}
						className="h-6 w-6 p-0"
					>
						{isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
					</Button>
				</div>
			</CardHeader>
			
			<CardContent className="pt-0">
				{/* Always visible summary */}
				<div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
					<div className="text-center">
						<div className="text-lg font-semibold text-blue-600">
							{formatDuration(metrics.total_duration_ms)}
						</div>
						<div className="text-xs text-muted-foreground">Response Time</div>
					</div>
					
					{metrics.token_usage && (
						<div className="text-center">
							<div className="text-lg font-semibold text-green-600">
								{metrics.token_usage.total}
							</div>
							<div className="text-xs text-muted-foreground">
								Tokens ({metrics.token_usage.efficiency_ratio.toFixed(1)}x)
							</div>
						</div>
					)}
					
					{metrics.tool_metrics && (
						<div className="text-center">
							<div className="text-lg font-semibold text-purple-600">
								{metrics.tool_metrics.tools_used}
							</div>
							<div className="text-xs text-muted-foreground">Tools Used</div>
						</div>
					)}
					
					<div className="text-center">
						<div className="text-lg font-semibold text-orange-600">
							{((metrics.success_rate || 0) * 100).toFixed(0)}%
						</div>
						<div className="text-xs text-muted-foreground">Success Rate</div>
					</div>
				</div>

				{/* Expandable detailed metrics */}
				{isExpanded && (
					<div className="space-y-4 pt-3 border-t border-slate-200">
						{/* Query Analysis */}
						{(metrics.query_type || metrics.complexity) && (
							<div>
								<h4 className="text-sm font-medium mb-2">Query Analysis</h4>
								<div className="flex gap-2">
									{metrics.query_type && (
										<Badge variant="secondary" className="text-xs">
											Type: {metrics.query_type.replace('_', ' ')}
										</Badge>
									)}
									{metrics.complexity && (
										<Badge variant="outline" className="text-xs">
											Complexity: {metrics.complexity}
										</Badge>
									)}
								</div>
							</div>
						)}

						{/* Token Usage Details */}
						{metrics.token_usage && (
							<div>
								<h4 className="text-sm font-medium mb-2">Token Usage</h4>
								<div className="grid grid-cols-3 gap-2 text-sm">
									<div>Input: <span className="font-medium">{metrics.token_usage.input}</span></div>
									<div>Output: <span className="font-medium">{metrics.token_usage.output}</span></div>
									<div>Efficiency: <span className="font-medium">{metrics.token_usage.efficiency_ratio.toFixed(2)}x</span></div>
								</div>
							</div>
						)}

						{/* Tool Execution Details */}
						{metrics.tool_metrics && (
							<div>
								<h4 className="text-sm font-medium mb-2">Tool Execution</h4>
								<div className="grid grid-cols-2 gap-2 text-sm">
									<div>Parallel calls: <span className="font-medium">{metrics.tool_metrics.parallel_calls}</span></div>
									<div>Sequential calls: <span className="font-medium">{metrics.tool_metrics.sequential_calls}</span></div>
									<div>Avg time: <span className="font-medium">{formatDuration(metrics.tool_metrics.avg_tool_time)}</span></div>
									<div>Fastest: <span className="font-medium">{formatDuration(metrics.tool_metrics.fastest_tool)}</span></div>
								</div>
							</div>
						)}

						{/* Streaming Performance */}
						{metrics.streaming && (
							<div>
								<h4 className="text-sm font-medium mb-2">Streaming Performance</h4>
								<div className="grid grid-cols-2 gap-2 text-sm">
									<div>First chunk: <span className="font-medium">{formatDuration(metrics.streaming.first_chunk_latency)}</span></div>
									<div>Total chunks: <span className="font-medium">{metrics.streaming.total_chunks}</span></div>
								</div>
							</div>
						)}

						{/* Optimization Recommendations */}
						{metrics.optimization_recommendations && metrics.optimization_recommendations.length > 0 && (
							<div>
								<h4 className="text-sm font-medium mb-2">Optimization Recommendations</h4>
								<div className="space-y-1">
									{metrics.optimization_recommendations.map((rec, index) => (
										<div key={index} className="text-xs text-muted-foreground bg-yellow-50 p-2 rounded">
											💡 {rec}
										</div>
									))}
								</div>
							</div>
						)}
					</div>
				)}
			</CardContent>
		</Card>
	);
}