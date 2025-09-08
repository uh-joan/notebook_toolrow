"use client";

import { getAnnotationData, type Message } from "@llamaindex/chat-ui";
import {
	Activity,
	Database,
	ExternalLink,
	Microscope,
	FileText,
	Zap,
	Clock,
	CheckCircle,
	XCircle,
	AlertCircle,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ToolrowSource, ToolrowInvocation } from "@/components/chat/types";

function getProviderIcon(provider: string) {
	switch (provider.toLowerCase()) {
		case "fda":
			return <Microscope className="h-4 w-4" />;
		case "clinicaltrials.gov":
		case "ct_gov":
			return <Activity className="h-4 w-4" />;
		case "pubmed":
			return <FileText className="h-4 w-4" />;
		case "sec":
			return <Database className="h-4 w-4" />;
		case "who":
			return <Activity className="h-4 w-4" />;
		default:
			return <Zap className="h-4 w-4" />;
	}
}

function getStatusIcon(status: ToolrowInvocation["status"]) {
	switch (status) {
		case "completed":
			return <CheckCircle className="h-4 w-4 text-green-500" />;
		case "failed":
			return <XCircle className="h-4 w-4 text-red-500" />;
		case "running":
			return <Clock className="h-4 w-4 text-blue-500 animate-spin" />;
		case "pending":
			return <AlertCircle className="h-4 w-4 text-yellow-500" />;
		default:
			return <Clock className="h-4 w-4 text-gray-500" />;
	}
}

