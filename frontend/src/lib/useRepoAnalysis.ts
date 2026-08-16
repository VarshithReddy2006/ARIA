import { useEffect, useMemo, useState } from 'react';
import { apiUrl } from './api';
import { parseGitHubUrl, type ParsedRepo, type ValidationState } from './repoUrl';

/**
 * One step of the backend pipeline, as reported by the analyze SSE stream.
 * The ids match the `status` values the stream emits and must not be renamed.
 */
export interface AnalysisStep {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'completed';
}

/** Previous name for {@link AnalysisStep}. */
export type TimelineStep = AnalysisStep;

/**
 * useRepoAnalysis — all client behaviour behind "analyse a repository".
 *
 * Extracted so the landing page can present the analyzer however it likes
 * without re-implementing streaming, validation or navigation. The contract
 * with the backend is unchanged: `POST /api/v1/analyze` streamed over SSE,
 * `GET /api/v1/repos/examples` for the sample list, and a redirect to
 * `/analysis?owner=…&repo=…` once indexing completes.
 */

export interface ExampleRepo {
  name: string;
  url: string;
  tech_stack: string[];
  description: string;
}

const INITIAL_STEPS: AnalysisStep[] = [
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
  analyze: (repoUrl: string) => Promise<void>;
}

export function useRepoAnalysis(): RepoAnalysis {
  const [url, setUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [examples, setExamples] = useState<ExampleRepo[]>([]);
  const [analysisSteps, setAnalysisSteps] = useState<AnalysisStep[]>(INITIAL_STEPS);
  const [validation, setValidation] = useState<ValidationState>('empty');

  const parsed = useMemo(() => parseGitHubUrl(url), [url]);

  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl('/api/v1/repos/examples'))
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled && Array.isArray(data)) setExamples(data);
      })
      .catch((err) => console.error('Could not load example repositories', err));
    return () => {
      cancelled = true;
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

  const analyze = async (repoUrl: string) => {
    if (!repoUrl.trim() || isAnalyzing) return;

    // Normalise to the canonical clone URL so trailing paths such as
    // /tree/main/src never reach the backend.
    const target = parseGitHubUrl(repoUrl);
    const submitUrl = target ? `https://github.com/${target.slug}` : repoUrl;

    setIsAnalyzing(true);
    setErrorMessage(null);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('aria-analysis-started'));
    }
    setAnalysisSteps([{ ...INITIAL_STEPS[0], status: 'active' }, ...INITIAL_STEPS.slice(1)]);

    try {
      const response = await fetch(apiUrl('/api/v1/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: submitUrl, branch: 'main' }),
      });

      if (!response.body) throw new Error('Stream not available');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let finished = false;

      while (!finished) {
        const { value, done } = await reader.read();
        finished = done;
        if (!value) continue;

        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));

            if (data.status === 'error') {
              const cleanMsg = (data.message || 'An error occurred during analysis.')
                .replace(/^[✗×x]\s*/i, '')
                .trim();
              setErrorMessage(cleanMsg);
              setIsAnalyzing(false);
              if (typeof window !== 'undefined') {
                window.dispatchEvent(new CustomEvent('aria-analysis-completed'));
              }
              reader.cancel().catch(() => {});
              return;
            }

            const activeStatus = data.status;

            setAnalysisSteps((prev) => {
              const currentIdx = prev.findIndex((s) => s.id === activeStatus);
              if (currentIdx !== -1) {
                return prev.map((s, idx) => {
                  if (idx < currentIdx) return { ...s, status: 'completed' as const };
                  if (idx === currentIdx) return { ...s, status: 'active' as const };
                  return { ...s, status: 'pending' as const };
                });
              }
              if (activeStatus === 'cloned') {
                return prev.map((s) =>
                  s.id === 'cloning'
                    ? { ...s, status: 'completed' as const }
                    : s.id === 'detecting'
                      ? { ...s, status: 'active' as const }
                      : s
                );
              }
              if (activeStatus === 'detected') {
                return prev.map((s) =>
                  s.id === 'detecting'
                    ? { ...s, status: 'completed' as const }
                    : s.id === 'parsing'
                      ? { ...s, status: 'active' as const }
                      : s
                );
              }
              if (activeStatus === 'complete') {
                return prev.map((s) => ({ ...s, status: 'completed' as const }));
              }
              return prev;
            });

            if (data.status === 'done') {
              const repoPath =
                data.repo ||
                data.repository ||
                (data.owner && data.repo_name ? `${data.owner}/${data.repo_name}` : null);

              if (repoPath) {
                const [owner, repo] = repoPath.split('/');
                if (owner && repo) {
                  if (typeof window !== 'undefined') {
                    localStorage.setItem('activeRepo', repoPath);
                  }
                  window.location.href = `/analysis?owner=${owner}&repo=${repo}`;
                } else {
                  setErrorMessage('Invalid repo format received');
                  setIsAnalyzing(false);
                }
              } else {
                setErrorMessage('Missing repo in analysis result');
                setIsAnalyzing(false);
              }
            }
          } catch {
            /* ignore malformed SSE frames */
          }
        }
      }
    } catch (err) {
      console.error('Analysis stream interrupted', err);
      setErrorMessage('The analysis stream was interrupted. Please try again.');
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
    analyze,
  };
}
