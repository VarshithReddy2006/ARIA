import React, { useState, useRef, useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiUrl } from '../../lib/api';
import {
  Send,
  MessageSquareCode,
  Sparkles,
  Bot,
  User,
  RefreshCw,
  FileCode,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Copy,
  CheckCircle2,
  StopCircle,
  ArrowRight,
  Workflow,
  FileText,
  Trash2,
  Shield,
  Layers,
  Code2,
  ExternalLink,
  Info,
  Check,
} from 'lucide-react';

import { tokenizeCode, type Token } from '../../lib/tokenizer';
import { sanitizeMarkdown } from '../../lib/sanitizer';
import {
  detectChatIntent,
  generateSuggestedPrompts,
  generateFollowUpPrompts,
  redactSecrets,
  resolvePronouns,
  parseAnswerHierarchy,
  deduplicateSources,
  type ChatIntent,
  type IntentAnalysis,
  type EvidenceLevel,
  type StructuredEvidenceItem,
} from '../../lib/chatIntelligence';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp?: string;
  /** Sources attached to this assistant message (from the done event). */
  sources?: string[];
  /** 0-100 confidence score attached to this assistant message. */
  confidence?: number;
  /** True when the LLM was unavailable and we fell back to retrieval-only. */
  fallbackMode?: boolean;
  /** True when this is an inline error (no_repo_selected, etc.). */
  isError?: boolean;
  /** Classified engineering intent of the user prompt */
  intent?: ChatIntent;
  /** Follow-up prompt recommendations */
  followUps?: string[];
  /** Primary cross-surface action */
  actionTarget?: IntentAnalysis['actionTarget'];
  actionLabel?: string;
}

export interface ChatInterfaceProps {
  repoName: string;
  /**
   * A question pushed in from elsewhere in the dashboard (e.g. "Ask about this
   * file" in the reading path). The `token` allows the same text to be sent
   * again. Consumed once, then reported back via `onPendingPromptConsumed`.
   */
  pendingPrompt?: { text: string; token: number } | null;
  onPendingPromptConsumed?: () => void;
  /** Optional metadata passed to enrich dynamic suggested prompts */
  repoMetadata?: {
    techStack?: string[];
    dependencies?: string[];
    entryPoints?: string[];
    cyclesCount?: number;
    componentCount?: number;
    readingSteps?: number;
    healthScore?: number;
  };
}

const createChatSessionId = (): string =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

/**
 * Normalized localStorage key generator for repository conversation history.
 */
function getChatStorageKey(repo: string): string {
  const normalized = (repo || 'default').trim().toLowerCase();
  return `aria-chat-history:${normalized}`;
}

// ---------------------------------------------------------------------------
// Custom Sub-components for Markdown & Layout
// ---------------------------------------------------------------------------

/** Custom helper to inject a blinking cursor element where %%CURSOR%% is found */
const renderChildrenWithCursor = (children: React.ReactNode): React.ReactNode => {
  if (typeof children === 'string' && children.includes('%%CURSOR%%')) {
    const parts = children.split('%%CURSOR%%');
    return (
      <>
        {parts[0]}
        <span className="inline-block h-3.5 w-1.5 ml-1 bg-primary animate-blink align-middle" />
        {parts[1]}
      </>
    );
  }
  if (Array.isArray(children)) {
    return React.Children.map(children, (child) => renderChildrenWithCursor(child));
  }
  return children;
};

/** Safe Token Syntax Renderer - Converts AST tokens into native React elements */
const SafeSyntaxHighlighter: React.FC<{ codeText: string }> = ({ codeText }) => {
  const cleanText = codeText.includes('%%CURSOR%%') ? codeText.split('%%CURSOR%%')[0] : codeText;
  const hasCursor = codeText.includes('%%CURSOR%%');

  const tokens = tokenizeCode(cleanText);

  const getTokenClassName = (type: Token['type']): string => {
    switch (type) {
      case 'comment':
        return 'text-text-subtle italic';
      case 'keyword':
        return 'text-indigo-400 font-semibold';
      case 'string':
        return 'text-emerald-400';
      case 'number':
        return 'text-amber-400';
      case 'operator':
        return 'text-primary/80';
      default:
        return '';
    }
  };

  return (
    <>
      {tokens.map((t, idx) => (
        <span key={idx} className={getTokenClassName(t.type)}>
          {t.text}
        </span>
      ))}
      {hasCursor && <span className="inline-block h-3.5 w-1.5 ml-1 bg-primary animate-blink align-middle" />}
    </>
  );
};