function ToolrowSourceCard({ source }: { source: ToolrowSource }) {
	const hasUri = source.uri && source.uri.trim() !== "";
	
	// Format metadata for display
	const formatMetadata = (metadata: Record<string, any>) => {
		const important = ['manufacturer', 'approval_date', 'dosage_form', 'strength', 'status', 'phase'];
		const display = important
			.filter(key => metadata[key])
			.map(key => `${key}: ${metadata[key]}`)
			.join(', ');
		return display || 'Live data from Toolrow';
	};

	return (
		<Card className="border-muted hover:border-muted-foreground/20 transition-colors">
			<CardHeader className="pb-3 pt-3">
				<div className="flex items-start justify-between gap-2">
					<div className="flex items-start gap-2 flex-1 min-w-0">
						{getProviderIcon(source.provider)}
						<div className="flex-1 min-w-0">
							<CardTitle className="text-sm font-medium leading-tight line-clamp-2">
								{source.title}
							</CardTitle>
							<div className="flex items-center gap-2 mt-1">
								<Badge variant="outline" className="text-xs">
									{source.provider}
								</Badge>
								<Badge variant="secondary" className="text-xs">
									{source.kind}
								</Badge>
							</div>
						</div>
					</div>
					{hasUri && (
						<Button
							variant="ghost"
							size="sm"
							className="h-7 w-7 p-0 flex-shrink-0 hover:bg-muted"
							onClick={() => window.open(source.uri, "_blank")}
						>
							<ExternalLink className="h-3.5 w-3.5" />
						</Button>
					)}
				</div>
			</CardHeader>
			<CardContent className="pt-0 pb-3">
				<CardDescription className="text-xs line-clamp-2 leading-relaxed text-muted-foreground">
					{formatMetadata(source.metadata)}
				</CardDescription>
				{source.last_updated && (
					<div className="flex items-center gap-1 mt-2">
						<Clock className="h-3 w-3 text-muted-foreground" />
						<span className="text-xs text-muted-foreground">
							Updated: {new Date(source.last_updated).toLocaleDateString()}
						</span>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

function ToolrowInvocationCard({ invocation }: { invocation: ToolrowInvocation }) {
	const [expanded, setExpanded] = useState(false);

	return (
		<Card className="border-muted">
			<CardHeader className="pb-3 pt-3">
				<div className="flex items-center justify-between gap-2">
					<div className="flex items-center gap-2">
						{getStatusIcon(invocation.status)}
						<CardTitle className="text-sm font-medium">
							{invocation.tool}
						</CardTitle>
					</div>
					<div className="flex items-center gap-2">
						{invocation.execution_time_ms && (
							<Badge variant="outline" className="text-xs">
								{invocation.execution_time_ms}ms
							</Badge>
						)}
						<Button
							variant="ghost"
							size="sm"
							className="h-6 px-2 text-xs"
							onClick={() => setExpanded(!expanded)}
						>
							{expanded ? "Less" : "More"}
						</Button>
					</div>
				</div>
			</CardHeader>
			{expanded && (
				<CardContent className="pt-0 pb-3">
					<div className="space-y-2">
						<div>
							<h5 className="text-xs font-medium text-muted-foreground mb-1">Parameters:</h5>
							<pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
								{JSON.stringify(invocation.params, null, 2)}
							</pre>
						</div>
						{invocation.result && (
							<div>
								<h5 className="text-xs font-medium text-muted-foreground mb-1">Result:</h5>
								<pre className="text-xs bg-muted p-2 rounded overflow-x-auto max-h-32 overflow-y-auto">
									{JSON.stringify(invocation.result, null, 2)}
								</pre>
							</div>
						)}
						{invocation.error && (
							<div>
								<h5 className="text-xs font-medium text-red-600 mb-1">Error:</h5>
								<p className="text-xs text-red-600 bg-red-50 p-2 rounded">
									{invocation.error}
								</p>
							</div>
						)}
					</div>
				</CardContent>
			)}
		</Card>
	);
}

export default function ToolrowSourcesDisplay({ message }: { message: Message }) {
	const [open, setOpen] = useState(false);
	
	// Get Toolrow sources from message annotations
	const toolrowSources = getAnnotationData(message, "toolrow_sources") as ToolrowSource[] | undefined;
	const toolrowInvocations = getAnnotationData(message, "toolrow_invocations") as ToolrowInvocation[] | undefined;

	// Group sources by provider
	const sourcesByProvider = toolrowSources?.reduce((acc, source) => {
		if (!acc[source.provider]) {
			acc[source.provider] = [];
		}
		acc[source.provider].push(source);
		return acc;
	}, {} as Record<string, ToolrowSource[]>) || {};

	const totalSources = toolrowSources?.length || 0;
	const totalInvocations = toolrowInvocations?.length || 0;

	// Don't show if no Toolrow data
	if (totalSources === 0 && totalInvocations === 0) {
		return null;
	}

	return (
		<Sheet open={open} onOpenChange={setOpen}>
			<SheetTrigger asChild>
				<Button variant="outline" size="sm" className="w-fit">
					<Zap className="h-4 w-4 mr-2" />
					Live Sources ({totalSources})
					{totalInvocations > 0 && (
						<Badge variant="secondary" className="ml-2 h-5">
							{totalInvocations} calls
						</Badge>
					)}
				</Button>
			</SheetTrigger>
			<SheetContent className="w-[400px] sm:w-[540px] md:w-[640px] lg:w-[720px] xl:w-[800px] sm:max-w-[540px] md:max-w-[640px] lg:max-w-[720px] xl:max-w-[800px] flex flex-col p-0 overflow-hidden">
				<SheetHeader className="px-6 py-4 border-b flex-shrink-0">
					<div className="flex items-center justify-between">
						<div className="flex items-center gap-2">
							<Zap className="h-5 w-5" />
							<SheetTitle className="text-lg font-semibold">Live Data Sources</SheetTitle>
						</div>
						<div className="flex items-center gap-2">
							<Badge variant="outline" className="font-normal">
								{totalSources} {totalSources === 1 ? "source" : "sources"}
							</Badge>
							{totalInvocations > 0 && (
								<Badge variant="secondary" className="font-normal">
									{totalInvocations} {totalInvocations === 1 ? "call" : "calls"}
								</Badge>
							)}
						</div>
					</div>
				</SheetHeader>
				
				<Tabs defaultValue="sources" className="flex-1 flex flex-col min-h-0">
					<div className="flex-shrink-0 w-full px-6 pt-4">
						<TabsList className="grid w-full grid-cols-2">
							<TabsTrigger value="sources" className="flex items-center gap-2">
								<Database className="h-4 w-4" />
								Sources ({totalSources})
							</TabsTrigger>
							<TabsTrigger value="invocations" className="flex items-center gap-2">
								<Activity className="h-4 w-4" />
								Tool Calls ({totalInvocations})
							</TabsTrigger>
						</TabsList>
					</div>

					<TabsContent value="sources" className="flex-1 min-h-0 mt-0 px-6 pb-6 data-[state=active]:flex data-[state=active]:flex-col">
						{totalSources > 0 ? (
							<Tabs defaultValue={Object.keys(sourcesByProvider)[0]} className="flex-1 flex flex-col min-h-0">
								<div className="flex-shrink-0 w-full overflow-x-auto pt-4 scrollbar-none">
									<TabsList className="flex w-max min-w-full bg-muted/50">
										{Object.entries(sourcesByProvider).map(([provider, sources]) => (
											<TabsTrigger
												key={provider}
												value={provider}
												className="flex items-center gap-2 whitespace-nowrap px-4"
											>
												{getProviderIcon(provider)}
												<span className="capitalize">{provider}</span>
												<Badge variant="secondary" className="ml-1.5 h-5 text-xs flex-shrink-0">
													{sources.length}
												</Badge>
											</TabsTrigger>
										))}
									</TabsList>
								</div>
								{Object.entries(sourcesByProvider).map(([provider, sources]) => (
									<TabsContent
										key={provider}
										value={provider}
										className="flex-1 min-h-0 mt-0 data-[state=active]:flex data-[state=active]:flex-col"
									>
										<div className="h-full overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent">
											<div className="grid gap-3 pt-4 grid-cols-1 lg:grid-cols-2">
												{sources.map((source) => (
													<ToolrowSourceCard key={source.id} source={source} />
												))}
											</div>
										</div>
									</TabsContent>
								))}
							</Tabs>
						) : (
							<div className="flex-1 flex items-center justify-center text-muted-foreground">
								<p>No live sources available</p>
							</div>
						)}
					</TabsContent>

					<TabsContent value="invocations" className="flex-1 min-h-0 mt-0 px-6 pb-6 data-[state=active]:flex data-[state=active]:flex-col">
						{totalInvocations > 0 ? (
							<div className="h-full overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent">
								<div className="space-y-3 pt-4">
									{toolrowInvocations?.map((invocation, index) => (
										<ToolrowInvocationCard key={index} invocation={invocation} />
									))}
								</div>
							</div>
						) : (
							<div className="flex-1 flex items-center justify-center text-muted-foreground">
								<p>No tool invocations recorded</p>
							</div>
						)}
					</TabsContent>
				</Tabs>
			</SheetContent>
		</Sheet>
	);
}
