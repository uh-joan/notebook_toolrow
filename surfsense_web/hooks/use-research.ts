import { useState } from 'react';
import { apiClient as api } from '@/lib/api';
import type { ToolrowCoverage, ToolrowSource, ToolrowInvocation } from '@/components/chat/types';

interface ResearchRequest {
  question: string;
  search_space_id: string;
  document_ids?: string[];
  connector_types?: string[];
  use_live_data?: boolean;
}

interface ResearchResponse {
  answer: string;
  sources: Array<{
    id: string;
    title: string;
    description: string;
    url: string;
    type: string;
  }>;
  toolrow_sources?: ToolrowSource[];
  toolrow_invocations?: ToolrowInvocation[];
  coverage?: ToolrowCoverage;
  citations?: Array<{
    text: string;
    source_id: string;
    page?: number;
  }>;
}

interface IntentPreview {
  category: string;
  entities: string[];
  confidence: number;
  recommended_tools: string[];
}

export function useResearch() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const askQuestion = async (request: ResearchRequest): Promise<ResearchResponse> => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await api.post<ResearchResponse>('/api/v1/research/ask', request);
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Research request failed';
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const getCoverage = async (searchSpaceId: string, query: string): Promise<ToolrowCoverage> => {
    try {
      const response = await api.get<ToolrowCoverage>(`/api/v1/research/coverage/${searchSpaceId}?query=${encodeURIComponent(query)}`);
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Coverage check failed';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  const previewIntent = async (query: string): Promise<IntentPreview> => {
    try {
      const response = await api.post<IntentPreview>('/api/v1/research/intent-preview', { query });
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Intent preview failed';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  return {
    loading,
    error,
    askQuestion,
    getCoverage,
    previewIntent,
  };
}

// Hook specifically for the enhanced research workflow
export function useEnhancedResearch() {
  const { askQuestion, getCoverage, previewIntent, loading, error } = useResearch();
  const [coverageData, setCoverageData] = useState<ToolrowCoverage | null>(null);
  const [intentData, setIntentData] = useState<IntentPreview | null>(null);

  const analyzeQuery = async (query: string, searchSpaceId: string) => {
    try {
      // Run coverage check and intent preview in parallel
      const [coverage, intent] = await Promise.all([
        getCoverage(searchSpaceId, query),
        previewIntent(query)
      ]);

      setCoverageData(coverage);
      setIntentData(intent);

      return { coverage, intent };
    } catch (err) {
      console.error('Query analysis failed:', err);
      return { coverage: null, intent: null };
    }
  };

  const executeResearch = async (request: ResearchRequest) => {
    // Automatically enable live data if coverage is low
    const enhancedRequest = {
      ...request,
      use_live_data: request.use_live_data || (coverageData?.rag_score !== undefined && coverageData.rag_score < 0.6),
    };

    return askQuestion(enhancedRequest);
  };

  const clearAnalysis = () => {
    setCoverageData(null);
    setIntentData(null);
  };

  return {
    loading,
    error,
    coverageData,
    intentData,
    analyzeQuery,
    executeResearch,
    clearAnalysis,
    askQuestion,
    getCoverage,
    previewIntent,
  };
}