/** Premium CodeBlock with safe syntax highlighting, copy button, and wrap options */
const CodeBlock: React.FC<{ inline?: boolean; className?: string; children: React.ReactNode }> = ({
  inline,
  className,
  children,
}) => {
  const [copied, setCopied] = useState(false);
  const [wrapLines, setWrapLines] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const lang = match ? match[1] : '';
  const codeText = String(children).replace(/\n$/, '');

  if (inline) {
    return (
      <code className="bg-surface-3 px-1.5 py-0.5 rounded text-xs text-primary font-mono select-all">
        {children}
      </code>
    );
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(codeText.includes('%%CURSOR%%') ? codeText.split('%%CURSOR%%')[0] : codeText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-3 border border-border rounded-xl overflow-hidden bg-surface-1 shadow-card flex flex-col w-full fade-up">
      <div className="flex items-center justify-between px-4 py-2.5 bg-surface-2 border-b border-border/80 text-[10px] font-mono text-text-muted select-none shrink-0">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-primary/70"></span>
          <span>{lang || 'code'}</span>
        </div>
        <div className="flex items-center gap-3.5">
          <button
            type="button"
            onClick={() => setWrapLines((v) => !v)}
            className="hover:text-text transition-colors"
          >
            {wrapLines ? 'unwrap' : 'wrap'}
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 hover:text-text transition-colors font-semibold"
          >
            {copied ? (
              <>
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                <span className="text-emerald-500">Copied!</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>
      <pre className={`p-4 overflow-x-auto text-xs font-mono leading-relaxed bg-surface-1/40 ${wrapLines ? 'whitespace-pre-wrap break-all' : 'whitespace-pre'}`}>
        <code>
          <SafeSyntaxHighlighter codeText={codeText} />
        </code>
      </pre>
    </div>
  );
};

/** Markdown Component mapping GFM styles to Tailwind classes with secret redaction */
const Markdown: React.FC<{ content: string; isStreaming: boolean; activeRepo?: string }> = ({
  content,
  isStreaming,
  activeRepo,
}) => {
  const redacted = redactSecrets(content);
  const sanitized = sanitizeMarkdown(redacted);
  const textWithCursor = isStreaming ? sanitized + ' %%CURSOR%%' : sanitized;

  const handleNavigate = (pathOrFile: string) => {
    if (typeof window !== 'undefined') {
      const [owner, repo] = (activeRepo || '').split('/');
      window.dispatchEvent(
        new CustomEvent('aria-open-graph', {
          detail: {
            owner: owner || undefined,
            repo: repo || undefined,
            file: pathOrFile,
            path: pathOrFile,
            source: 'chat',
          },
        })
      );
    }
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code: ({ className, children }) => {
          const match = /language-(\w+)/.exec(className || '');
          const isInline = !match;
          const strVal = String(children).trim();

          // If inline token matches a file path or symbol, make it interactive
          if (isInline && (strVal.includes('/') || strVal.includes('.'))) {
            return (
              <button
                type="button"
                onClick={() => handleNavigate(strVal)}
                className="bg-surface-3 hover:bg-primary/20 hover:text-primary px-1.5 py-0.5 rounded text-xs text-primary font-mono inline-flex items-center gap-1 transition-colors cursor-pointer border border-white/[0.05]"
                title={`Inspect ${strVal} in File Graph`}
              >
                <span>{strVal}</span>
              </button>
            );
          }

          return (
            <CodeBlock inline={isInline} className={className}>
              {children}
            </CodeBlock>
          );
        },
        table: ({ children }) => (
          <div className="overflow-x-auto my-3 border border-border rounded-xl bg-surface-1/25 shadow-card max-w-full">
            <table className="w-full text-left text-xs border-collapse font-sans leading-relaxed">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="bg-surface-2 border-b border-border text-[9px] font-mono font-bold text-text-muted uppercase tracking-wider select-none">{children}</thead>,
        tbody: ({ children }) => <tbody className="divide-y divide-border/40 bg-surface-1/10">{children}</tbody>,
        tr: ({ children }) => <tr className="hover:bg-primary/5 transition-colors">{children}</tr>,
        th: ({ children }) => <th className="p-3 font-semibold text-text-muted">{children}</th>,
        td: ({ children }) => <td className="p-3 text-text/90 font-mono break-all">{children}</td>,
        ul: ({ children }) => <ul className="list-disc pl-5 my-2 space-y-1.5 font-sans">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5 my-2 space-y-1.5 font-sans">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{renderChildrenWithCursor(children)}</li>,
        p: ({ children }) => <p className="leading-relaxed mb-3.5 break-words text-text/95 last:mb-0">{renderChildrenWithCursor(children)}</p>,
        h1: ({ children }) => <h1 className="text-base font-bold border-b border-border/50 pb-1.5 mt-5 mb-2.5 text-text font-mono uppercase tracking-wider">{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mt-4.5 mb-2 text-text font-mono">{children}</h2>,
        h3: ({ children }) => <h3 className="text-xs font-bold mt-4 mb-1.5 text-text-muted font-mono">{children}</h3>,
        blockquote: ({ children }) => <blockquote className="border-l-4 border-primary/40 bg-primary/5 pl-4 py-2.5 my-3 rounded-r-lg italic text-text-muted">{children}</blockquote>,
        a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline font-semibold">{children}</a>,
      }}
    >
      {textWithCursor}
    </ReactMarkdown>
  );
};

/** Streaming Typing indicator */
const TypingIndicator: React.FC = () => (
  <div className="flex items-center gap-1 py-1 select-none text-text-muted shrink-0" aria-label="Thinking">
    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce-slow" />
    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce-slow [animation-delay:0.2s]" />
    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce-slow [animation-delay:0.4s]" />
  </div>
);

/** Semantic Badge helper component */
const EvidenceBadge: React.FC<{ level: EvidenceLevel }> = ({ level }) => {
  switch (level) {
    case 'VERIFIED':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9.5px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <Shield className="h-2.5 w-2.5" /> VERIFIED
        </span>
      );
    case 'STRONGLY INFERRED':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9.5px] font-mono font-bold bg-primary/10 text-primary border border-primary/20">
          <Workflow className="h-2.5 w-2.5" /> STRONGLY INFERRED
        </span>
      );
    case 'INFERRED':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9.5px] font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <Info className="h-2.5 w-2.5" /> INFERRED
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9.5px] font-mono font-bold bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">
          <AlertTriangle className="h-2.5 w-2.5" /> UNKNOWN
        </span>
      );
  }
};

