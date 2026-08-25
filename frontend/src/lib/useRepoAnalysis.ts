import { useEffect, useMemo, useRef, useState } from 'react';
import { apiUrl, extractErrorMessage, getApiHeaders } from './api.ts';
import { parseGitHubUrl, type ParsedRepo, type ValidationState } from './repoUrl.ts';

/**
 * One step of the backend pipeline, as reported by the analyze status endpoint.
 * The ids match the `status` values the pipeline stages emit and must not be renamed.
 */
export interface AnalysisStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'completed';
}

/** Previous name for {@link AnalysisStep}. */
export type TimelineStep = AnalysisStep;

/**
 * Maps a backend step_id / status name to the corresponding frontend UI AnalysisStep ID.
 */
export function mapBackendStepToUiStep(activeStatus: string, message?: string): string {
  let targetId = activeStatus;
  const lowerStatus = (activeStatus || '').toLowerCase();
  const lowerMsg = (message || '').toLowerCase();

  if (lowerStatus === 'clone' || lowerStatus === 'cloned' || lowerStatus === 'cloning') {
    targetId = 'cloning';
  } else if (lowerStatus === 'detect' || lowerStatus === 'detected' || lowerStatus === 'detecting') {
    targetId = 'detecting';
  } else if (lowerStatus === 'parse' || lowerStatus === 'parsed' || lowerStatus === 'parsing') {
    targetId = 'parsing';
  } else if (lowerStatus === 'embed' || lowerStatus === 'generating_embeddings') {
    targetId = 'generating_embeddings';
  } else if (lowerStatus === 'index') {
    if (lowerMsg.includes('dependency') || lowerMsg.includes('dependencies')) {
      targetId = 'building_dependency';
    } else if (lowerMsg.includes('call')) {
      targetId = 'building_call';
    } else if (lowerMsg.includes('api')) {
      targetId = 'building_api';
    } else {
      targetId = 'building_symbols';
    }
  } else if (lowerStatus === 'building_symbols') {
    targetId = 'building_symbols';
  } else if (lowerStatus === 'building_dependency') {
    targetId = 'building_dependency';
  } else if (lowerStatus === 'building_call') {
    targetId = 'building_call';
  } else if (lowerStatus === 'building_api') {
    targetId = 'building_api';
  } else if (lowerStatus === 'analyze' || lowerStatus === 'computing_intel') {
    targetId = 'computing_intel';
  } else if (lowerStatus === 'answer' || lowerStatus === 'report' || lowerStatus === 'generating_report') {
    targetId = 'generating_report';
  }
  return targetId;
}

/**
 * useRepoAnalysis — all client behaviour behind "analyse a repository".
 *
 * Extracted so the landing page can present the analyzer however it likes
 * without re-implementing polling, validation or navigation. The contract
 * with the backend is:
 *   1. `POST /api/v1/analyze` -> receives { job_id, status, repo } with HTTP 202
 *   2. Poll `GET /api/v1/analyze/${job_id}` every ~1 second
 *   3. `GET /api/v1/repos/examples` for the sample list
 *   4. Redirect to `/analysis?owner=…&repo=…` once indexing completes.
 */

export interface ExampleRepo {
  name: string;
  url: string;
  tech_stack: string[];
  description: string;
}

export const INITIAL_STEPS: AnalysisStep[] = [
  { id: 'cloning', label: 'Cloning Repository', status: 'pending' },
  { id: 'detecting', label: 'Detecting Languages', status: 'pending' },
  { id: 'parsing', label: 'Parsing Source Files', status: 'pending' },
  { id: 'generating_embeddings', label: 'Generating Embeddings', status: 'pending' },
  { id: 'building_symbols', label: 'Building Symbol Index', status: 'pending' },
  { id: 'building_dependency', label: 'Building Dependency Graph', status: 'pending' },
  { id: 'building_call', label: 'Building Call Graph', status: 'pending' },
  { id: 'building_api', label: 'Computing API Surface', status: 'pending' },
  { id: 'computing_intel', label: 'Computing Repository Intelligence', status: 'pending' },
  { id: 'generating_report', label: 'Generating Report', status: 'pending' },
];

/** Debounce before an in-progress keystroke is judged invalid. */
const VALIDATION_DELAY_MS = 400;
/** Polling interval in ms for background job status. */
export const POLLING_INTERVAL_MS = 1000;
/** Polling timeout in ms (10 minutes). */
export const POLLING_TIMEOUT_MS = 10 * 60 * 1000;

export interface RepoAnalysis {
  url: string;
  setUrl: (value: string) => void;
  parsed: ParsedRepo | null;
  validation: ValidationState;
  isAnalyzing: boolean;
  errorMessage: string | null;
  analysisSteps: AnalysisStep[];
  examples: ExampleRepo[];
  canSubmit: boolean;
  jobProgress?: number;
  jobStats?: Record<string, any>;
  jobStartedAt?: number;
  jobElapsedSeconds?: number;
  analyze: (repoUrl: string, forceRebuild?: boolean) => Promise<void>;
}

