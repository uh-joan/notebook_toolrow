"use client";

import { ChatInput } from "@llamaindex/chat-ui";
import { Brain, Database, Zap } from "lucide-react";
import React, { Suspense, useCallback, useState } from "react";
import type { DiscoveryMode } from "@/components/chat";
import {
	ConnectorButton as ConnectorButtonComponent,
	getConnectorIcon,
} from "@/components/chat/ConnectorComponents";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { useLLMConfigs, useLLMPreferences } from "@/hooks/use-llm-configs";

// Tool definitions based on our backend tools
const AVAILABLE_TOOLS = [
	{
		name: "ct_gov_studies",
		label: "Clinical Trials",
		description: "Search clinical trials from ClinicalTrials.gov",
		category: "clinical_trials",
		icon: "🔬",
	},
	{
		name: "nlm_ct_codes",
		label: "Medical Codes",
		description: "ICD-10, ICD-11, HCPCS codes from NLM Clinical Tables",
		category: "medical_codes",
		icon: "📋",
	},
	{
		name: "pubmed_articles",
		label: "Research Papers",
		description: "Biomedical literature from PubMed",
		category: "research",
		icon: "📄",
	},
	{
		name: "fda_info",
		label: "FDA Information",
		description: "Drug labels, approvals, and regulatory data",
		category: "regulatory",
		icon: "💊",
	},
	{
		name: "who-health",
		label: "WHO Health Data",
		description: "Global health statistics and indicators",
		category: "health_organization",
		icon: "🌍",
	},
	{
		name: "sec-edgar",
		label: "SEC Filings",
		description: "Company financial data and SEC documents",
		category: "financial",
		icon: "💼",
	},
];

const ToolSelector = React.memo(
	({
		onSelectionChange,
		selectedTools = [],
	}: {
		onSelectionChange?: (tools: string[]) => void;
		selectedTools?: string[];
	}) => {
		const [isOpen, setIsOpen] = useState(false);

		const handleToolToggle = useCallback(
			(toolName: string, checked: boolean) => {
				const newSelection = checked
					? [...selectedTools, toolName]
					: selectedTools.filter((t) => t !== toolName);
				onSelectionChange?.(newSelection);
			},
			[selectedTools, onSelectionChange]
		);

		const selectedCount = selectedTools.length;

		return (
			<Dialog open={isOpen} onOpenChange={setIsOpen}>
				<DialogTrigger asChild>
					<Button
						variant="outline"
						size="sm"
						className="h-8 px-3 text-xs border-border bg-background hover:bg-muted/50 transition-colors duration-200 focus:ring-2 focus:ring-primary/20"
					>
						<Database className="h-3 w-3 mr-2" />
						<span className="hidden sm:inline">
							{selectedCount === 0 ? "Select Tools" : `Tools (${selectedCount})`}
						</span>
						<span className="sm:hidden">
							{selectedCount === 0 ? "Tools" : selectedCount}
						</span>
					</Button>
				</DialogTrigger>
				<DialogContent className="max-w-2xl">
					<DialogTitle>Select Discovery Tools</DialogTitle>
					<DialogDescription>
						Choose which data sources to search. Leave empty for AI auto-selection.
					</DialogDescription>
					<div className="grid gap-4 py-4">
						{AVAILABLE_TOOLS.map((tool) => (
							<div key={tool.name} className="flex items-start space-x-3">
								<Checkbox
									id={tool.name}
									checked={selectedTools.includes(tool.name)}
									onCheckedChange={(checked) =>
										handleToolToggle(tool.name, checked as boolean)
									}
								/>
								<div className="grid gap-1.5 leading-none">
									<label
										htmlFor={tool.name}
										className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
									>
										{tool.icon} {tool.label}
									</label>
									<p className="text-xs text-muted-foreground">
										{tool.description}
									</p>
								</div>
							</div>
						))}
					</div>
					<DialogFooter>
						<Button onClick={() => setIsOpen(false)}>Done</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		);
	}
);

ToolSelector.displayName = "ToolSelector";

