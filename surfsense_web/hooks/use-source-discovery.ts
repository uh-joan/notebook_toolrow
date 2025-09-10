"use client";

import { useState, useCallback } from "react";

// Types for the Source Discovery API
export interface DiscoveryRequest {
  query: string;
  focus_areas?: string[];
  filters?: Record<string, any>;
  max_sources?: number;
  export_format?: "excel" | "pdf" | "json";
}

export interface SourceMetadata {
  source_type: string;
  title: string;
  description?: string;
  url?: string;
  publication_date?: string;
  relevance_score: number;
  tags: string[];
  raw_data: Record<string, any>;
}

export interface SourceSuggestion {
  metadata: SourceMetadata;
  content_preview: string;
  import_recommendation: string;
  estimated_value: number;
  processing_notes?: string;
}

export interface DiscoveryResult {
  request: DiscoveryRequest;
  suggestions: SourceSuggestion[];
  total_found: number;
  processing_time_ms: number;
  export_path?: string;
  summary: string;
  next_steps: string[];
}

export interface DiscoveryStatus {
  status: "ready" | "limited" | "error";
  message: string;
  tools_available: number;
}

export interface DiscoveryError {
  message: string;
  code?: string;
}

// Hook for managing source discovery
export function useSourceDiscovery() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<DiscoveryError | null>(null);
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);

  // Get discovery status
  const getStatus = useCallback(async () => {
    try {
      const apiBaseUrl = process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";
      const response = await fetch(`${apiBaseUrl}/api/source-discovery/status`);
      if (!response.ok) {
        throw new Error(`Status check failed: ${response.statusText}`);
      }
      const statusData: DiscoveryStatus = await response.json();
      setStatus(statusData);
      return statusData;
    } catch (err) {
      const error: DiscoveryError = {
        message: err instanceof Error ? err.message : "Failed to get status"
      };
      setError(error);
      throw error;
    }
  }, []);

  // Discover sources
  const discover = useCallback(async (request: DiscoveryRequest) => {
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      // Get auth token from localStorage (same as other hooks)
      const token = localStorage.getItem("surfsense_bearer_token");
      
      const apiBaseUrl = process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";
      const response = await fetch(`${apiBaseUrl}/api/source-discovery/discover`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token && { "Authorization": `Bearer ${token}` })
        },
        body: JSON.stringify(request)
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Authentication required. Please log in.");
        }
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || `Discovery failed: ${response.statusText}`);
      }

      const discoveryResult: DiscoveryResult = await response.json();
      setResult(discoveryResult);
      return discoveryResult;

    } catch (err) {
      const error: DiscoveryError = {
        message: err instanceof Error ? err.message : "Discovery failed"
      };
      setError(error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Quick discovery methods
  const discoverClinicalTrials = useCallback(async (condition: string, status: string = "recruiting") => {
    return discover({
      query: `clinical trials for ${condition}${status !== "all" ? ` that are ${status}` : ""}`,
      focus_areas: ["clinical_trials"],
      filters: { status },
      max_sources: 20
    });
  }, [discover]);

  const discoverFDADrugs = useCallback(async (condition: string) => {
    return discover({
      query: `FDA approved drugs for ${condition}`,
      focus_areas: ["regulatory"],
      max_sources: 15
    });
  }, [discover]);

  const discoverResearchPapers = useCallback(async (topic: string) => {
    return discover({
      query: `recent research papers on ${topic}`,
      focus_areas: ["research"],
      max_sources: 25
    });
  }, [discover]);

  // List available tools
  const getAvailableTools = useCallback(async () => {
    try {
      const apiBaseUrl = process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "http://localhost:8000";
      const response = await fetch(`${apiBaseUrl}/api/source-discovery/tools`);
      if (!response.ok) {
        throw new Error(`Failed to get tools: ${response.statusText}`);
      }
      return await response.json();
    } catch (err) {
      const error: DiscoveryError = {
        message: err instanceof Error ? err.message : "Failed to get available tools"
      };
      setError(error);
      throw error;
    }
  }, []);

  // Clear results
  const clearResults = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  // Reset all state
  const reset = useCallback(() => {
    setIsLoading(false);
    setError(null);
    setResult(null);
    setStatus(null);
  }, []);

  return {
    // State
    isLoading,
    error,
    result,
    status,
    
    // Methods
    getStatus,
    discover,
    discoverClinicalTrials,
    discoverFDADrugs,
    discoverResearchPapers,
    getAvailableTools,
    clearResults,
    reset,
    
    // Computed values
    hasResults: !!result,
    isReady: status?.status === "ready",
    toolsAvailable: status?.tools_available || 0
  };
}
