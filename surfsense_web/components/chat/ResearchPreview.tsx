"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { 
	Zap, 
	Database, 
	Brain, 
	Target, 
	TrendingUp, 
	Info,
	Clock,
	CheckCircle,
	AlertTriangle,
	Eye,
	Send
} from "lucide-react";
import { useEnhancedResearch } from "@/hooks/use-research";
import ToolrowCoverageIndicator from "./ToolrowCoverage";
import type { ToolrowCoverage } from "@/components/chat/types";

interface ResearchPreviewProps {
	query: string;
	searchSpaceId: string;
	onProceed?: (useLiveData: boolean) => void;
	onCancel?: () => void;
	autoAnalyze?: boolean;
}

function IntentPreviewCard({ intent }: { intent: any }) {
	if (!intent) return null;

	const getConfidenceColor = (confidence: number) => {
		if (confidence >= 0.8) return "text-green-600 bg-green-50";
		if (confidence >= 0.6) return "text-blue-600 bg-blue-50";
		return "text-yellow-600 bg-yellow-50";
	};

	return (
		<Card>
			<CardHeader className="pb-3">
				<div className="flex items-center gap-2">
					<Brain className="h-4 w-4" />
					<CardTitle className="text-sm">Intent Analysis</CardTitle>
				</div>
			</CardHeader>
			<CardContent className="space-y-3">
				<div className="flex items-center gap-2">
					<Target className="h-4 w-4 text-muted-foreground" />
					<span className="text-sm font-medium capitalize">{intent.category.replace('_', ' ')}</span>
					<Badge 
						variant="outline" 
						className={`border-0 ${getConfidenceColor(intent.confidence)}`}
					>
						{Math.round(intent.confidence * 100)}% confident
					</Badge>
				</div>

				{intent.entities.length > 0 && (
					<div>
						<h5 className="text-xs font-medium text-muted-foreground mb-2">Key Entities:</h5>
						<div className="flex flex-wrap gap-1">
							{intent.entities.map((entity: string, index: number) => (
								<Badge key={index} variant="secondary" className="text-xs">
									{entity}
								</Badge>
							))}
						</div>
					</div>
				)}

				{intent.recommended_tools.length > 0 && (
					<div>
						<h5 className="text-xs font-medium text-muted-foreground mb-2">Recommended Tools:</h5>
						<div className="flex flex-wrap gap-1">
							{intent.recommended_tools.map((tool: string, index: number) => (
								<Badge key={index} variant="outline" className="text-xs">
									<Zap className="h-3 w-3 mr-1" />
									{tool}
								</Badge>
							))}
						</div>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

export default function ResearchPreview({ 
	query, 
	searchSpaceId, 
	onProceed, 
	onCancel,
	autoAnalyze = true 
}: ResearchPreviewProps) {
	const [showPreview, setShowPreview] = useState(false);
	const [recommendLiveData, setRecommendLiveData] = useState(false);
	const { 
		loading, 
		error, 
		coverageData, 
		intentData, 
		analyzeQuery 
	} = useEnhancedResearch();

	useEffect(() => {
		if (autoAnalyze && query.trim() && searchSpaceId) {
			const timeoutId = setTimeout(() => {
				analyzeQuery(query, searchSpaceId);
				setShowPreview(true);
			}, 1000); // Debounce to avoid too many API calls

			return () => clearTimeout(timeoutId);
		}
	}, [query, searchSpaceId, autoAnalyze, analyzeQuery]);

	useEffect(() => {
		if (coverageData) {
			setRecommendLiveData(coverageData.rag_score < 0.6 || coverageData.live_data_needed);
		}
	}, [coverageData]);

	if (!showPreview || (!loading && !coverageData && !intentData && !error)) {
		return null;
	}

	const handleProceed = (useLiveData: boolean) => {
		setShowPreview(false);
		onProceed?.(useLiveData);
	};

	return (
		<div className="space-y-4 p-4 border rounded-lg bg-background">
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-2">
					<Eye className="h-4 w-4" />
					<h3 className="text-sm font-medium">Research Preview</h3>
				</div>
				<Button
					variant="ghost"
					size="sm"
					onClick={() => setShowPreview(false)}
					className="h-6 px-2 text-xs"
				>
					Hide
				</Button>
			</div>

			{loading && (
				<div className="space-y-2">
					<div className="flex items-center gap-2 text-sm text-muted-foreground">
						<Clock className="h-4 w-4 animate-spin" />
						Analyzing your query...
					</div>
					<Progress value={0} className="h-2" />
				</div>
			)}

			{error && (
				<Alert className="border-red-200 bg-red-50">
					<AlertTriangle className="h-4 w-4 text-red-600" />
					<AlertDescription className="text-red-800">
						{error}
					</AlertDescription>
				</Alert>
			)}

			<div className="grid gap-4 md:grid-cols-2">
				{coverageData && (
					<ToolrowCoverageIndicator 
						coverage={coverageData}
						loading={loading}
						onRequestLiveData={() => handleProceed(true)}
					/>
				)}

				{intentData && (
					<IntentPreviewCard intent={intentData} />
				)}
			</div>

			{(coverageData || intentData) && (
				<div className="space-y-3">
					{recommendLiveData && (
						<Alert className="border-blue-200 bg-blue-50">
							<Zap className="h-4 w-4 text-blue-600" />
							<AlertDescription className="text-blue-800">
								<div className="flex items-center justify-between">
									<span className="text-sm">
										Live data sources could significantly improve this answer
									</span>
									<Badge variant="outline" className="bg-white border-blue-300 text-blue-700 ml-2">
										Recommended
									</Badge>
								</div>
							</AlertDescription>
						</Alert>
					)}

					<div className="flex gap-2 justify-end">
						{onCancel && (
							<Button variant="outline" size="sm" onClick={onCancel}>
								Cancel
							</Button>
						)}
						<Button 
							variant="outline" 
							size="sm" 
							onClick={() => handleProceed(false)}
							className="flex items-center gap-1"
						>
							<Database className="h-3 w-3" />
							Use Documents Only
						</Button>
						<Button 
							size="sm" 
							onClick={() => handleProceed(true)}
							className="flex items-center gap-1"
							disabled={!intentData?.recommended_tools?.length}
						>
							<Zap className="h-3 w-3" />
							Include Live Data
						</Button>
					</div>
				</div>
			)}
		</div>
	);
}