export function useRepoAnalysis(): RepoAnalysis {
  const [url, setUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [examples, setExamples] = useState<ExampleRepo[]>([]);
  const [analysisSteps, setAnalysisSteps] = useState<AnalysisStep[]>(INITIAL_STEPS);
  const [validation, setValidation] = useState<ValidationState>('empty');
  const [jobProgress, setJobProgress] = useState<number>(0);
  const [jobStats, setJobStats] = useState<Record<string, any>>({});
  const [jobStartedAt, setJobStartedAt] = useState<number | undefined>(undefined);
  const [jobElapsedSeconds, setJobElapsedSeconds] = useState<number | undefined>(undefined);

  const pollTimerRef = useRef<number | null>(null);
  const isMountedRef = useRef(true);
  const highestStepIdxRef = useRef<number>(0);
  const lastUpdatedAtRef = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const parsed = useMemo(() => parseGitHubUrl(url), [url]);

  useEffect(() => {
    isMountedRef.current = true;
    let cancelled = false;
    fetch(apiUrl('/api/v1/repos/examples'), { headers: getApiHeaders() })
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled && Array.isArray(data)) setExamples(data);
      })
      .catch((err) => console.error('Could not load example repositories', err));

    return () => {
      cancelled = true;
      isMountedRef.current = false;
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, []);

  /**
   * Validation is optimistic: a recognised repository resolves instantly so
   * pasting feels immediate, while an unrecognised value waits out the debounce
   * so it isn't flagged mid-typing.
   */
  useEffect(() => {
    if (!url.trim()) {
      setValidation('empty');
      return;
    }
    if (parsed) {
      setValidation('valid');
      return;
    }
    setValidation('checking');
    const timer = window.setTimeout(() => setValidation('invalid'), VALIDATION_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [url, parsed]);

  const mapStepProgress = (activeStatus: string, message?: string) => {
    setAnalysisSteps((prev) => {
      const targetId = mapBackendStepToUiStep(activeStatus, message);
      let currentIdx = prev.findIndex((s) => s.id === targetId);
      if (currentIdx !== -1) {
        // Enforce monotonic stage progression: never regress backwards
        if (currentIdx < highestStepIdxRef.current) {
          currentIdx = highestStepIdxRef.current;
        } else {
          highestStepIdxRef.current = currentIdx;
        }

        return prev.map((s, idx) => {
          if (idx < currentIdx) return { ...s, status: 'completed' as const };
          if (idx === currentIdx) return { ...s, status: 'active' as const };
          return { ...s, status: 'pending' as const };
        });
      }
      return prev;
    });
  };

  const analyze = async (repoUrl: string, forceRebuild = false) => {
    if (!repoUrl.trim() || isAnalyzing) return;

    // Normalise to canonical clone URL and resolve branch if embedded in URL
    const target = parseGitHubUrl(repoUrl);
    const submitUrl = target ? `https://github.com/${target.slug}` : repoUrl.trim();
    const branch = target?.branch;

    // Abort previous in-flight requests if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    setIsAnalyzing(true);
    setErrorMessage(null);
    setJobProgress(0);
    setJobStats({});
    setJobStartedAt(Date.now() / 1000);
    setJobElapsedSeconds(0);
    highestStepIdxRef.current = 0;
    lastUpdatedAtRef.current = 0;

    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('aria-analysis-started'));
    }
    setAnalysisSteps([{ ...INITIAL_STEPS[0], status: 'active' }, ...INITIAL_STEPS.slice(1)]);

    try {
      // 1. Submit asynchronous analysis request
      const payload: Record<string, any> = {
        url: submitUrl,
      };
      if (forceRebuild) {
        payload.force_rebuild = true;
      }
      if (branch) {
        payload.branch = branch;
      }

      const response = await fetch(apiUrl('/api/v1/analyze'), {
        method: 'POST',
        headers: getApiHeaders(),
        body: JSON.stringify(payload),
        signal: abortController.signal,
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        const rawMsg = errJson.detail || errJson.error || errJson.message || `Server responded with ${response.status}`;
        throw new Error(extractErrorMessage(rawMsg));
      }

      const initData = await response.json();
      const jobId = initData.job_id;

      if (!jobId) {
        throw new Error('No job identifier returned by the server.');
      }

      const pollStartTime = Date.now();

      // 2. Start asynchronous polling of the status endpoint
      const pollStatus = async () => {
        if (!isMountedRef.current || abortController.signal.aborted) return;

        // Check timeout
        if (Date.now() - pollStartTime > POLLING_TIMEOUT_MS) {
          setErrorMessage('Analysis timed out after 10 minutes. Please try again.');
          setIsAnalyzing(false);
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('aria-analysis-completed'));
          }
          return;
        }

        try {
          const pollRes = await fetch(apiUrl(`/api/v1/analyze/${jobId}`), {
            headers: getApiHeaders(),
            signal: abortController.signal,
          });

          if (pollRes.status === 404) {
            throw new Error('Analysis job not found on server.');
          }

          if (!pollRes.ok && pollRes.status !== 202) {
            const errJson = await pollRes.json().catch(() => ({}));
            if (errJson.status === 'failed' || errJson.error) {
              const cleanMsg = (errJson.error || errJson.detail || 'Analysis job failed on server.')
                .replace(/^[✗×x]\s*/i, '')
                .trim();
              setErrorMessage(cleanMsg);
              setIsAnalyzing(false);
              if (typeof window !== 'undefined') {
                window.dispatchEvent(new CustomEvent('aria-analysis-completed'));
              }
              return;
            }
          }

          const data = await pollRes.json();

          // Reject stale / out-of-order responses based on updated_at timestamp
          const responseUpdatedAt = typeof data.updated_at === 'number' ? data.updated_at : 0;
          if (responseUpdatedAt && lastUpdatedAtRef.current && responseUpdatedAt < lastUpdatedAtRef.current) {
            if (isMountedRef.current && !abortController.signal.aborted) {
              pollTimerRef.current = window.setTimeout(pollStatus, POLLING_INTERVAL_MS);
            }
            return;
          }
          if (responseUpdatedAt) {
            lastUpdatedAtRef.current = responseUpdatedAt;
          }

          // Authoritative progress percentage from backend
          if (typeof data.progress === 'number') {
            setJobProgress((prev) => Math.max(prev, Math.min(100, data.progress)));
          }
          if (data.stats && typeof data.stats === 'object') {
            setJobStats(data.stats);
          }
          if (typeof data.started_at === 'number') {
            setJobStartedAt(data.started_at);
          }
          if (typeof data.elapsed_seconds === 'number') {
            setJobElapsedSeconds(data.elapsed_seconds);
          }

          if (data.status === 'failed') {
            const cleanMsg = (data.error || data.message || 'An error occurred during analysis.')
              .replace(/^[✗×x]\s*/i, '')
              .trim();
            setErrorMessage(cleanMsg);
            setIsAnalyzing(false);
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('aria-analysis-completed'));
            }
            return;
          }

          if (data.status === 'completed') {
            setAnalysisSteps((prev) => prev.map((s) => ({ ...s, status: 'completed' as const })));
            setJobProgress(100);

            const repoPath =
              data.repo?.full_name ||
              (data.repo?.owner && data.repo?.name ? `${data.repo.owner}/${data.repo.name}` : null) ||
              data.result?.repo ||
              (data.result?.owner && data.result?.name ? `${data.result.owner}/${data.result.name}` : null);

            if (repoPath) {
              const [owner, repo] = repoPath.split('/');
              if (owner && repo) {
                if (typeof window !== 'undefined') {
                  localStorage.setItem('activeRepo', repoPath);
                }
                window.location.href = `/analysis?owner=${owner}&repo=${repo}`;
                return;
              }
            }

            // Fallback navigation from target if known
            if (target) {
              if (typeof window !== 'undefined') {
                localStorage.setItem('activeRepo', target.slug);
              }
              window.location.href = `/analysis?owner=${target.owner}&repo=${target.repo}`;
              return;
            }

            setErrorMessage('Analysis completed but repository identifier was missing.');
            setIsAnalyzing(false);
            return;
          }

          // In progress (queued / running)
          const currentStage = data.step_id || data.status;
          if (currentStage) {
            mapStepProgress(currentStage, data.message);
          }

          // Schedule next poll
          if (isMountedRef.current && !abortController.signal.aborted) {
            pollTimerRef.current = window.setTimeout(pollStatus, POLLING_INTERVAL_MS);
          }
        } catch (pollErr: any) {
          if (abortController.signal.aborted) return;
          console.warn('Analysis polling warning:', pollErr);

          if (pollErr.message === 'Analysis job not found on server.') {
            setErrorMessage('Analysis job not found on server.');
            setIsAnalyzing(false);
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('aria-analysis-completed'));
            }
            return;
          }

          // Retry polling on transient network failure unless unmounted or timed out
          if (isMountedRef.current && !abortController.signal.aborted) {
            pollTimerRef.current = window.setTimeout(pollStatus, POLLING_INTERVAL_MS);
          }
        }
      };

      // Kick off first poll after POLLING_INTERVAL_MS
      pollTimerRef.current = window.setTimeout(pollStatus, POLLING_INTERVAL_MS);

    } catch (err: any) {
      if (abortController.signal.aborted) return;
      console.error('Failed to start repository analysis', err);
      setErrorMessage(err.message || 'The analysis request failed. Please try again.');
      setIsAnalyzing(false);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('aria-analysis-completed'));
      }
    }
  };

  return {
    url,
    setUrl,
    parsed,
    validation,
    isAnalyzing,
    errorMessage,
    analysisSteps,
    examples,
    canSubmit: validation === 'valid' && !isAnalyzing,
    jobProgress,
    jobStats,
    jobStartedAt,
    jobElapsedSeconds,
    analyze,
  };
}
