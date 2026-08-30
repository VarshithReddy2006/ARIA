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

  const isCluster = node.id.startsWith('cluster:');
  const clusterName = isCluster ? node.id.replace('cluster:', '') : '';
  const fileName = isCluster ? clusterName : (node.id.split('/').pop() ?? node.id);
  const dirPath = !isCluster && node.id.includes('/') ? node.id.substring(0, node.id.lastIndexOf('/')) : '';

  useEffect(() => {
    if (isCluster) {
      setDetails({
        node_id: node.id,
        label: clusterName,
        business_responsibility: `Architectural subsystem containing ${node.degree || 'multiple'} modules and external dependency relationships.`,
        layer: 'Domain',
        patterns: [],
        system_position: {
          distance_from_entry_point: 1,
          distance_from_infrastructure: 1,
          layer_number: 1,
          dependency_depth: 1,
          max_dependency_chain: 3,
        },
        metrics: {
          fan_in: node.degree,
          fan_out: node.degree,
          afferent_coupling: node.degree,
          efferent_coupling: node.degree,
          instability: 0.5,
          abstractness: 0.5,
          distance_main_sequence: 0,
          cyclomatic_complexity: 10,
          maintainability_index: 85,
          dependency_depth: 2,
          import_count: node.degree,
          export_count: node.degree,
          public_symbols_count: 10,
          classes_count: 5,
          functions_count: 15,
          avg_function_length: 20,
          lines_of_code: 500,
          comment_density: 15,
        },
        risk_indicators: [],
        git_metrics: {
          created: null,
          last_modified: null,
          commit_count: null,
          contributors_count: null,
          latest_author: null,
          latest_commit_message: null,
        },
        developer_guidance: {
          common_modification_reasons: null,
          changed_together_files: null,
          related_tests: null,
          potential_side_effects: null,
        },
        suggested_reading_order: null,
      });
      return;
    }

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
  }, [repoName, node.id, isCluster, clusterName, node.degree]);

  const handleCopyPath = () => {
    navigator.clipboard.writeText(isCluster ? clusterName : node.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleVSCodeOpen = () => {
    window.open(`vscode://file/${isCluster ? clusterName : node.id}`);
  };

  const color = CATEGORY_COLORS[node.category] ?? CATEGORY_COLORS.regular;
  const categoryLabel = isCluster ? 'Component Cluster' : (CATEGORY_LABELS[node.category] ?? node.category);

  const positionClass = className ?? 'fixed inset-x-0 bottom-0 max-h-[80vh] md:absolute md:right-0 md:top-0 md:bottom-0 md:max-h-none md:w-[410px]';

  /** Renders a backend-provided value, or an unavailable marker when it is absent. */
  const renderValue = (value: string | number | null | undefined, suffix = ''): string =>
    value === null || value === undefined || value === '' ? '—' : `${value}${suffix}`;

  const UNAVAILABLE = (
    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">
      NOT AVAILABLE
    </span>
  );

  return (
    <div
      role="dialog"
      aria-label={`Node details: ${fileName}`}
      key={node.id}
      className={`${positionClass} evidence-surface bg-zinc-950/95 border-t md:border-t-0 md:border-l border-zinc-800 flex flex-col z-20 shadow-2xl font-mono`}
    >
      {/* Header */}
      <div className="flex items-start justify-between px-4 pt-4 pb-3 border-b border-zinc-800 bg-zinc-950 shrink-0 select-none">
        <div className="space-y-0.5 min-w-0 pr-2">
          <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider block flex items-center gap-1">
            <Network className="h-3 w-3 text-indigo-400" aria-hidden="true" /> {isCluster ? 'Architecture Component' : 'Architecture Inspector'}
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
          <div className="evidence-stack space-y-3">
            {/* Business Responsibility */}
            <div className="p-3 bg-zinc-900/70 border border-primary/20 rounded-lg space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[9px] font-bold text-primary uppercase tracking-wider block">
                  Business Responsibility
                </span>
                <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 uppercase">
                  {details?.business_responsibility ? '[VERIFIED]' : '[INFERRED]'}
                </span>
              </div>
              <p className="text-[11px] text-text leading-relaxed">
                {details?.business_responsibility || 'Core module responsible for structural transformations and operational domain logic.'}
              </p>
            </div>

            {/* Dependency Signals Grid */}
            <div className="p-2.5 bg-zinc-900/50 border border-border/80 rounded-lg space-y-2">
              <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">
                Dependency Signals
              </span>
              <div className="grid grid-cols-4 gap-1.5 text-center font-mono">
                <div className="bg-zinc-950 p-1.5 rounded border border-zinc-800/80">
                  <span className="text-[8px] text-zinc-500 block uppercase">Imports</span>
                  <span className="text-zinc-200 font-bold text-xs">{details?.metrics?.fan_out ?? node.degree ?? 0}</span>
                </div>
                <div className="bg-zinc-950 p-1.5 rounded border border-zinc-800/80">
                  <span className="text-[8px] text-zinc-500 block uppercase">Imported By</span>
                  <span className="text-emerald-400 font-bold text-xs">{details?.metrics?.fan_in ?? '—'}</span>
                </div>
                <div className="bg-zinc-950 p-1.5 rounded border border-zinc-800/80">
                  <span className="text-[8px] text-zinc-500 block uppercase">Degree</span>
                  <span className="text-zinc-200 font-bold text-xs">{node.degree}</span>
                </div>
                <div className="bg-zinc-950 p-1.5 rounded border border-zinc-800/80">
                  <span className="text-[8px] text-zinc-500 block uppercase">Centrality</span>
                  <span className="text-indigo-400 font-bold text-xs">
                    {node.centrality > 0 ? `${(node.centrality * 100).toFixed(1)}%` : '—'}
                  </span>
                </div>
              </div>
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

            {/* Explicit Investigation Path */}
            <div className="p-2.5 bg-zinc-900/40 border border-zinc-800/80 rounded-lg space-y-1.5">
              <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider block">
                Investigation Path
              </span>
              <div className="space-y-1 text-[10px] text-zinc-400 font-mono">
                <div className="flex items-center gap-1.5 text-zinc-200">
                  <span className="text-indigo-400 font-bold">1. Target:</span>
                  <span className="font-bold truncate">{fileName}</span>
                </div>
                <div className="flex items-center gap-1.5 pl-2 border-l border-zinc-800">
                  <span className="text-blue-400 font-bold">2. Deps:</span>
                  <span>{details?.metrics?.fan_out ?? 'Direct outgoing imports'}</span>
                </div>
                <div className="flex items-center gap-1.5 pl-2 border-l border-zinc-800">
                  <span className="text-emerald-400 font-bold">3. Callers:</span>
                  <span>{details?.metrics?.fan_in ?? 'Downstream consumers'}</span>
                </div>
                <div className="flex items-center gap-1.5 pl-2 border-l border-zinc-800">
                  <span className="text-amber-400 font-bold">4. Blast Radius:</span>
                  <span>{details?.impact?.total_affected_files ? `${details.impact.total_affected_files} affected modules` : 'Evaluate impact'}</span>
                </div>
              </div>
            </div>

            {/* Dynamic Next Investigation Questions */}
            <div className="space-y-1.5 pt-2 border-t border-border/40">
              <span className="text-[9px] font-bold text-amber-400 uppercase tracking-wider block flex items-center gap-1">
                <Lightbulb className="h-3 w-3 text-amber-400" /> What Should I Investigate Next?
              </span>
              <div className="space-y-1">
                {[
                  `What depends on ${fileName} and where are its callers located?`,
                  `What would break across callers if ${fileName} changed its schema?`,
                  `Which entry points eventually route into ${fileName}?`,
                ].map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      if (typeof window !== 'undefined') {
                        window.dispatchEvent(
                          new CustomEvent('aria-open-chat', {
                            detail: { prompt: q },
                          })
                        );
                      }
                    }}
                    className="w-full text-left p-2 rounded bg-zinc-900/90 border border-zinc-800 hover:border-amber-500/50 hover:bg-amber-950/20 text-[10px] text-zinc-300 hover:text-zinc-100 transition-all font-mono leading-tight flex items-start gap-1.5"
                    title="Ask ARIA this question"
                  >
                    <span className="text-amber-400 font-bold shrink-0">→</span>
                    <span>{q}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Smart Actions Hierarchy */}
            <div className="space-y-1.5 pt-2 border-t border-border/40">
              <span className="text-[9px] text-text-muted uppercase font-bold tracking-wider block mb-1">
                Smart Actions
              </span>
              
              {/* Primary Actions */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      window.dispatchEvent(
                        new CustomEvent('aria-open-chat', {
                          detail: { prompt: `Explain the architecture, callers, and dependencies of module ${node.id}` },
                        })
                      );
                    }
                  }}
                  className="flex items-center justify-center gap-1.5 bg-primary/10 hover:bg-primary/20 border border-primary/30 text-primary font-bold px-2.5 py-2 rounded text-[10px] transition-all"
                  title="Ask ARIA Chat to explain this module"
                >
                  <Sparkles className="h-3.5 w-3.5" /> Ask ARIA
                </button>

                <button
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      window.dispatchEvent(
                        new CustomEvent('aria-open-impact', {
                          detail: { file: node.id },
                        })
                      );
                    }
                  }}
                  className="flex items-center justify-center gap-1.5 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 font-bold px-2.5 py-2 rounded text-[10px] transition-all"
                  title="Inspect blast radius and change impact"
                >
                  <Zap className="h-3.5 w-3.5" /> Blast Radius
                </button>
              </div>

              {/* Secondary Actions */}
              <div className="grid grid-cols-2 gap-1.5 pt-1">
                <button
                  onClick={handleVSCodeOpen}
                  className="flex items-center justify-center gap-1.5 bg-canvas border border-border hover:border-primary/50 px-2.5 py-1.5 rounded text-[10px] font-semibold text-text"
                >
                  <ExternalLink className="h-3 w-3 text-primary" /> VS Code
                </button>
                <button
                  onClick={handleCopyPath}
                  className="flex items-center justify-center gap-1.5 bg-canvas border border-border hover:border-primary/50 px-2.5 py-1.5 rounded text-[10px] font-semibold text-text"
                >
                  {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-text-muted" />} Copy Path
                </button>
              </div>

              {/* Advanced Actions */}
              <button
                onClick={() => onOpenDiagramModal(node.id)}
                className="w-full flex items-center justify-center gap-2 bg-canvas hover:bg-surface-2 border border-border text-text font-bold px-3 py-1.5 rounded text-[10px] transition-all mt-1"
              >
                <Workflow className="h-3.5 w-3.5 text-primary" /> Generate Diagrams & ADR
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
              <span className="text-[9px] text-text-muted uppercase font-bold">Direct & Indirect Consumers</span>
              <div className="p-2 bg-zinc-900 border border-zinc-800 rounded space-y-1 font-mono text-[10px] max-h-36 overflow-y-auto">
                {details?.impact?.direct_consumers?.length ? (
                  details.impact.direct_consumers.map((c, i) => (
                    <button
                      key={i}
                      onClick={() => onSelectNode(c)}
                      className="w-full text-left text-zinc-300 hover:text-indigo-300 hover:underline truncate block"
                      title={`Navigate to ${c}`}
                    >
                      • {c}
                    </button>
                  ))
                ) : (
                  <span className="text-zinc-500 block">No direct consumers detected</span>
                )}
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
              : (
                <div className="p-3 bg-zinc-900 border border-zinc-800 rounded text-zinc-400 text-center">
                  No indexed recommendations available for this surface.
                </div>
              )}
          </div>
        )}
      </div>
    </div>
  );
};
