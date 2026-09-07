import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Search,
  Settings,
  Package,
  ExternalLink,
  RotateCcw,
  Check,
  ChevronDown,
  AlertCircle,
  Activity,
  Cpu,
  Menu,
  X,
  FileText,
  Trash2,
  AlertTriangle,
  GitCommit,
  GitPullRequest,
  GitCompare,
  Target,
} from 'lucide-react';
import { API_BASE_URL, apiUrl, getEngineStatus, type EngineStatusResult } from '../../lib/api';
import { ANALYSIS_TABS, type AnalysisTabId } from '../../lib/analysisTabs';

// ── Types ───────────────────────────────────────────────────────────────────

interface PrimaryNavLink {
  id: AnalysisTabId;
  label: string;
}

const PRIMARY_LINKS: PrimaryNavLink[] = [
  { id: 'analysis', label: 'Overview' },
  { id: 'reading_path', label: 'Reading Path' },
  { id: 'chat', label: 'Chat' },
  { id: 'graph', label: 'File Graph' },
  { id: 'call_graph', label: 'Call Graph' },
  { id: 'api_surface', label: 'API Surface' },
];

const SECONDARY_LINKS = ANALYSIS_TABS.filter(
  (t) => !PRIMARY_LINKS.some((p) => p.id === t.id)
);

const SECONDARY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  report: FileText,
  dead_code: Trash2,
  issues: AlertTriangle,
  git_history: GitCommit,
  pr_intelligence: GitPullRequest,
  architecture_drift: GitCompare,
  impact_analysis: Target,
};

