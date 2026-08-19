import { useCallback, useEffect, useState } from 'react';
import { apiUrl, extractErrorMessage } from '../../../lib/api';

export interface HealthStatus {
  github_auth?: boolean;
  rate_limit_remaining?: number;
  analysis_exists?: boolean;
  graph_available?: boolean;
  symbol_index_available?: boolean;
}

export interface UsePrerequisitesResult {
  healthStatus: HealthStatus | null;
  /** True when no health response yet (treat as "allow form to render") */
  hasPrerequisites: boolean;
  isRepairing: boolean;
  repairError: string | null;
  repair: () => Promise<void>;
  refresh: () => Promise<void>;
}

/**
 * Shared prerequisite/diagnostics hook used by PR Intelligence,
 * Architecture Drift, and Dead Code Analyzer.
 */
export function usePrerequisites(activeRepo: string): UsePrerequisitesResult {
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [isRepairing, setIsRepairing] = useState(false);
  const [repairError, setRepairError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!activeRepo) return;
    const [owner, repo] = activeRepo.split('/');
    if (!owner || !repo) return;
    try {
      const res = await fetch(apiUrl(`/api/v1/pr/health?owner=${owner}&repo=${repo}`));
      const data = await res.json();
      setHealthStatus(data);
    } catch (err) {
      console.error('PR Health check failed', err);
    }
  }, [activeRepo]);

  useEffect(() => {
    setHealthStatus(null);
    setRepairError(null);
    refresh();
  }, [activeRepo, refresh]);

  const repair = useCallback(async () => {
    if (!activeRepo) return;
    const [owner, repo] = activeRepo.split('/');
    if (!owner || !repo) return;
    setIsRepairing(true);
    setRepairError(null);
    try {
      const res = await fetch(apiUrl('/api/v1/repos/repair'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner, repo }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData));
      }
      await refresh();
    } catch (err) {
      setRepairError(extractErrorMessage(err));
    } finally {
      setIsRepairing(false);
    }
  }, [activeRepo, refresh]);

  const hasPrerequisites = healthStatus
    ? Boolean(healthStatus.analysis_exists && healthStatus.graph_available && healthStatus.symbol_index_available)
    : true;

  return { healthStatus, hasPrerequisites, isRepairing, repairError, repair, refresh };
}
