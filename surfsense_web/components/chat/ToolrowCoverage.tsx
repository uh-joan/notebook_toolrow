"use client";

import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { 
	Database, 
	Zap, 
	Info, 
	CheckCircle, 
	AlertTriangle, 
	XCircle,
	TrendingUp,
	Clock
} from "lucide-react";
import { useState } from "react";
import type { ToolrowCoverage } from "@/components/chat/types";

interface ToolrowCoverageProps {
	coverage: ToolrowCoverage | null;
	loading?: boolean;
	onRequestLiveData?: () => void;
}

function getCoverageStatus(score: number) {
	if (score >= 0.8) return { 
		status: 'excellent', 
		icon: CheckCircle, 
		color: 'text-green-600', 
		bgColor: 'bg-green-50',
		label: 'Excellent Coverage'
	};
	if (score >= 0.6) return { 
		status: 'good', 
		icon: TrendingUp, 
		color: 'text-blue-600', 
		bgColor: 'bg-blue-50',
		label: 'Good Coverage'
	};
	if (score >= 0.3) return { 
		status: 'partial', 
		icon: AlertTriangle, 
		color: 'text-yellow-600', 
		bgColor: 'bg-yellow-50',
		label: 'Partial Coverage'
	};
	return { 
		status: 'poor', 
		icon: XCircle, 
		color: 'text-red-600', 
		bgColor: 'bg-red-50',
		label: 'Limited Coverage'
	};
}

export default function ToolrowCoverageIndicator({ 
	coverage, 
	loading = false, 
	onRequestLiveData 
}: ToolrowCoverageProps) {
	const [expanded, setExpanded] = useState(false);

	if (loading) {
		return (
			<Card className="w-full">
				<CardHeader className="pb-3">
					<div className="flex items-center gap-2">
						<Clock className="h-4 w-4 animate-spin" />
						<CardTitle className="text-sm">Analyzing Coverage...</CardTitle>
					</div>
				</CardHeader>
				<CardContent>
					<Progress value={0} className="h-2" />
				</CardContent>
			</Card>
		);
	}

	if (!coverage) {
		return null;
	}

	const { status, icon: StatusIcon, color, bgColor, label } = getCoverageStatus(coverage.rag_score);
	const percentage = Math.round(coverage.rag_score * 100);

	return (
		<Card className="w-full">
			<CardHeader className="pb-3">
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2">
						<Database className="h-4 w-4" />
						<CardTitle className="text-sm">Knowledge Coverage</CardTitle>
						<TooltipProvider>
							<Tooltip>
								<TooltipTrigger>
									<Info className="h-3 w-3 text-muted-foreground" />
								</TooltipTrigger>
								<TooltipContent>
									<p className="text-xs max-w-xs">
										Shows how well your documents cover this query. 
										Low scores suggest live data might be helpful.
									</p>
								</TooltipContent>
							</Tooltip>
						</TooltipProvider>
					</div>
					<Button
						variant="ghost"
						size="sm"
						className="h-6 px-2 text-xs"
						onClick={() => setExpanded(!expanded)}
					>
						{expanded ? "Less" : "Details"}
					</Button>
				</div>
			</CardHeader>
			<CardContent className="space-y-3">
				<div className="space-y-2">
					<div className="flex items-center justify-between">
						<div className="flex items-center gap-2">
							<StatusIcon className={`h-4 w-4 ${color}`} />
							<span className="text-sm font-medium">{label}</span>
						</div>
						<Badge variant="outline" className={`${bgColor} border-0`}>
							{percentage}%
						</Badge>
					</div>
					<Progress value={percentage} className="h-2" />
				</div>

				{coverage.live_data_needed && (
					<div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border border-blue-200">
						<div className="flex items-center gap-2">
							<Zap className="h-4 w-4 text-blue-600" />
							<div>
								<p className="text-sm font-medium text-blue-900">
									Live Data Recommended
								</p>
								<p className="text-xs text-blue-700">
									Real-time sources could improve this answer
								</p>
							</div>
						</div>
						{onRequestLiveData && (
							<Button
								size="sm"
								variant="outline"
								className="bg-white border-blue-300 text-blue-700 hover:bg-blue-50"
								onClick={onRequestLiveData}
							>
								Get Live Data
							</Button>
						)}
					</div>
				)}

				{expanded && (
					<div className="space-y-3 pt-2 border-t">
						<div>
							<h5 className="text-xs font-medium text-muted-foreground mb-2">Analysis Details</h5>
							<div className="grid grid-cols-2 gap-3 text-xs">
								<div>
									<span className="text-muted-foreground">RAG Score:</span>
									<span className="ml-1 font-medium">{coverage.rag_score.toFixed(2)}</span>
								</div>
								<div>
									<span className="text-muted-foreground">Confidence:</span>
									<span className="ml-1 font-medium">{Math.round(coverage.confidence * 100)}%</span>
								</div>
							</div>
						</div>

						{coverage.recommended_tools.length > 0 && (
							<div>
								<h5 className="text-xs font-medium text-muted-foreground mb-2">
									Recommended Tools
								</h5>
								<div className="flex flex-wrap gap-1">
									{coverage.recommended_tools.map((tool, index) => (
										<Badge key={index} variant="secondary" className="text-xs">
											{tool}
										</Badge>
									))}
								</div>
							</div>
						)}

						<div className="text-xs text-muted-foreground space-y-1">
							<p>• <strong>High scores (80%+):</strong> Your documents cover this well</p>
							<p>• <strong>Medium scores (60-80%):</strong> Good coverage, live data might help</p>
							<p>• <strong>Low scores (&lt;60%):</strong> Live data strongly recommended</p>
						</div>
					</div>
				)}
			</CardContent>
		</Card>
	);
}
