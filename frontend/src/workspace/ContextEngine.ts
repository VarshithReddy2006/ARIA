import type { ContextState, EngineeringIntent } from './types';

export class ContextEngine {
  public inferContext(selectedFile: string | null): {
    contextState: ContextState;
    suggestedIntent: EngineeringIntent;
    confidencePct: number;
    recommendedAction: string;
  } {
    if (!selectedFile) {
      return {
        contextState: 'API Layer',
        suggestedIntent: 'Understand Repository',
        confidencePct: 92,
        recommendedAction: 'Explore entry point application routing.',
      };
    }

    const path = selectedFile.toLowerCase();

    if (path.includes('auth') || path.includes('jwt') || path.includes('login')) {
      return {
        contextState: 'Authentication',
        suggestedIntent: 'Investigate Security',
        confidencePct: 98,
        recommendedAction: 'Run POST /login authentication lifecycle scenario.',
      };
    }

    if (path.includes('db') || path.includes('repo') || path.includes('postgres') || path.includes('sql')) {
      return {
        contextState: 'Persistence',
        suggestedIntent: 'Understand Feature',
        confidencePct: 95,
        recommendedAction: 'Inspect database repository query handlers.',
      };
    }

    if (path.includes('cache') || path.includes('redis')) {
      return {
        contextState: 'Caching',
        suggestedIntent: 'Investigate Performance',
        confidencePct: 94,
        recommendedAction: 'Check Redis cache hit ratio and key eviction policy.',
      };
    }

    if (path.includes('router') || path.includes('api') || path.includes('endpoint')) {
      return {
        contextState: 'Routing',
        suggestedIntent: 'Learn Architecture',
        confidencePct: 96,
        recommendedAction: 'Inspect HTTP endpoint schema validation and response serialization.',
      };
    }

    return {
        contextState: 'API Layer',
        suggestedIntent: 'Understand Repository',
        confidencePct: 90,
        recommendedAction: 'Explore module dependencies and layer classification.',
    };
  }
}