export const AppNavbar: React.FC = () => {
  // ── Route & Repository State ──────────────────────────────────────────────
  const [activeRepo, setActiveRepo] = useState<string>('');
  const [activeTab, setActiveTab] = useState<AnalysisTabId>('analysis');
  const [isLandingPage, setIsLandingPage] = useState(false);
  const [isMac, setIsMac] = useState(false);

  // ── Dropdown / Modal States ───────────────────────────────────────────────
  const [repoDropdownOpen, setRepoDropdownOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const [moreToolsOpen, setMoreToolsOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // ── Engine Status State ───────────────────────────────────────────────────
  const [engineStatus, setEngineStatus] = useState<EngineStatusResult>({
    state: 'ready',
    label: 'CHECKING ENGINE...',
  });
  const [recentRepos, setRecentRepos] = useState<{ name: string; tech_stack?: string[] }[]>([]);
  const [quickSwitchInput, setQuickSwitchInput] = useState('');
  const [switchError, setSwitchError] = useState<string | null>(null);

  // ── Refs for Outside Click & Keyboard Trapping ────────────────────────────
  const repoDropdownRef = useRef<HTMLDivElement>(null);
  const settingsRef = useRef<HTMLDivElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);
  const moreToolsRef = useRef<HTMLDivElement>(null);

  // ── Detect OS Platform for Keyboard Badge ─────────────────────────────────
  useEffect(() => {
    if (typeof navigator !== 'undefined') {
      setIsMac(/Mac|iPod|iPhone|iPad/.test(navigator.platform || navigator.userAgent));
    }
  }, []);

  // ── Active Tab & Repo Detection ───────────────────────────────────────────
  const syncRouteAndRepo = useCallback(() => {
    if (typeof window === 'undefined') return;

    // Active Repo from URL or localStorage
    const params = new URLSearchParams(window.location.search);
    const owner = params.get('owner');
    const repo = params.get('repo');
    const storedRepo = localStorage.getItem('activeRepo') || '';

    let resolvedRepo = '';
    if (owner && repo) {
      resolvedRepo = `${owner}/${repo}`;
      if (resolvedRepo !== storedRepo) {
        localStorage.setItem('activeRepo', resolvedRepo);
      }
    } else if (storedRepo) {
      resolvedRepo = storedRepo;
    }
    setActiveRepo(resolvedRepo);

    // Active Tab & Landing Page check
    const pathname = window.location.pathname;
    setIsLandingPage(pathname === '/' || pathname === '');
    if (pathname === '/chat') {
      setActiveTab('chat');
    } else if (pathname === '/issues') {
      setActiveTab('issues');
    } else if (pathname === '/analysis') {
      const tabParam = params.get('tab') as AnalysisTabId | null;
      if (tabParam && ANALYSIS_TABS.some((t) => t.id === tabParam)) {
        setActiveTab(tabParam);
      } else {
        setActiveTab('analysis');
      }
    } else if (pathname === '/') {
      // Home page
      const tabParam = params.get('tab') as AnalysisTabId | null;
      if (tabParam) {
        setActiveTab(tabParam);
      }
    }
  }, []);

  useEffect(() => {
    syncRouteAndRepo();

    const handlePopState = () => syncRouteAndRepo();
    const handleRepoChanged = (e: any) => {
      if (e.detail && typeof e.detail === 'string') {
        setActiveRepo(e.detail);
      } else {
        syncRouteAndRepo();
      }
    };
    const handleRepoCleared = () => {
      setActiveRepo('');
    };
    const handleTabChanged = (e: any) => {
      if (e.detail && e.detail.tab) {
        setActiveTab(e.detail.tab);
      }
    };

    window.addEventListener('popstate', handlePopState);
    window.addEventListener('active-repo-changed', handleRepoChanged);
    window.addEventListener('active-repo-cleared', handleRepoCleared);
    window.addEventListener('aria-tab-changed', handleTabChanged);

    return () => {
      window.removeEventListener('popstate', handlePopState);
      window.removeEventListener('active-repo-changed', handleRepoChanged);
      window.removeEventListener('active-repo-cleared', handleRepoCleared);
      window.removeEventListener('aria-tab-changed', handleTabChanged);
    };
  }, [syncRouteAndRepo]);

  // ── Global Keyboard Shortcuts (Cmd+K / Ctrl+K / Esc) ──────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('open-command-palette'));
      } else if (e.key === 'Escape') {
        setRepoDropdownOpen(false);
        setSettingsOpen(false);
        setStatusOpen(false);
        setMoreToolsOpen(false);
        setMobileMenuOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // ── Outside Click Listeners ───────────────────────────────────────────────
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (repoDropdownRef.current && !repoDropdownRef.current.contains(e.target as Node)) {
        setRepoDropdownOpen(false);
      }
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) {
        setStatusOpen(false);
      }
      if (moreToolsRef.current && !moreToolsRef.current.contains(e.target as Node)) {
        setMoreToolsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // ── Periodic Engine Status Poll ───────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    const probeStatus = async () => {
      const res = await getEngineStatus(3500);
      if (mounted) {
        setEngineStatus(res);
      }
    };

    probeStatus();
    const interval = setInterval(probeStatus, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // ── Fetch Recent Repositories for Switcher ────────────────────────────────
  const fetchRecentRepos = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/v1/repos/recent'));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setRecentRepos(data.slice(0, 5));
        }
      }
    } catch {
      // Non-fatal
    }
  }, []);

  useEffect(() => {
    if (repoDropdownOpen) {
      fetchRecentRepos();
    }
  }, [repoDropdownOpen, fetchRecentRepos]);

  // ── Navigation Handler ────────────────────────────────────────────────────
  const handleNavClick = (tabId: AnalysisTabId) => {
    setMobileMenuOpen(false);
    setMoreToolsOpen(false);
    setActiveTab(tabId);

    const isAnalysisPage = window.location.pathname === '/analysis';

    if (isAnalysisPage) {
      // In-page navigation: update URL query parameter and trigger tab change event
      const url = new URL(window.location.href);
      url.searchParams.set('tab', tabId);
      window.history.pushState({}, '', url.toString());
      window.dispatchEvent(new CustomEvent('aria-navigate-tab', { detail: { tab: tabId } }));
    } else {
      // Navigating from another page: resolve active repository
      let repoToUse = activeRepo;
      if (!repoToUse) {
        repoToUse = localStorage.getItem('activeRepo') || '';
      }

      if (repoToUse) {
        const [o, r] = repoToUse.split('/');
        window.location.href = `/analysis?owner=${encodeURIComponent(o)}&repo=${encodeURIComponent(r)}&tab=${tabId}`;
      } else {
        // Fallback: take user to analysis landing to select or index a repository
        window.location.href = '/#analyze';
      }
    }
  };

  // ── Repository Switch Handlers ────────────────────────────────────────────
  const handleSwitchRepo = (targetRepo: string) => {
    const trimmed = targetRepo.trim();
    if (!trimmed) return;

    let owner = '';
    let repo = '';

    if (trimmed.includes('github.com/')) {
      const clean = trimmed.replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '');
      const parts = clean.split('/');
      owner = parts[0] || '';
      repo = parts[1] || '';
    } else if (trimmed.includes('/')) {
      const parts = trimmed.split('/');
      owner = parts[0] || '';
      repo = parts[1] || '';
    }

    if (!owner || !repo) {
      setSwitchError('Please enter a valid owner/repo slug or GitHub URL');
      return;
    }

    setSwitchError(null);
    setRepoDropdownOpen(false);
    setQuickSwitchInput('');
    const fullSlug = `${owner}/${repo}`;
    localStorage.setItem('activeRepo', fullSlug);
    window.dispatchEvent(new CustomEvent('active-repo-changed', { detail: fullSlug }));
    window.location.href = `/analysis?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}&tab=${activeTab}`;
  };

  const handleClearRepoContext = () => {
    localStorage.removeItem('activeRepo');
    setActiveRepo('');
    setRepoDropdownOpen(false);
    window.dispatchEvent(new CustomEvent('active-repo-cleared'));
    window.location.href = '/';
  };

  const isSecondaryActive = useMemo(() => {
    return SECONDARY_LINKS.some((s) => s.id === activeTab);
  }, [activeTab]);

  return (
    <header
      id="aria-app-shell-navbar"
      className="sticky top-0 z-50 w-full h-[52px] border-b border-[#202631] bg-[#050608]/90 backdrop-blur-md select-none transition-colors"
      role="banner"
    >
      <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-3 sm:px-5 lg:px-7 gap-3 sm:gap-6">
        {/* ── LEFT: Brand + Primary Horizontal Navigation ── */}
        <div className="flex items-center gap-3 lg:gap-6 min-w-0">
          {/* Brand */}
          <a
            href="/"
            className="flex items-center gap-2 shrink-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#7C83FF] rounded px-1 -mx-1"
            aria-label="ARIA Home"
          >
            <span
              className="h-2 w-2 rounded-full bg-[#7C83FF] shadow-[0_0_12px_rgba(124,131,255,0.6)]"
              aria-hidden="true"
            />
            <span className="text-[13px] font-bold tracking-[0.24em] text-[#F5F7FA] font-mono uppercase">
              ARIA
            </span>
          </a>

          {/* Primary Navigation Links (Desktop) */}
          {isLandingPage ? (
            <nav
              className="hidden lg:flex items-center gap-1.5"
              aria-label="Marketing Navigation"
            >
              {[
                { label: 'WHY ARIA', href: '#premise' },
                { label: 'HOW IT WORKS', href: '#graph' },
                { label: 'CAPABILITIES', href: '#change' },
                { label: 'SELF-HOST', href: '#analyze' },
              ].map((item) => (
                <a
                  key={item.label}
                  href={item.href}
                  className="px-3 py-1.5 text-[11.5px] lg:text-[12px] font-mono tracking-wider text-[#818895] hover:text-[#F4F5F7] transition-colors rounded-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#737DFF]"
                >
                  {item.label}
                </a>
              ))}
              <a
                href="https://github.com/VarshithReddy2006/ARIA"
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 text-[11.5px] lg:text-[12px] font-mono tracking-wider text-[#818895] hover:text-[#F4F5F7] transition-colors rounded-md inline-flex items-center gap-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#737DFF]"
              >
                <span>GITHUB</span>
                <ExternalLink className="h-2.5 w-2.5 opacity-60" />
              </a>
            </nav>
          ) : (
            <nav
              className="hidden lg:flex items-center gap-0.5"
              aria-label="Primary Instrument Navigation"
            >
              {PRIMARY_LINKS.map((link) => {
                const isActive = activeTab === link.id;
                return (
                  <button
                    key={link.id}
                    type="button"
                    onClick={() => handleNavClick(link.id)}
                    aria-current={isActive ? 'page' : undefined}
                    className={`relative px-1.5 lg:px-2.5 py-1.5 text-[11.5px] lg:text-[12.5px] font-sans whitespace-nowrap transition-colors rounded-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#737DFF] ${
                      isActive
                        ? 'text-[#F4F5F7] font-semibold'
                        : 'text-[#818895] hover:text-[#C3C7D0] font-normal'
                    }`}
                  >
                    <span>{link.label}</span>
                    {isActive && (
                      <span
                        className="absolute bottom-[-10px] left-1.5 right-1.5 h-[2px] bg-[#737DFF] rounded-full shadow-[0_0_8px_rgba(115,125,255,0.4)]"
                        aria-hidden="true"
                      />
                    )}
                  </button>
                );
              })}

            {/* Secondary Tools Dropdown */}
            <div className="relative" ref={moreToolsRef}>
              <button
                type="button"
                onClick={() => setMoreToolsOpen((prev) => !prev)}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11.5px] lg:text-[12px] font-sans transition-colors rounded-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#7C83FF] ${
                  isSecondaryActive
                    ? 'text-[#7C83FF] font-semibold bg-[rgba(124,131,255,0.10)] border border-[rgba(124,131,255,0.38)]'
                    : 'text-[#858D9A] hover:text-[#D0D5DD] hover:bg-[#11141B] font-normal'
                }`}
                aria-expanded={moreToolsOpen}
                aria-haspopup="true"
                aria-label="More analysis instruments"
              >
                <span>
                  {isSecondaryActive
                    ? SECONDARY_LINKS.find((s) => s.id === activeTab)?.label || 'More'
                    : 'More'}
                </span>
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${moreToolsOpen ? 'rotate-180' : ''}`}
                  aria-hidden="true"
                />
              </button>

              {moreToolsOpen && (
                <div
                  className="absolute left-0 mt-2 w-64 rounded-lg border border-[#2A313C] bg-[#0D1015] p-2 shadow-float z-50 animate-in fade-in zoom-in-95 duration-150 space-y-1.5 backdrop-blur-md"
                  role="menu"
                >
                  <div className="px-2 pt-1 pb-0.5 text-[9px] font-mono uppercase tracking-widest text-[#858D9A] font-bold">
                    Quality &amp; Reliability
                  </div>
                  {SECONDARY_LINKS.filter(t => t.group === 'Quality & Reliability').map((tool) => {
                    const Icon = SECONDARY_ICONS[tool.id] || FileText;
                    const isActive = activeTab === tool.id;
                    return (
                      <button
                        key={tool.id}
                        type="button"
                        onClick={() => handleNavClick(tool.id)}
                        className={`w-full text-left px-2.5 py-1.5 rounded-md text-[12px] font-sans transition-all flex items-center justify-between group ${
                          isActive
                            ? 'bg-[rgba(124,131,255,0.10)] text-[#F5F7FA] font-medium border border-[rgba(124,131,255,0.38)]'
                            : 'text-[#B8BEC9] hover:text-[#F5F7FA] hover:bg-[#11141B]'
                        }`}
                        role="menuitem"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Icon className={`h-3.5 w-3.5 shrink-0 ${isActive ? 'text-[#7C83FF]' : 'text-[#858D9A] group-hover:text-[#B8BEC9]'}`} />
                          <span className="truncate">{tool.label}</span>
                        </div>
                        <span className="text-[9px] font-mono text-[#858D9A] shrink-0">
                          {tool.group.split(' ')[0]}
                        </span>
                      </button>
                    );
                  })}

                  <div className="my-1.5 border-t border-[#202631]" />

                  <div className="px-2 pt-1 pb-0.5 text-[9px] font-mono uppercase tracking-widest text-[#858D9A] font-bold">
                    History &amp; Change
                  </div>
                  {SECONDARY_LINKS.filter(t => t.group === 'History & Change').map((tool) => {
                    const Icon = SECONDARY_ICONS[tool.id] || GitCommit;
                    const isActive = activeTab === tool.id;
                    return (
                      <button
                        key={tool.id}
                        type="button"
                        onClick={() => handleNavClick(tool.id)}
                        className={`w-full text-left px-2.5 py-1.5 rounded-md text-[12px] font-sans transition-all flex items-center justify-between group ${
                          isActive
                            ? 'bg-[rgba(124,131,255,0.10)] text-[#F5F7FA] font-medium border border-[rgba(124,131,255,0.38)]'
                            : 'text-[#B8BEC9] hover:text-[#F5F7FA] hover:bg-[#11141B]'
                        }`}
                        role="menuitem"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Icon className={`h-3.5 w-3.5 shrink-0 ${isActive ? 'text-[#7C83FF]' : 'text-[#858D9A] group-hover:text-[#B8BEC9]'}`} />
                          <span className="truncate">{tool.label}</span>
                        </div>
                        <span className="text-[9px] font-mono text-[#858D9A] shrink-0">
                          {tool.group.split(' ')[0]}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </nav>
          )}
        </div>

        {/* ── RIGHT: Utility Area (Search, Repo, Status, Settings) ── */}
        <div className="flex items-center gap-2 sm:gap-2.5 shrink-0">
          {isLandingPage && (
            <a
              href={activeRepo ? `/analysis?owner=${encodeURIComponent(activeRepo.split('/')[0])}&repo=${encodeURIComponent(activeRepo.split('/')[1] || '')}` : '/analysis?owner=fastapi&repo=fastapi'}
              className="cta-light-sweep relative group flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-[#818CF8]/50 bg-gradient-to-r from-[#131A2E] to-[#0A0D14] hover:border-[#A5B4FC] text-white transition-all text-xs font-mono font-bold tracking-wider shadow-[0_0_16px_rgba(129,140,248,0.20)] hover:shadow-[0_0_24px_rgba(129,140,248,0.40)] hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#818CF8]"
            >
              <span className="relative z-10 font-mono tracking-wider">OPEN ARIA</span>
              <span className="relative z-10 text-[#818CF8] group-hover:text-white group-hover:translate-x-0.5 transition-all">→</span>
            </a>
          )}

          {/* 1. Search Trigger (⌘K / Ctrl+K) */}
          <button
            type="button"
            onClick={() => window.dispatchEvent(new CustomEvent('open-command-palette'))}
            className="flex items-center gap-2 px-2 sm:px-2.5 py-1 rounded-md border border-[#20242D] bg-[#080A0F] hover:bg-[#0D1016] hover:border-[#2A303C] text-[#818895] hover:text-[#F4F5F7] transition-colors text-xs font-sans focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#737DFF]"
            aria-label={`Search repository (${isMac ? 'Cmd+K' : 'Ctrl+K'})`}
            title={`Search symbols, files, and commands (${isMac ? '⌘K' : 'Ctrl+K'})`}
          >
            <Search className="h-3.5 w-3.5 text-[#818895]" aria-hidden="true" />
            <span className="hidden xl:inline text-[11.5px]">Search</span>
            <kbd className="text-[10px] font-mono bg-[#0D1016] px-1.5 py-0.2 rounded text-[#818895] border border-[#20242D]">
              {isMac ? '⌘K' : 'Ctrl+K'}
            </kbd>
          </button>

          {/* 2. Repository Context Badge & Switcher */}
          <div className="relative" ref={repoDropdownRef}>
            <button
              type="button"
              onClick={() => setRepoDropdownOpen((prev) => !prev)}
              className={`flex items-center gap-1.5 px-2 sm:px-2.5 py-1 rounded-md border text-xs font-mono transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#7C83FF] max-w-[110px] sm:max-w-[130px] lg:max-w-[160px] xl:max-w-[260px] truncate ${
                activeRepo
                  ? 'border-[#202631] bg-[#090B0F] text-[#F5F7FA] hover:border-[#2A313C] hover:bg-[#11141B]'
                  : 'border-dashed border-[#202631] text-[#858D9A] hover:text-[#F5F7FA] hover:border-[#2A313C]'
              }`}
              aria-expanded={repoDropdownOpen}
              aria-haspopup="true"
              aria-label="Active repository switcher"
              title={activeRepo ? `Active: ${activeRepo}` : 'No active repository selected'}
            >
              <Package className="h-3.5 w-3.5 shrink-0 text-[#7C83FF]" aria-hidden="true" />
              <span className="truncate text-[11.5px]">
                {activeRepo || 'Select Repository'}
              </span>
              <ChevronDown
                className={`h-3 w-3 shrink-0 text-[#858D9A] transition-transform ${repoDropdownOpen ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            </button>

            {repoDropdownOpen && (
              <div
                className="absolute right-0 mt-2 w-80 rounded-lg border border-[#2A313C] bg-[#0D1015] p-3 shadow-float z-50 animate-in fade-in zoom-in-95 duration-150 space-y-3 font-sans"
                role="dialog"
                aria-label="Repository Context"
              >
                {/* Header info */}
                <div className="flex items-center justify-between border-b border-[#202631] pb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A]">
                    Active Repository
                  </span>
                  {activeRepo && (
                    <span className="text-[10px] font-mono text-[#35D6A3] bg-[rgba(53,214,163,0.09)] px-1.5 py-0.5 rounded border border-[rgba(53,214,163,0.34)]">
                      INDEXED
                    </span>
                  )}
                </div>

                {/* Current Repo Details */}
                {activeRepo ? (
                  <div className="p-2 rounded bg-[#090B0F] border border-[#202631] space-y-1">
                    <p className="font-mono text-xs text-[#F5F7FA] font-semibold break-all">
                      {activeRepo}
                    </p>
                    <div className="flex items-center justify-between text-[10px] font-mono text-[#858D9A] pt-1">
                      <span>branch: main</span>
                      <a
                        href={`https://github.com/${activeRepo}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#B8BEC9] hover:text-[#F5F7FA] inline-flex items-center gap-1"
                      >
                        GitHub <ExternalLink className="h-2.5 w-2.5" />
                      </a>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-[#B8BEC9]">No repository context active.</p>
                )}

                {/* Quick Switch Input */}
                <div className="space-y-1.5">
                  <label htmlFor="quick-switch-input" className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] block">
                    Switch Repository
                  </label>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      handleSwitchRepo(quickSwitchInput);
                    }}
                    className="flex gap-1.5"
                  >
                    <input
                      id="quick-switch-input"
                      type="text"
                      placeholder="owner/repo or GitHub URL"
                      value={quickSwitchInput}
                      onChange={(e) => {
                        setQuickSwitchInput(e.target.value);
                        setSwitchError(null);
                      }}
                      className="flex-1 bg-[#080A0D] border border-[#202631] focus:border-[#7C83FF] rounded px-2 py-1 text-xs font-mono text-[#F5F7FA] placeholder-[#626A77] focus:outline-none"
                    />
                    <button
                      type="submit"
                      disabled={!quickSwitchInput.trim()}
                      className="px-2.5 py-1 bg-[#7C83FF] hover:bg-[#9197FF] active:bg-[#636BEF] text-white text-xs font-sans rounded disabled:opacity-40 transition-colors shrink-0"
                    >
                      Go
                    </button>
                  </form>
                  {switchError && (
                    <p className="text-[10px] text-[#F27781] font-mono">{switchError}</p>
                  )}
                </div>

                {/* Recent Repositories */}
                {recentRepos.length > 0 && (
                  <div className="space-y-1 pt-1 border-t border-[#202631]">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] block mb-1">
                      Recent Indexes
                    </span>
                    <div className="space-y-0.5 max-h-32 overflow-y-auto pr-1">
                      {recentRepos.map((r) => (
                        <button
                          key={r.name}
                          type="button"
                          onClick={() => handleSwitchRepo(r.name)}
                          className={`w-full text-left px-2 py-1 rounded text-[11px] font-mono truncate flex items-center justify-between transition-colors ${
                            activeRepo === r.name
                              ? 'bg-[rgba(124,131,255,0.10)] text-[#7C83FF] font-semibold border border-[rgba(124,131,255,0.38)]'
                              : 'text-[#B8BEC9] hover:text-[#F5F7FA] hover:bg-[#11141B]'
                          }`}
                        >
                          <span className="truncate">{r.name}</span>
                          {activeRepo === r.name && <Check className="h-3 w-3 shrink-0" />}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Footer Actions */}
                {activeRepo && (
                  <div className="pt-2 border-t border-[#202631] flex justify-end">
                    <button
                      type="button"
                      onClick={handleClearRepoContext}
                      className="text-[10px] font-mono text-[#858D9A] hover:text-[#F27781] transition-colors"
                    >
                      Clear Context
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 3. Engine Status Indicator */}
          <div className="relative" ref={statusRef}>
            <button
              type="button"
              onClick={() => setStatusOpen((prev) => !prev)}
              className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-mono border border-[#202631] bg-[#090B0F] hover:bg-[#11141B] text-[#B8BEC9] hover:text-[#F5F7FA] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#7C83FF]"
              aria-label={`Engine status: ${engineStatus.label}. Click for diagnostics.`}
              aria-expanded={statusOpen}
              aria-haspopup="true"
              title="Click to view engine health telemetry"
            >
              <span
                className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                  engineStatus.state === 'ready'
                    ? 'bg-[#35D6A3] shadow-[0_0_8px_rgba(53,214,163,0.5)]'
                    : engineStatus.state === 'analyzing'
                      ? 'bg-[#F0B429] animate-pulse'
                      : 'bg-[#F27781]'
                }`}
                aria-hidden="true"
              />
              <span className="hidden xl:inline uppercase">{engineStatus.label}</span>
            </button>

            {statusOpen && (
              <div
                className="absolute right-0 mt-2 w-72 rounded-lg border border-[#2A313C] bg-[#0D1015] p-3 shadow-float z-50 animate-in fade-in zoom-in-95 duration-150 space-y-2.5 font-sans"
                role="dialog"
                aria-label="Engine Health Diagnostics"
              >
                <div className="flex items-center justify-between border-b border-[#202631] pb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#858D9A] flex items-center gap-1.5">
                    <Activity className="h-3 w-3 text-[#7C83FF]" /> Engine Health
                  </span>
                  <span
                    className={`text-[9.5px] font-mono uppercase px-1.5 py-0.5 rounded ${
                      engineStatus.state === 'ready'
                        ? 'bg-[rgba(53,214,163,0.09)] text-[#35D6A3] border border-[rgba(53,214,163,0.34)]'
                        : 'bg-[rgba(242,119,129,0.09)] text-[#F27781] border border-[rgba(242,119,129,0.34)]'
                    }`}
                  >
                    {engineStatus.state}
                  </span>
                </div>

                <div className="space-y-1.5 text-xs font-mono">
                  <div className="flex justify-between text-text-muted">
                    <span className="text-text-subtle">Gateway:</span>
                    <span className="text-text">FastAPI :8001</span>
                  </div>
                  <div className="flex justify-between text-text-muted">
                    <span className="text-text-subtle">LLM Provider:</span>
                    <span className="text-text">{engineStatus.provider || 'gemini-3.1-flash-lite'}</span>
                  </div>
                  <div className="flex justify-between text-text-muted">
                    <span className="text-text-subtle">Vector DB:</span>
                    <span className="text-text">Qdrant (Local / Cloud)</span>
                  </div>
                  {engineStatus.uptimeSeconds !== undefined && (
                    <div className="flex justify-between text-text-muted">
                      <span className="text-text-subtle">Uptime:</span>
                      <span className="text-text">{Math.round(engineStatus.uptimeSeconds)}s</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="hidden sm:block h-3.5 w-px bg-[#202631]" aria-hidden="true" />

          {/* 4. Settings Trigger */}
          <div className="relative" ref={settingsRef}>
            <button
              type="button"
              onClick={() => setSettingsOpen((prev) => !prev)}
              className="flex items-center justify-center h-7 w-7 rounded-md text-[#858D9A] hover:text-[#F5F7FA] hover:bg-[#11141B] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#7C83FF]"
              aria-label="ARIA settings & telemetry"
              title="System Configuration & Diagnostics"
              aria-expanded={settingsOpen}
              aria-haspopup="true"
            >
              <Settings className="h-3.5 w-3.5" aria-hidden="true" />
            </button>

            {settingsOpen && (
              <div
                className="absolute right-0 mt-2 w-80 rounded-lg border border-[#2A313C] bg-[#0D1015] p-3.5 shadow-float z-50 animate-in fade-in zoom-in-95 duration-150 space-y-3 font-sans"
                role="dialog"
                aria-label="System Settings"
              >
                <div className="flex items-center justify-between border-b border-[#202631] pb-2">
                  <span className="text-[10.5px] font-mono uppercase tracking-wider text-[#F5F7FA] font-semibold flex items-center gap-1.5">
                    <Cpu className="h-3.5 w-3.5 text-[#7C83FF]" /> Configuration
                  </span>
                  <button
                    type="button"
                    onClick={() => setSettingsOpen(false)}
                    className="text-[#858D9A] hover:text-[#F5F7FA] text-xs"
                    aria-label="Close settings"
                  >
                    ✕
                  </button>
                </div>

                <div className="space-y-2 text-xs font-mono">
                  <div className="p-2 rounded bg-[#090B0F] border border-[#202631] space-y-1">
                    <span className="text-[10px] text-[#858D9A] uppercase block">Backend Target</span>
                    <span className="text-[11px] text-[#F5F7FA] break-all">{API_BASE_URL || 'http://127.0.0.1:8001'}</span>
                  </div>

                  <div className="p-2 rounded bg-[#090B0F] border border-[#202631] space-y-1">
                    <span className="text-[10px] text-[#858D9A] uppercase block">Inference Topology</span>
                    <span className="text-[11px] text-[#F5F7FA]">Primary: Gemini 3.1 Flash Lite</span>
                    <span className="text-[10px] text-[#858D9A] block">Failover: DeepSeek V4 Flash</span>
                  </div>

                  <div className="p-2 rounded bg-[#090B0F] border border-[#202631] space-y-1">
                    <span className="text-[10px] text-[#858D9A] uppercase block">Embedding Model</span>
                    <span className="text-[11px] text-[#F5F7FA]">BAAI/bge-small-en-v1.5</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-[#202631] flex items-center justify-between">
                  <span className="text-[10px] font-mono text-[#858D9A]">v1.5.0 (v6 engine)</span>
                  <button
                    type="button"
                    onClick={() => {
                      localStorage.clear();
                      window.location.reload();
                    }}
                    className="text-[10px] font-mono text-[#858D9A] hover:text-[#F0B429] transition-colors flex items-center gap-1"
                  >
                    <RotateCcw className="h-2.5 w-2.5" /> Reset Local Caches
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Mobile/Tablet Hamburger Toggle */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            className="lg:hidden flex items-center justify-center h-7 w-7 rounded border border-[#202631] text-[#858D9A] hover:text-[#F5F7FA] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#7C83FF] ml-1"
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X className="h-3.5 w-3.5" /> : <Menu className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* ── Mobile/Tablet Horizontal Navigation Drawer ── */}
      {mobileMenuOpen && (
        <div
          className="lg:hidden border-b border-[#202631] bg-[#0D1015] px-4 py-3 space-y-3 shadow-float animate-in slide-in-from-top-2 duration-150 max-h-[80vh] overflow-y-auto"
          role="navigation"
          aria-label="Mobile Navigation"
        >
          <div>
            <span className="text-[9px] font-mono uppercase tracking-widest text-[#858D9A] font-bold block mb-1.5">
              Primary Workspace
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              {PRIMARY_LINKS.map((link) => {
                const isActive = activeTab === link.id;
                return (
                  <button
                    key={link.id}
                    type="button"
                    onClick={() => handleNavClick(link.id)}
                    className={`text-left px-2.5 py-1.5 rounded text-xs font-sans transition-colors ${
                      isActive
                        ? 'bg-[rgba(124,131,255,0.10)] text-[#F5F7FA] font-medium border border-[rgba(124,131,255,0.38)]'
                        : 'text-[#858D9A] hover:text-[#F5F7FA] hover:bg-[#11141B]'
                    }`}
                  >
                    {link.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="pt-2 border-t border-[#202631]">
            <span className="text-[9px] font-mono uppercase tracking-widest text-[#858D9A] font-bold block mb-1.5">
              Quality &amp; Reliability
            </span>
            <div className="grid grid-cols-1 gap-1">
              {SECONDARY_LINKS.filter(t => t.group === 'Quality & Reliability').map((tool) => {
                const Icon = SECONDARY_ICONS[tool.id] || FileText;
                const isActive = activeTab === tool.id;
                return (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => handleNavClick(tool.id)}
                    className={`text-left px-2.5 py-1.5 rounded text-xs font-sans transition-colors flex items-center justify-between ${
                      isActive
                        ? 'bg-[rgba(124,131,255,0.10)] text-[#F5F7FA] font-medium border border-[rgba(124,131,255,0.38)]'
                        : 'text-[#858D9A] hover:text-[#F5F7FA] hover:bg-[#11141B]'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon className={`h-3.5 w-3.5 ${isActive ? 'text-[#7C83FF]' : 'text-[#858D9A]'}`} />
                      <span>{tool.label}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="pt-2 border-t border-[#202631]">
            <span className="text-[9px] font-mono uppercase tracking-widest text-[#858D9A] font-bold block mb-1.5">
              History &amp; Change
            </span>
            <div className="grid grid-cols-1 gap-1">
              {SECONDARY_LINKS.filter(t => t.group === 'History & Change').map((tool) => {
                const Icon = SECONDARY_ICONS[tool.id] || GitCommit;
                const isActive = activeTab === tool.id;
                return (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => handleNavClick(tool.id)}
                    className={`text-left px-2.5 py-1.5 rounded text-xs font-sans transition-colors flex items-center justify-between ${
                      isActive
                        ? 'bg-[rgba(124,131,255,0.10)] text-[#F5F7FA] font-medium border border-[rgba(124,131,255,0.38)]'
                        : 'text-[#858D9A] hover:text-[#F5F7FA] hover:bg-[#11141B]'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Icon className={`h-3.5 w-3.5 ${isActive ? 'text-[#7C83FF]' : 'text-[#858D9A]'}`} />
                      <span>{tool.label}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="pt-2 border-t border-[#202631] flex items-center justify-between text-xs font-mono text-[#858D9A]">
            <span className="truncate max-w-[200px]">{activeRepo || 'No repo selected'}</span>
            <button
              type="button"
              onClick={() => {
                setMobileMenuOpen(false);
                window.dispatchEvent(new CustomEvent('open-command-palette'));
              }}
              className="text-[#7C83FF] hover:underline inline-flex items-center gap-1"
            >
              <Search className="h-3 w-3" /> Search
            </button>
          </div>
        </div>
      )}
    </header>
  );
};

export default AppNavbar;
