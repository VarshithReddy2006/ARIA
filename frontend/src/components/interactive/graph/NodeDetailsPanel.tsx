import React, { useState, useEffect } from 'react';
import {
  X, Network, ArrowRight, ArrowLeft, ArrowLeftRight, Code2, ShieldAlert,
  GitCommit, Layers, Workflow, FileText, Check, Copy, ExternalLink, Sparkles, BookOpen, Zap, Lightbulb
} from 'lucide-react';
import { CATEGORY_COLORS, CATEGORY_LABELS } from './types';
import type { GraphNode, ArchitectureNodeDetails } from './types';
import { MiniDependencyPreviewTree } from './MiniDependencyPreviewTree';
import { apiUrl } from '../../../lib/api';

interface NodeDetailsPanelProps {
  node: GraphNode;
  repoName: string;
  onClose: () => void;
  onExpand: (nodeId: string) => void;
  onTraceForward: (nodeId: string) => void;
  onTraceBackward: (nodeId: string) => void;
  onTraceBoth: (nodeId: string) => void;
  onOpenDiagramModal: (nodeId: string) => void;
  onSelectNode: (nodeId: string) => void;
  className?: string;
}

export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({
  node,
  repoName,
  onClose,
  onExpand,
  onTraceForward,
  onTraceBackward,
  onTraceBoth,
  onOpenDiagramModal,
  onSelectNode,
  className,
}) => {
  const [tab, setTab] = useState<'overview' | 'architecture' | 'metrics' | 'deps' | 'git' | 'guidance' | 'impact' | 'recommendations'>('overview');
  const [details, setDetails] = useState<ArchitectureNodeDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const fetchNodeDetails = async () => {
      setLoading(true);
      const [owner, name] = repoName.split('/');
      try {
        const res = await fetch(apiUrl(`/api/v1/architecture/${owner}/${name}/node-details/${encodeURIComponent(node.id)}`));
        if (res.ok) {
          const data = await res.json();
          setDetails(data);
        }
      } catch {
        /* fallback to defaults */
      } finally {
        setLoading(false);
      }
    };
    fetchNodeDetails();
  }, [repoName, node.id]);

  const handleCopyPath = () => {
    navigator.clipboard.writeText(node.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleVSCodeOpen = () => {
    window.open(`vscode://file/${node.id}`);
  };

  const color = CATEGORY_COLORS[node.category] ?? CATEGORY_COLORS.regular;
  const categoryLabel = CATEGORY_LABELS[node.category] ?? node.category;
  const fileName = node.id.split('/').pop() ?? node.id;
  const dirPath = node.id.includes('/') ? node.id.substring(0, node.id.lastIndexOf('/')) : '';

  const positionClass = className ?? 'fixed inset-x-0 bottom-0 max-h-[80vh] md:absolute md:right-0 md:top-0 md:bottom-0 md:max-h-none md:w-[410px]';

  /** Renders a backend-provided value, or an unavailable marker when it is absent. */
  const renderValue = (value: string | number | null | undefined, suffix = ''): string =>
    value === null || value === undefined || value === '' ? '—' : `${value}${suffix}`;

  const UNAVAILABLE = (
    <span className="text-[10px] text-text-muted italic">Unavailable</span>
  );

  return (
    <div
      role="dialog"
      aria-label={`Node details: ${fileName}`}
      className={`${positionClass} bg-zinc-950 border-t md:border-t-0 md:border-l border-border flex flex-col z-20 shadow-2xl font-mono`}
    >
      {/* Header */}
      <div className="flex items-start justify-between px-4 pt-4 pb-3 border-b border-border bg-canvas/30 shrink-0 select-none">
        <div className="space-y-0.5 min-w-0 pr-2">
          <span className="text-[9px] font-bold text-primary uppercase tracking-wider block flex items-center gap-1">
            <Sparkles className="h-3 w-3 text-primary" /> Architecture Inspector v2
          </span>
          <h3 className="text-xs font-semibold text-text truncate block" title={node.id}>
            {fileName}
          </h3>
          {dirPath && (
            <span className="text-[9px] text-text-muted truncate block" title={dirPath}>
              {dirPath}/
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-text-muted hover:text-text rounded p-1"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 8 Inspector Subtabs */}
      <div className="flex border-b border-border bg-canvas/20 text-[9px] font-bold uppercase select-none overflow-x-auto">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'architecture', label: 'Patterns' },
          { id: 'metrics', label: 'Metrics' },
          { id: 'deps', label: 'Tree' },
          { id: 'git', label: 'Git' },
          { id: 'guidance', label: 'Guidance' },
          { id: 'impact', label: 'Impact' },
          { id: 'recommendations', label: 'Suggest' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as any)}
            className={`flex-1 py-2 px-1 text-center border-b-2 transition-all shrink-0 ${
              tab === t.id
                ? 'border-primary text-primary bg-primary/5 font-extrabold'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content Body */}
      <div className="px-4 py-3 space-y-4 text-xs flex-grow overflow-y-auto">
        {tab === 'overview' && (
          <div className="space-y-3">
            {/* Business Responsibility */}
            <div className="p-3 bg-canvas/40 border border-primary/20 rounded-lg space-y-1">
              <span className="text-[9px] font-bold text-primary uppercase tracking-wider block">
                Business Responsibility
              </span>
              <p className="text-[11px] text-text leading-relaxed">
                {details?.business_responsibility || UNAVAILABLE}
              </p>
            </div>

            {/* Category & Layer Badges */}
            <div className="flex flex-wrap gap-2">
              <span
                className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase px-2 py-0.5 rounded border"
                style={{ color, borderColor: `${color}40`, backgroundColor: `${color}15` }}
              >
                <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                {categoryLabel}
              </span>
              {details?.layer && (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-400">
                  <Layers className="h-3 w-3" /> {details.layer} Layer
                </span>
              )}
            </div>

            {/* Quick Actions */}
            <div className="space-y-1.5 pt-2 border-t border-border/40">
              <span className="text-[9px] text-text-muted uppercase font-bold tracking-wider block mb-1">
                Smart Actions
              </span>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  onClick={handleVSCodeOpen}
                  className="flex items-center gap-1.5 bg-canvas border border-border hover:border-primary/50 px-2.5 py-1.5 rounded text-[10px] font-semibold text-text"
                >
                  <ExternalLink className="h-3 w-3 text-primary" /> VS Code
                </button>
                <button
                  onClick={handleCopyPath}
                  className="flex items-center gap-1.5 bg-canvas border border-border hover:border-primary/50 px-2.5 py-1.5 rounded text-[10px] font-semibold text-text"
                >
                  {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-text-muted" />} Copy Path
                </button>
              </div>
              <button
                onClick={() => onOpenDiagramModal(node.id)}
                className="w-full flex items-center justify-center gap-2 bg-primary/10 hover:bg-primary/20 border border-primary/30 text-primary font-bold px-3 py-2 rounded text-[11px] transition-all"
              >
                <Workflow className="h-3.5 w-3.5" /> Generate Diagrams & ADR
              </button>
            </div>

            {/* Graph Traversal */}
            <div className="space-y-1.5 pt-2 border-t border-border/40">
              <span className="text-[9px] text-text-muted uppercase font-bold tracking-wider block mb-1">
                Graph Traversal
              </span>
              <div className="space-y-1">
                <button
                  onClick={() => onExpand(node.id)}
                  className="w-full flex items-center gap-2 bg-canvas border border-border hover:border-primary/50 px-3 py-1.5 rounded text-[10px] text-text"
                >
                  <Network className="h-3.5 w-3.5 text-primary" /> Expand Neighbours
                </button>
                <button
                  onClick={() => onTraceForward(node.id)}
                  className="w-full flex items-center gap-2 bg-canvas border border-border hover:border-blue-500/50 px-3 py-1.5 rounded text-[10px] text-text"
                >
                  <ArrowRight className="h-3.5 w-3.5 text-blue-400" /> Trace Dependencies →
                </button>
                <button
                  onClick={() => onTraceBackward(node.id)}
                  className="w-full flex items-center gap-2 bg-canvas border border-border hover:border-emerald-500/50 px-3 py-1.5 rounded text-[10px] text-text"
                >
                  <ArrowLeft className="h-3.5 w-3.5 text-emerald-400" /> ← Trace Consumers
                </button>
              </div>
            </div>
          </div>
        )}

        {tab === 'architecture' && (
          <div className="space-y-3">
            <div>
              <span className="text-[9px] text-text-muted uppercase block mb-1 font-bold">Architectural Layer</span>
              <div className="p-2.5 bg-canvas border border-border rounded-lg text-text font-bold text-xs flex items-center gap-2">
                <Layers className="h-4 w-4 text-primary" />
                <span>{details?.layer ? `${details.layer} Layer` : UNAVAILABLE}</span>
              </div>
            </div>

            <div>
              <span className="text-[9px] text-text-muted uppercase block mb-1 font-bold">Detected Design Patterns</span>
              <div className="flex flex-wrap gap-1.5">
                {details?.patterns?.length
                  ? details.patterns.map((p) => (
                      <span key={p} className="text-[10px] font-bold bg-primary/10 border border-primary/20 text-primary px-2 py-0.5 rounded">
                        {p}
                      </span>
                    ))
                  : UNAVAILABLE}
              </div>
            </div>

            {/* System Position Metrics */}
            <div className="border-t border-border/40 pt-2 space-y-2">
              <span className="text-[9px] text-text-muted uppercase block font-bold">System Position Metrics</span>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="border border-border/60 bg-canvas/30 p-2 rounded">
                  <span className="text-text-muted block text-[8px] uppercase">Entry Distance</span>
                  <span className="text-text font-bold text-xs mt-0.5 block">
                    {renderValue(details?.system_position?.distance_from_entry_point, ' hops')}
                  </span>
                </div>
                <div className="border border-border/60 bg-canvas/30 p-2 rounded">
                  <span className="text-text-muted block text-[8px] uppercase">Infra Distance</span>
                  <span className="text-text font-bold text-xs mt-0.5 block">
                    {renderValue(details?.system_position?.distance_from_infrastructure, ' hops')}
                  </span>
                </div>
              </div>
            </div>

            {/* Suggested Reading Sequence */}
            <div className="border-t border-border/40 pt-2 space-y-1.5">
              <span className="text-[9px] text-text-muted uppercase block font-bold flex items-center gap-1">
                <BookOpen className="h-3 w-3 text-primary" /> Suggested Reading Sequence
              </span>
              <div className="space-y-1 bg-canvas/40 border border-border/50 p-2 rounded text-[10px] text-text-muted">
                {details?.suggested_reading_order?.length
                  ? details.suggested_reading_order.map((step, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <span className="text-primary font-bold">{step}</span>
                      </div>
                    ))
                  : UNAVAILABLE}
              </div>
            </div>
          </div>
        )}

        {tab === 'metrics' && (
          <div className="space-y-3">
            <span className="text-[9px] text-text-muted uppercase block font-bold">Advanced Metrics Suite</span>
            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Instability (I)</span>
                <span className="text-primary text-sm font-bold block mt-0.5">{renderValue(details?.metrics?.instability)}</span>
              </div>
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Main Seq Dist (D)</span>
                <span className="text-text text-sm font-bold block mt-0.5">{renderValue(details?.metrics?.distance_main_sequence)}</span>
              </div>
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Maintainability (MI)</span>
                <span className="text-emerald-400 text-sm font-bold block mt-0.5">
                  {renderValue(details?.metrics?.maintainability_index, '/100')}
                </span>
              </div>
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Complexity v(G)</span>
                <span className="text-amber-400 text-sm font-bold block mt-0.5">{renderValue(details?.metrics?.cyclomatic_complexity)}</span>
              </div>
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Afferent (Ca)</span>
                <span className="text-text text-sm font-bold block mt-0.5">{renderValue(details?.metrics?.afferent_coupling)}</span>
              </div>
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Efferent (Ce)</span>
                <span className="text-text text-sm font-bold block mt-0.5">{renderValue(details?.metrics?.efferent_coupling)}</span>
              </div>
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Lines of Code</span>
                <span className="text-text text-sm font-bold block mt-0.5">{renderValue(details?.metrics?.lines_of_code)}</span>
              </div>
              <div className="border border-border bg-canvas/30 rounded p-2">
                <span className="text-[8px] text-text-muted uppercase block">Comment Density</span>
                <span className="text-text text-sm font-bold block mt-0.5">{renderValue(details?.metrics?.comment_density, '%')}</span>
              </div>
            </div>
          </div>
        )}

        {tab === 'deps' && (
          <MiniDependencyPreviewTree
            nodeId={node.id}
            dependsOn={[]}
            importedBy={[]}
            onSelectNode={onSelectNode}
          />
        )}

        {tab === 'git' && (
          <div className="space-y-3">
            <span className="text-[9px] text-text-muted uppercase block font-bold">Git History & Churn</span>
            <div className="space-y-2 text-[10px] bg-canvas border border-border p-3 rounded-lg">
              <div className="flex justify-between">
                <span className="text-text-muted">First Created:</span>
                <span className="text-text font-bold">{renderValue(details?.git_metrics?.created)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Last Modified:</span>
                <span className="text-text font-bold">{renderValue(details?.git_metrics?.last_modified)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Commit Count:</span>
                <span className="text-primary font-bold">{renderValue(details?.git_metrics?.commit_count, ' commits')}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Contributors:</span>
                <span className="text-text font-bold">{renderValue(details?.git_metrics?.contributors_count, ' authors')}</span>
              </div>
            </div>

            {details?.git_metrics?.latest_commit_message && (
              <div className="border-t border-border/40 pt-2 space-y-1">
                <span className="text-[9px] text-text-muted uppercase block font-bold">Latest Commit</span>
                <p className="text-[10px] text-text-subtle italic bg-canvas/40 p-2 rounded border border-border/40">
                  "{details.git_metrics.latest_commit_message}"
                </p>
              </div>
            )}
          </div>
        )}

        {tab === 'guidance' && (
          <div className="space-y-3 text-[10px]">
            <span className="text-[9px] text-text-muted uppercase block font-bold">Developer Modifications</span>
            <div className="text-text-muted bg-canvas p-2.5 rounded border border-border">
              {details?.developer_guidance?.common_modification_reasons?.length ? (
                <ul className="list-disc list-inside space-y-1">
                  {details.developer_guidance.common_modification_reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              ) : (
                UNAVAILABLE
              )}
            </div>

            <span className="text-[9px] text-text-muted uppercase block font-bold pt-1">Risk Indicators</span>
            <div className="space-y-1">
              {details?.risk_indicators?.length
                ? details.risk_indicators.map((rk, idx) => (
                    <div key={idx} className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400 font-bold flex items-center gap-2">
                      <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
                      <span>{rk.label}: {rk.description}</span>
                    </div>
                  ))
                : UNAVAILABLE}
            </div>
          </div>
        )}

        {tab === 'impact' && (
          <div className="space-y-3 text-[10px]">
            <div className="p-3 bg-rose-950/20 border border-rose-500/30 rounded-lg space-y-1">
              <span className="text-[9px] font-bold text-rose-400 uppercase tracking-wider block flex items-center gap-1">
                <Zap className="h-3.5 w-3.5" /> Blast Radius Assessment
              </span>
              <div className="flex justify-between font-bold text-xs text-text pt-1">
                <span>Risk Level: <span className="text-rose-400">{renderValue(details?.impact?.risk_level)}</span></span>
                <span>Affected Files: <span className="text-primary">{renderValue(details?.impact?.total_affected_files)}</span></span>
              </div>
            </div>

            <div className="space-y-1.5">
              <span className="text-[9px] text-text-muted uppercase font-bold">Affected Entry Points & APIs</span>
              <div className="p-2 bg-canvas border border-border rounded space-y-1 font-mono text-[10px]">
                {details?.impact?.affected_apis?.length
                  ? details.impact.affected_apis.map((api, i) => (
                      <div key={i} className="text-emerald-400 font-semibold truncate">{api}</div>
                    ))
                  : UNAVAILABLE}
              </div>
            </div>
          </div>
        )}

        {tab === 'recommendations' && (
          <div className="space-y-3 text-[10px]">
            <span className="text-[9px] text-text-muted uppercase block font-bold flex items-center gap-1">
              <Lightbulb className="h-3.5 w-3.5 text-amber-400" /> Architecture Suggestions
            </span>

            {details?.recommendations?.length
              ? details.recommendations.map((rec, i) => (
                  <div key={i} className="p-3 bg-canvas border border-border/80 rounded-lg space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-text text-xs">{rec.title}</span>
                      <span className="px-1.5 py-0.5 rounded bg-primary/20 text-primary text-[9px] font-bold">{rec.priority}</span>
                    </div>
                    <p className="text-text-muted text-[10px] leading-relaxed">{rec.reason}</p>
                    <div className="text-[9px] text-emerald-400 font-bold border-t border-border/40 pt-1">
                      💡 {rec.suggestion}
                    </div>
                  </div>
                ))
              : UNAVAILABLE}
          </div>
        )}
      </div>
    </div>
  );
};