/** Key Files Table/List */
const KeyFilesSection: React.FC<{ files: { filePath: string; role: string }[]; activeRepo?: string }> = ({
  files,
  activeRepo,
}) => {
  if (!files || files.length < 2) return null;

  const handleNavigate = (path: string) => {
    if (typeof window !== 'undefined') {
      const [owner, repo] = (activeRepo || '').split('/');
      window.dispatchEvent(
        new CustomEvent('aria-open-graph', {
          detail: { owner, repo, file: path, path, source: 'chat' },
        })
      );
    }
  };

  return (
    <div className="my-3 p-3 rounded-xl border border-white/[0.08] bg-surface-1/70 shadow-card">
      <div className="flex items-center gap-2 mb-2.5 text-[10px] font-mono font-bold text-text-muted uppercase tracking-wider">
        <FileText className="h-3.5 w-3.5 text-primary" /> Key Files & Subsystem Roles
      </div>
      <div className="grid grid-cols-1 gap-1.5">
        {files.map((kf, i) => (
          <div
            key={i}
            className="flex items-center justify-between gap-3 p-2 rounded-lg bg-surface-2/40 border border-white/[0.04] text-[11px]"
          >
            <button
              type="button"
              onClick={() => handleNavigate(kf.filePath)}
              className="font-mono text-primary hover:underline font-semibold truncate text-left"
              title={`Inspect ${kf.filePath}`}
            >
              {kf.filePath}
            </button>
            <span className="font-sans text-text-muted text-[10px] shrink-0 text-right">
              {kf.role}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

/** Progressive Evidence Disclosure Component */
const ProgressiveEvidencePanel: React.FC<{
  evidenceItems: StructuredEvidenceItem[];
  groundingStatus: string;
  fallbackMode: boolean;
  activeRepo?: string;
}> = ({ evidenceItems, groundingStatus, fallbackMode, activeRepo }) => {
  const [panelOpen, setPanelOpen] = useState(true);
  // Auto-expand the top / most relevant evidence item
  const [expandedMap, setExpandedMap] = useState<Record<string, boolean>>({
    [evidenceItems[0]?.id || '0']: true,
  });
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const toggleItem = (id: string) => {
    setExpandedMap((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleNavigateToGraph = (filePath: string) => {
    if (typeof window !== 'undefined') {
      const [owner, repo] = (activeRepo || '').split('/');
      window.dispatchEvent(
        new CustomEvent('aria-open-graph', {
          detail: {
            owner: owner || undefined,
            repo: repo || undefined,
            file: filePath,
            path: filePath,
            source: 'chat',
          },
        })
      );
      if (window.location.pathname === '/chat' && activeRepo && owner && repo) {
        window.location.href = `/analysis?owner=${owner}&repo=${repo}&tab=graph&file=${encodeURIComponent(filePath)}`;
      }
    }
  };

  const handleCopyPath = (filePath: string, id: string) => {
    navigator.clipboard.writeText(filePath);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  if (evidenceItems.length === 0) return null;

  return (
    <div className="border border-white/[0.08] rounded-xl overflow-hidden bg-surface-1 text-[11px] font-sans shadow-card fade-up select-none mt-2">
      {/* Header */}
      <button
        type="button"
        onClick={() => setPanelOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 bg-surface-2/80 hover:bg-surface-2 transition-colors focus-visible:outline-none border-b border-white/[0.04]"
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs font-bold text-text flex items-center gap-1.5">
            <FileCode className="h-3.5 w-3.5 text-primary" /> Supporting Evidence ({evidenceItems.length})
          </span>
          <span className="font-mono text-[9.5px] px-2 py-0.5 rounded bg-surface-3/80 text-text-muted border border-white/[0.04]">
            {fallbackMode ? 'Fallback Mode' : `Grounding: ${groundingStatus}`}
          </span>
        </div>
        {panelOpen ? <ChevronUp className="h-3.5 w-3.5 text-text-muted" /> : <ChevronDown className="h-3.5 w-3.5 text-text-muted" />}
      </button>

      {/* Expandable Rows */}
      {panelOpen && (
        <div className="p-3 bg-canvas/60 space-y-2.5">
          {evidenceItems.map((item, idx) => {
            const isExpanded = !!expandedMap[item.id];
            const fileName = item.filePath.split('/').pop() || item.filePath;
            const dir = item.filePath.includes('/') ? item.filePath.substring(0, item.filePath.lastIndexOf('/')) : '';

            return (
              <div
                key={item.id || idx}
                className="border border-white/[0.06] rounded-lg overflow-hidden bg-surface-1/90 transition-all hover:border-primary/30"
              >
                {/* Row Header Toggle */}
                <button
                  type="button"
                  onClick={() => toggleItem(item.id)}
                  className="w-full flex items-center justify-between p-2.5 text-left bg-surface-2/30 hover:bg-surface-2/60 transition-colors focus-visible:outline-none"
                >
                  <div className="flex items-center gap-2 min-w-0 pr-2">
                    {isExpanded ? (
                      <ChevronDown className="h-3.5 w-3.5 text-primary shrink-0" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 text-text-muted shrink-0" />
                    )}
                    <div className="truncate">
                      <span className="font-mono text-[11px] font-semibold text-text truncate">
                        {fileName}
                      </span>
                      {dir && (
                        <span className="font-mono text-[9px] text-text-subtle ml-1.5 truncate">
                          ({dir}/)
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    {item.subsystem && (
                      <span className="hidden sm:inline font-mono text-[9px] text-text-subtle px-1.5 py-0.5 rounded bg-surface-3/50 border border-white/[0.04]">
                        {item.subsystem}
                      </span>
                    )}
                    <EvidenceBadge level={item.level} />
                  </div>
                </button>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="p-3 border-t border-white/[0.04] bg-surface-1/40 space-y-2.5 fade-up">
                    <div className="space-y-1">
                      <span className="text-[9px] font-mono uppercase tracking-wider text-text-subtle font-bold">
                        Why this evidence matters
                      </span>
                      <p className="text-[11px] font-sans text-text/90 leading-relaxed">
                        {item.whyItMatters}
                      </p>
                    </div>

                    <div className="flex items-center justify-between pt-1 text-[10px] font-mono border-t border-white/[0.04] flex-wrap gap-2">
                      <span className="text-text-subtle">
                        Role: <span className="text-text font-semibold">{item.role}</span>
                      </span>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleCopyPath(item.filePath, item.id)}
                          className="px-2 py-1 rounded bg-surface-3/70 hover:bg-surface-3 text-text-muted hover:text-text transition-colors flex items-center gap-1"
                        >
                          {copiedId === item.id ? (
                            <>
                              <Check className="h-3 w-3 text-emerald-400" />
                              <span className="text-emerald-400">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3" />
                              <span>Copy Path</span>
                            </>
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleNavigateToGraph(item.filePath)}
                          className="px-2 py-1 rounded bg-primary/10 border border-primary/25 text-primary hover:bg-primary hover:text-white transition-colors flex items-center gap-1 font-semibold"
                        >
                          <span>Inspect in Graph →</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  repoName,
  pendingPrompt,
  onPendingPromptConsumed,
  repoMetadata,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeRepo, setActiveRepo] = useState<string>(() => {
    if (repoName) return repoName;
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      const owner = urlParams.get('owner');
      const repo = urlParams.get('repo');
      if (owner && repo) return `${owner}/${repo}`;
      if (urlParams.get('repo')) return urlParams.get('repo')!;
      const stored = localStorage.getItem('activeRepo');
      if (stored) return stored;
    }
    return '';
  });
  const [copiedAnswerId, setCopiedAnswerId] = useState<string | null>(null);
  const [noRepoError, setNoRepoError] = useState(false);
  const [lastReferencedEntity, setLastReferencedEntity] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string>(createChatSessionId());

  // Dynamic Suggested Prompts based on repository intelligence
  const dynamicPrompts = useMemo(() => {
    return generateSuggestedPrompts({
      repoName: activeRepo,
      techStack: repoMetadata?.techStack,
      dependencies: repoMetadata?.dependencies,
      entryPoints: repoMetadata?.entryPoints,
      cyclesCount: repoMetadata?.cyclesCount,
      componentCount: repoMetadata?.componentCount,
      readingSteps: repoMetadata?.readingSteps,
      healthScore: repoMetadata?.healthScore,
    });
  }, [activeRepo, repoMetadata]);

  // Load persisted chat history for active repository
  useEffect(() => {
    if (!activeRepo) {
      setMessages([]);
      return;
    }
    const storageKey = getChatStorageKey(activeRepo);
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        setMessages(JSON.parse(stored));
      } else {
        setMessages([]);
      }
    } catch (e) {
      console.error('Failed to load chat history', e);
      setMessages([]);
    }
  }, [activeRepo]);

  // Persist chat history changes to localStorage
  const saveChatHistory = (nextMessages: Message[]) => {
    if (!activeRepo || typeof window === 'undefined') return;
    const storageKey = getChatStorageKey(activeRepo);
    try {
      localStorage.setItem(storageKey, JSON.stringify(nextMessages));
    } catch (e) {
      console.error('Failed to persist chat history', e);
    }
  };

  const handleClearHistory = () => {
    setMessages([]);
    if (activeRepo && typeof window !== 'undefined') {
      const storageKey = getChatStorageKey(activeRepo);
      localStorage.removeItem(storageKey);
    }
  };

  // Sync active repo changes from prop
  useEffect(() => {
    if (repoName) {
      setActiveRepo(repoName);
      setNoRepoError(false);
    }
  }, [repoName]);

  // Fallback: If still no activeRepo on mount, look up recent analyzed repos from the backend
  useEffect(() => {
    if (!activeRepo) {
      fetch(apiUrl('/api/v1/repos/recent'))
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data) && data.length > 0 && data[0].name) {
            const foundRepo = data[0].name;
            setActiveRepo(foundRepo);
            if (typeof window !== 'undefined') {
              localStorage.setItem('activeRepo', foundRepo);
              window.dispatchEvent(new CustomEvent('active-repo-changed', { detail: foundRepo }));
            }
          } else {
            setNoRepoError(true);
          }
        })
        .catch(() => {
          setNoRepoError(true);
        });
    }
  }, [activeRepo]);

  // Window events for active repo synchronization
  useEffect(() => {
    const handleRepoChanged = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail) {
        setActiveRepo(customEvent.detail);
        setNoRepoError(false);
      }
    };
    const handleRepoCleared = () => {
      setActiveRepo('');
      setNoRepoError(true);
    };

    window.addEventListener('active-repo-changed', handleRepoChanged);
    window.addEventListener('active-repo-cleared', handleRepoCleared);
    return () => {
      window.removeEventListener('active-repo-changed', handleRepoChanged);
      window.removeEventListener('active-repo-cleared', handleRepoCleared);
    };
  }, []);

  // Scroll bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleCopyAnswer = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedAnswerId(id);
    setTimeout(() => setCopiedAnswerId(null), 2000);
  };

  // Cross-surface navigation helper
  const handleCrossSurfaceAction = (target?: IntentAnalysis['actionTarget'], file?: string) => {
    if (!target || typeof window === 'undefined') return;
    const [owner, repo] = (activeRepo || '').split('/');

    if (target === 'graph') {
      window.dispatchEvent(
        new CustomEvent('aria-open-graph', {
          detail: { owner, repo, file, path: file, source: 'chat' },
        })
      );
    } else if (target === 'pr_intelligence') {
      window.dispatchEvent(
        new CustomEvent('aria-open-impact', {
          detail: { owner, repo, source: 'chat' },
        })
      );
    }

    if (owner && repo) {
      const targetUrl = `/analysis?owner=${owner}&repo=${repo}&tab=${target}${file ? `&file=${encodeURIComponent(file)}` : ''}`;
      if (window.location.pathname === '/chat') {
        window.location.href = targetUrl;
      } else {
        const url = new URL(window.location.href);
        url.searchParams.set('tab', target);
        if (file) url.searchParams.set('file', file);
        window.history.pushState({}, '', url.toString());
        window.dispatchEvent(new PopStateEvent('popstate'));
      }
    }
  };

  const triggerStreamResponse = async (userPrompt: string, updatedHistory: Message[], intentInfo: IntentAnalysis) => {
    setIsStreaming(true);
    const assistantId = Math.random().toString();
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const initialAssistantMsg: Message = {
      id: assistantId,
      sender: 'assistant',
      text: '',
      timestamp,
      intent: intentInfo.intent,
      actionTarget: intentInfo.actionTarget,
      actionLabel: intentInfo.actionLabel,
    };

    const nextHistory = [...updatedHistory, initialAssistantMsg];
    setMessages(nextHistory);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let accumulatedText = '';

    try {
      const response = await fetch(apiUrl('/api/v1/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo: activeRepo,
          message: userPrompt,
          session_id: sessionIdRef.current,
          history: updatedHistory.map((m) => ({
            role: m.sender === 'user' ? 'user' : 'model',
            parts: [m.text],
          })),
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail = `Backend error ${response.status}`;
        try {
          const errBody = await response.json();
          if (errBody?.detail) {
            if (Array.isArray(errBody.detail)) {
              detail = errBody.detail.map((d: any) => d.msg).join('; ');
            } else {
              detail = String(errBody.detail);
            }
          }
        } catch { /* ignore */ }
        
        setMessages((prev) => {
          const updated = prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, text: detail, isError: true }
              : msg
          );
          saveChatHistory(updated);
          return updated;
        });
        return;
      }

      if (!response.body) throw new Error('ReadableStream not available');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let finished = false;

      while (!finished) {
        const { value, done } = await reader.read();
        finished = done;
        if (!value) continue;

        const raw = decoder.decode(value);
        const lines = raw.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));

            if (data.error) {
              const fallbackSources = deduplicateSources(data.sources ?? []);
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        text: data.message ?? data.error,
                        fallbackMode: true,
                        sources: fallbackSources.length > 0 ? fallbackSources : msg.sources,
                      }
                    : msg
                )
              );
              continue;
            }

            if (data.text) {
              accumulatedText += data.text;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? { ...msg, text: msg.text + data.text }
                    : msg
                )
              );
            }

            if (data.status === 'done') {
              const finalSources: string[] = deduplicateSources(data.sources ?? []);
              if (finalSources.length > 0) {
                setLastReferencedEntity(finalSources[0]);
              }
              const serverFollowUps = Array.isArray(data.follow_ups) && data.follow_ups.length > 0 ? data.follow_ups : null;
              const followUps = serverFollowUps || generateFollowUpPrompts(userPrompt, intentInfo.intent, accumulatedText, finalSources);

              setMessages((prev) => {
                const finalTxt = accumulatedText.trim() || '⚠️ The AI provider returned an empty response. Repository intelligence fallback applied.';
                const updated = prev.map((msg) => {
                  if (msg.id !== assistantId) return msg;
                  return {
                    ...msg,
                    text: finalTxt,
                    sources: finalSources,
                    confidence: data.confidence ?? 0,
                    fallbackMode: data.fallback_mode ?? false,
                    followUps,
                  };
                });
                saveChatHistory(updated);
                return updated;
              });
            }
          } catch {
            /* ignore JSON parse errors */
          }
        }
      }

      // Final check: if stream finished cleanly but accumulatedText is empty
      if (!accumulatedText.trim()) {
        setMessages((prev) => {
          const updated = prev.map((msg) =>
            msg.id === assistantId && !msg.text.trim()
              ? { ...msg, text: '⚠️ The AI provider returned an empty response. Repository intelligence fallback applied.', isError: true }
              : msg
          );
          saveChatHistory(updated);
          return updated;
        });
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setMessages((prev) => {
          const updated = prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, text: msg.text + '\n\n*Stream generation stopped.*' }
              : msg
          );
          saveChatHistory(updated);
          return updated;
        });
      } else {
        console.error('Chat stream error:', err);
        setMessages((prev) => {
          const updated = prev.map((msg) =>
            msg.id === assistantId
              ? {
                  ...msg,
                  text: 'Could not reach the agent backend. Please verify that the backend server is running and reachable.',
                  isError: true,
                }
              : msg
          );
          saveChatHistory(updated);
          return updated;
        });
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleSend = async (textToSend: string) => {
    const rawText = textToSend.trim();
    if (!rawText || isStreaming) return;

    // Detect intent and resolve context/pronouns
    const intentInfo = detectChatIntent(rawText);
    const resolvedPrompt = resolvePronouns(rawText, lastReferencedEntity);

    // Update referenced entity if explicit file mentioned
    if (intentInfo.entities.length > 0) {
      setLastReferencedEntity(intentInfo.entities[0].normalized);
    }

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMessage: Message = {
      id: Math.random().toString(),
      sender: 'user',
      text: rawText,
      timestamp,
      intent: intentInfo.intent,
    };

    const nextHistory = [...messages, userMessage];
    setMessages(nextHistory);
    setInput('');

    await triggerStreamResponse(resolvedPrompt, nextHistory, intentInfo);
  };

  /**
   * Dispatches a question handed in from another panel.
   */
  const consumedPromptTokenRef = useRef<number | null>(null);
  useEffect(() => {
    if (!pendingPrompt?.text) return;
    if (consumedPromptTokenRef.current === pendingPrompt.token) return;
    if (isStreaming) return;

    consumedPromptTokenRef.current = pendingPrompt.token;
    onPendingPromptConsumed?.();
    void handleSend(pendingPrompt.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt?.text, pendingPrompt?.token, isStreaming]);

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleRegenerate = async () => {
    const userMsgs = messages.filter((m) => m.sender === 'user');
    if (userMsgs.length === 0) return;
    const lastUserMsg = userMsgs[userMsgs.length - 1];

    let nextMsgs = [...messages];
    if (nextMsgs[nextMsgs.length - 1]?.sender === 'assistant') {
      nextMsgs.pop();
    }

    const intentInfo = detectChatIntent(lastUserMsg.text);
    setMessages(nextMsgs);
    await triggerStreamResponse(lastUserMsg.text, nextMsgs, intentInfo);
  };

  return (
    <div className="flex flex-col min-h-[550px] h-full border border-border bg-card/10 rounded-xl overflow-hidden w-full shadow-float">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-card/45 shrink-0 select-none">
        <div className="flex items-center gap-2">
          <MessageSquareCode className="h-4 w-4 text-primary" />
          <span className="font-mono text-xs font-bold text-text uppercase tracking-wider">
            Repository Engineering Copilot
          </span>
        </div>

        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClearHistory}
              className="text-[10px] font-mono text-text-subtle hover:text-text hover:underline flex items-center gap-1 mr-1 transition-colors"
              title="Clear conversation history"
            >
              <Trash2 className="h-3 w-3" />
              <span>Clear</span>
            </button>
          )}

          <span className="text-[10px] font-mono border border-primary/25 text-primary px-2.5 py-0.5 rounded-md bg-primary/5 truncate max-w-[200px]">
            {activeRepo || 'no repo'}
          </span>
        </div>
      </div>

      {/* No-repo state */}
      {noRepoError && (
        <div className="flex-grow flex flex-col items-center justify-center p-8 gap-3.5 text-center fade-up">
          <div className="h-12 w-12 rounded-full bg-amber-500/10 border border-amber-500/25 flex items-center justify-center text-amber-500 select-none">
            <AlertTriangle className="h-6 w-6" />
          </div>
          <p className="text-sm font-semibold text-text">
            No active repository found
          </p>
          <p className="text-xs text-text-muted max-w-xs leading-relaxed font-sans">
            Please analyze a repository on the homepage to start asking questions about its codebase.
          </p>
        </div>
      )}

      {/* Empty State Welcome Dashboard with Dynamic Prompts */}
      {!noRepoError && messages.length === 0 && (
        <div className="flex-grow flex flex-col items-center justify-center p-6 gap-6 text-center max-w-2xl mx-auto my-auto fade-up">
          <div className="h-12 w-12 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary select-none">
            <Sparkles className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h2 className="text-base font-bold text-text font-mono">Chat with {activeRepo}</h2>
            <p className="text-xs text-text-muted leading-relaxed font-sans max-w-md">
              Ask about execution flows, function callers, change planning, blast radius impact, or architectural bottlenecks.
            </p>
          </div>

          <div className="w-full text-left mt-2 select-none">
            <p className="text-[10px] uppercase font-mono tracking-widest text-text-subtle font-semibold mb-3 flex items-center gap-1.5 justify-center">
              Suggested Engineering Inquiries
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {dynamicPrompts.map((q) => (
                <button
                  key={q}
                  onClick={() => handleSend(q)}
                  className="card p-3 text-left hover:border-primary/40 hover:bg-primary/5 transition-all text-xs font-sans text-text-muted hover:text-text duration-200 group flex items-start gap-2.5"
                >
                  <MessageSquareCode className="h-4 w-4 text-primary/70 shrink-0 mt-0.5 group-hover:text-primary transition-colors" />
                  <span className="leading-relaxed">{q}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Message thread */}
      {!noRepoError && messages.length > 0 && (
        <div className="flex-grow overflow-y-auto p-5 space-y-5 font-sans text-xs">
          {messages.map((msg, idx) => {
            const hierarchy = msg.sender === 'assistant' ? parseAnswerHierarchy(msg.text, msg.sources, msg.confidence) : null;

            return (
              <div
                key={msg.id}
                className={`flex gap-3 fade-up ${
                  msg.sender === 'user' ? 'ml-auto flex-row-reverse max-w-[85%]' : 'max-w-[94%]'
                }`}
              >
                {/* Avatar */}
                <div
                  className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 border select-none ${
                    msg.sender === 'user'
                      ? 'bg-primary/10 border-primary/30 text-primary'
                      : msg.isError
                      ? 'bg-red-500/10 border-red-500/30 text-red-400'
                      : 'bg-card border-border text-text-muted'
                  }`}
                >
                  {msg.sender === 'user' ? (
                    <User className="h-4 w-4" />
                  ) : (
                    <Bot className="h-4 w-4" />
                  )}
                </div>

                {/* Bubble + Citations + Actions */}
                <div className="flex flex-col gap-1.5 min-w-0 flex-1">
                  {/* Intent indicator if present */}
                  {msg.sender === 'user' && msg.intent && msg.intent !== 'GENERAL_REPOSITORY' && (
                    <span className="text-[9px] font-mono uppercase text-text-subtle self-end px-1">
                      Intent: {msg.intent.replace('_', ' ')}
                    </span>
                  )}

                  <div
                    className={`p-3.5 rounded-xl border leading-relaxed break-words shadow-card ${
                      msg.sender === 'user'
                        ? 'bg-primary/10 border-primary/20 text-text'
                        : msg.isError
                        ? 'bg-red-500/5 border-red-500/20 text-red-400 font-mono'
                        : msg.fallbackMode
                        ? 'bg-amber-500/5 border-amber-500/20 text-text'
                        : 'bg-card/40 border-border text-text'
                    }`}
                  >
                    {msg.sender === 'user' ? (
                      <p className="whitespace-pre-wrap leading-relaxed break-words text-text/95">
                        {msg.text}
                      </p>
                    ) : msg.text === '' ? (
                      <TypingIndicator />
                    ) : (
                      <div className="markdown-body font-sans text-[12px] overflow-hidden">
                        <Markdown
                          content={msg.text}
                          isStreaming={isStreaming && idx === messages.length - 1}
                          activeRepo={activeRepo}
                        />

                        {/* First-class Key Files Section */}
                        {hierarchy && hierarchy.keyFiles.length >= 2 && !isStreaming && (
                          <KeyFilesSection files={hierarchy.keyFiles} activeRepo={activeRepo} />
                        )}
                      </div>
                    )}
                  </div>

                  {/* Message Timestamp */}
                  {msg.timestamp && (
                    <span className={`text-[8px] font-mono text-text-muted mt-0.5 px-1 select-none ${
                      msg.sender === 'user' ? 'self-end' : 'self-start'
                    }`}>
                      {msg.timestamp}
                    </span>
                  )}

                  {/* Toolbar & Cross-Surface Action Bar under assistant bubble */}
                  {msg.sender === 'assistant' && msg.text !== '' && (
                    <div className="space-y-2 mt-1 pl-1">
                      <div className="flex items-center gap-3.5 text-[10px] text-text-muted select-none flex-wrap">
                        <button
                          type="button"
                          onClick={() => handleCopyAnswer(msg.text, msg.id)}
                          className="flex items-center gap-1 hover:text-text transition-colors"
                        >
                          {copiedAnswerId === msg.id ? (
                            <>
                              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                              <span className="text-emerald-500 font-semibold">Copied answer</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3.5 w-3.5" />
                              <span>Copy answer</span>
                            </>
                          )}
                        </button>
                        
                        {idx === messages.length - 1 && !isStreaming && (
                          <button
                            type="button"
                            onClick={handleRegenerate}
                            className="flex items-center gap-1 hover:text-text transition-colors font-semibold"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            <span>Regenerate</span>
                          </button>
                        )}

                        {/* Primary Cross-Surface Action Button */}
                        {msg.actionTarget && (
                          <button
                            type="button"
                            onClick={() => handleCrossSurfaceAction(msg.actionTarget, msg.sources?.[0])}
                            className="action-chip text-[10px] px-2 py-0.5 inline-flex items-center gap-1 text-primary bg-primary/10 border-primary/25 hover:bg-primary/20 transition-colors focus-visible:outline-none"
                          >
                            <ArrowRight className="h-3 w-3" />
                            <span>{msg.actionLabel || 'Inspect in Graph'}</span>
                          </button>
                        )}
                      </div>

                      {/* Contextual Follow-up Suggestions */}
                      {msg.followUps && msg.followUps.length > 0 && !isStreaming && idx === messages.length - 1 && (
                        <div className="pt-2 border-t border-white/[0.05] space-y-1.5">
                          <span className="mono-detail text-[9.5px] text-text-subtle uppercase tracking-wider block">
                            SUGGESTED FOLLOW-UP INQUIRIES
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {msg.followUps.map((prompt) => (
                              <button
                                key={prompt}
                                type="button"
                                onClick={() => handleSend(prompt.replace(/^→\s*/, ''))}
                                className="text-[11px] font-sans px-2.5 py-1 rounded-md bg-surface-1/60 border border-white/[0.06] text-text-muted hover:text-primary hover:border-primary/40 transition-colors text-left"
                              >
                                {prompt}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Progressively Disclosed Grounded Evidence Panel */}
                  {msg.sender === 'assistant' &&
                    hierarchy &&
                    hierarchy.evidenceItems.length > 0 && (
                      <ProgressiveEvidencePanel
                        evidenceItems={hierarchy.evidenceItems}
                        groundingStatus={hierarchy.groundingStatus}
                        fallbackMode={msg.fallbackMode ?? false}
                        activeRepo={activeRepo}
                      />
                    )}
                </div>
              </div>
            );
          })}

          {/* Inline Stop button while streaming */}
          {isStreaming && (
            <div className="flex items-center justify-center py-2 fade-up select-none">
              <button
                type="button"
                onClick={handleStop}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/25 bg-red-500/5 text-red-500 hover:bg-red-500/10 text-[10px] font-mono uppercase tracking-wider font-bold transition-all focus-visible:outline-none"
              >
                <StopCircle className="h-3.5 w-3.5" />
                Stop Generation
              </button>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      )}

      {/* Input bar */}
      {!noRepoError && (
        <div className="p-3.5 border-t border-border bg-card/25 shrink-0">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend(input);
            }}
            className="flex gap-2 items-end"
          >
            <textarea
              value={input}
              rows={1}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend(input);
                }
              }}
              disabled={isStreaming || !activeRepo}
              placeholder={
                activeRepo
                  ? `Ask a question about ${activeRepo}… (Enter to send)`
                  : 'Waiting for repository...'
              }
              aria-label="Chat message"
              className="flex-grow bg-canvas border border-border rounded-lg px-3.5 py-2.5 text-xs focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary font-sans text-text placeholder:text-text-muted/40 resize-none overflow-hidden leading-relaxed"
              style={{ minHeight: '40px' }}
            />
            <button
              type="submit"
              disabled={isStreaming || !input.trim() || !activeRepo}
              aria-label="Send message"
              className="bg-primary hover:bg-primary-hover text-text font-medium px-4 py-2.5 rounded-lg flex items-center gap-1.5 text-xs transition-all disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:shadow-ring shrink-0 hover:scale-[1.02] active:scale-[0.98] duration-150"
            >
              {isStreaming ? (
                <RefreshCw className="h-4 w-4 animate-spin text-text" aria-hidden="true" />
              ) : (
                <Send className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};

export default ChatInterface;