const DiscoveryModeSelector = React.memo(
	({
		discoveryMode,
		onDiscoveryModeChange,
	}: {
		discoveryMode?: DiscoveryMode;
		onDiscoveryModeChange?: (mode: DiscoveryMode) => void;
	}) => {
		const handleValueChange = useCallback(
			(value: string) => {
				onDiscoveryModeChange?.(value as DiscoveryMode);
			},
			[onDiscoveryModeChange]
		);

		const modeOptions = [
			{ value: "BASIC", label: "Basic Discovery", shortLabel: "Basic" },
			{ value: "DEEP", label: "Deep Discovery", shortLabel: "Deep" },
			{ value: "COMPREHENSIVE", label: "Comprehensive Discovery", shortLabel: "Comprehensive" },
		];

		return (
			<div className="flex items-center gap-1 sm:gap-2">
				<span className="text-xs text-muted-foreground hidden sm:block">Mode:</span>
				<Select value={discoveryMode} onValueChange={handleValueChange}>
					<SelectTrigger className="w-auto min-w-[80px] sm:min-w-[120px] h-8 text-xs border-border bg-background hover:bg-muted/50 transition-colors duration-200 focus:ring-2 focus:ring-primary/20">
						<SelectValue placeholder="Mode" className="text-xs" />
					</SelectTrigger>
					<SelectContent align="end" className="min-w-[140px]">
						<div className="px-2 py-1.5 text-xs font-medium text-muted-foreground border-b bg-muted/30">
							Discovery Mode
						</div>
						{modeOptions.map((option) => (
							<SelectItem
								key={option.value}
								value={option.value}
								className="px-3 py-2 cursor-pointer hover:bg-accent/50 focus:bg-accent"
							>
								<span className="hidden sm:inline">{option.label}</span>
								<span className="sm:hidden">{option.shortLabel}</span>
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</div>
		);
	}
);

DiscoveryModeSelector.displayName = "DiscoveryModeSelector";

const LLMSelector = React.memo(() => {
	const { llmConfigs, loading: isLoading, error } = useLLMConfigs();
	const { preferences, updatePreferences } = useLLMPreferences();

	const selectedConfig = React.useMemo(() => {
		return llmConfigs.find((config) => config.id === preferences.fast_llm_id);
	}, [preferences.fast_llm_id, llmConfigs]);

	const displayValue = React.useMemo(() => {
		if (!selectedConfig) return null;
		return (
			<div className="flex items-center gap-1">
				<span className="font-medium text-xs">{selectedConfig.provider}</span>
				<span className="text-muted-foreground">•</span>
				<span className="hidden sm:inline text-muted-foreground text-xs truncate max-w-[60px]">
					{selectedConfig.name}
				</span>
			</div>
		);
	}, [selectedConfig]);

	const handleValueChange = useCallback(
		(value: string) => {
			const llmId = value ? parseInt(value, 10) : undefined;
			updatePreferences({ fast_llm_id: llmId });
		},
		[updatePreferences]
	);

	if (isLoading) {
		return (
			<div className="h-8 min-w-[100px] sm:min-w-[120px]">
				<div className="h-8 rounded-md bg-muted animate-pulse flex items-center px-3">
					<div className="w-3 h-3 rounded bg-muted-foreground/20 mr-2" />
					<div className="h-3 w-16 rounded bg-muted-foreground/20" />
				</div>
			</div>
		);
	}

	return (
		<div className="h-8 min-w-0">
			<Select
				value={preferences.fast_llm_id?.toString() || ""}
				onValueChange={handleValueChange}
				disabled={isLoading}
			>
				<SelectTrigger className="h-8 w-auto min-w-[100px] sm:min-w-[120px] px-3 text-xs border-border bg-background hover:bg-muted/50 transition-colors duration-200 focus:ring-2 focus:ring-primary/20">
					<div className="flex items-center gap-2 min-w-0">
						<Zap className="h-3 w-3 text-primary flex-shrink-0" />
						<SelectValue placeholder="Fast LLM" className="text-xs">
							{displayValue || <span className="text-muted-foreground">Select LLM</span>}
						</SelectValue>
					</div>
				</SelectTrigger>
				<SelectContent align="end" className="w-[300px] max-h-[400px]">
					<div className="px-3 py-2 text-xs font-medium text-muted-foreground border-b bg-muted/30">
						<div className="flex items-center gap-2">
							<Zap className="h-3 w-3" />
							Fast LLM Selection
						</div>
					</div>
					{llmConfigs.length === 0 ? (
						<div className="px-4 py-6 text-center">
							<div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
								<Brain className="h-5 w-5 text-muted-foreground" />
							</div>
							<h4 className="text-sm font-medium mb-1">No LLM configurations</h4>
							<p className="text-xs text-muted-foreground mb-3">
								Configure AI models to get started
							</p>
							<Button
								variant="outline"
								size="sm"
								className="text-xs"
								onClick={() => window.open("/settings", "_blank")}
							>
								Open Settings
							</Button>
						</div>
					) : (
						<div className="py-1">
							{llmConfigs.map((config) => (
								<SelectItem
									key={config.id}
									value={config.id.toString()}
									className="px-3 py-2 cursor-pointer hover:bg-accent/50 focus:bg-accent"
								>
									<div className="flex items-center justify-between w-full">
										<div className="flex items-center gap-3">
											<div className="flex items-center gap-2 min-w-0">
												<span className="font-medium text-xs">
													{config.provider}
												</span>
												<span className="text-muted-foreground text-xs">•</span>
												<span className="text-muted-foreground text-xs truncate">
													{config.name}
												</span>
											</div>
										</div>
										{config.id === preferences.fast_llm_id && (
											<div className="flex items-center gap-1 text-primary">
												<span className="text-xs">Selected</span>
											</div>
										)}
									</div>
								</SelectItem>
							))}
						</div>
					)}
				</SelectContent>
			</Select>
		</div>
	);
});

LLMSelector.displayName = "LLMSelector";

const CustomDiscoverInputOptions = React.memo(
	({
		onToolSelectionChange,
		selectedTools,
		discoveryMode,
		onDiscoveryModeChange,
	}: {
		onToolSelectionChange?: (tools: string[]) => void;
		selectedTools?: string[];
		discoveryMode?: DiscoveryMode;
		onDiscoveryModeChange?: (mode: DiscoveryMode) => void;
	}) => {
		const loadingFallback = React.useMemo(
			() => <div className="h-8 min-w-[100px] animate-pulse bg-muted rounded-md" />,
			[]
		);

		return (
			<div className="flex flex-wrap gap-2 sm:gap-3 items-center justify-start">
				<Suspense fallback={loadingFallback}>
					<ToolSelector
						onSelectionChange={onToolSelectionChange}
						selectedTools={selectedTools}
					/>
				</Suspense>
				<DiscoveryModeSelector
					discoveryMode={discoveryMode}
					onDiscoveryModeChange={onDiscoveryModeChange}
				/>
				<LLMSelector />
			</div>
		);
	}
);

CustomDiscoverInputOptions.displayName = "CustomDiscoverInputOptions";

export const DiscoverChatInputUI = React.memo(
	({
		onToolSelectionChange,
		selectedTools,
		discoveryMode,
		onDiscoveryModeChange,
	}: {
		onToolSelectionChange?: (tools: string[]) => void;
		selectedTools?: string[];
		discoveryMode?: DiscoveryMode;
		onDiscoveryModeChange?: (mode: DiscoveryMode) => void;
	}) => {
		return (
			<ChatInput>
				<ChatInput.Form className="flex gap-2">
					<ChatInput.Field className="flex-1" />
					<ChatInput.Submit />
				</ChatInput.Form>
				<CustomDiscoverInputOptions
					onToolSelectionChange={onToolSelectionChange}
					selectedTools={selectedTools}
					discoveryMode={discoveryMode}
					onDiscoveryModeChange={onDiscoveryModeChange}
				/>
			</ChatInput>
		);
	}
);

DiscoverChatInputUI.displayName = "DiscoverChatInputUI";