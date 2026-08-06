import React, { useState, useEffect } from 'react';
import { X, Copy, Check, FileText, Code2, Network, Workflow } from 'lucide-react';
import { apiUrl } from '../../../lib/api';

interface DiagramModalProps {
  repoName: string;
  nodeId: string;
  onClose: () => void;
}

export const ArchitectureDiagramModal: React.FC<DiagramModalProps> = ({
  repoName,
  nodeId,
  onClose,
}) => {
  const [diagramType, setDiagramType] = useState<'mermaid' | 'plantuml' | 'adr' | 'sequence'>('mermaid');
  const [code, setCode] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    const fetchDiagram = async () => {
      setLoading(true);
      try {
        const res = await fetch(apiUrl('/api/v1/architecture/generate-diagram'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            repo: repoName,
            node_id: nodeId,
            diagram_type: diagramType,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          setCode(data.code || '');
        }
      } catch {
        setCode('// Failed to generate diagram syntax.');
      } finally {
        setLoading(false);
      }
    };
    fetchDiagram();
  }, [repoName, nodeId, diagramType]);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fileName = nodeId.split('/').pop() || nodeId;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-950 border border-border rounded-xl w-full max-w-3xl h-[650px] flex flex-col shadow-2xl overflow-hidden font-mono">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-canvas/40">
          <div className="flex items-center gap-2">
            <Workflow className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-bold text-text truncate">
              Architecture Intelligence Exporter: <span className="text-primary">{fileName}</span>
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text rounded p-1"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Format Selector Tabs */}
        <div className="flex border-b border-border bg-canvas/20 text-xs">
          {[
            { id: 'mermaid', label: 'Mermaid Diagram', icon: <Network className="h-3.5 w-3.5" /> },
            { id: 'plantuml', label: 'PlantUML Syntax', icon: <Code2 className="h-3.5 w-3.5" /> },
            { id: 'sequence', label: 'Sequence Flow', icon: <Workflow className="h-3.5 w-3.5" /> },
            { id: 'adr', label: 'ADR Document', icon: <FileText className="h-3.5 w-3.5" /> },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setDiagramType(t.id as any)}
              className={`flex-1 flex items-center justify-center gap-2 py-3 border-b-2 font-bold transition-all ${
                diagramType === t.id
                  ? 'border-primary text-primary bg-primary/5'
                  : 'border-transparent text-text-muted hover:text-text'
              }`}
            >
              {t.icon}
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        {/* Code Content Viewport */}
        <div className="flex-1 p-5 relative overflow-y-auto bg-canvas/10">
          {loading ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-text-muted gap-2">
              <div className="h-6 w-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
              <span className="text-xs">Generating architecture diagram...</span>
            </div>
          ) : (
            <pre className="text-xs font-mono text-emerald-400 leading-relaxed whitespace-pre-wrap select-all bg-canvas border border-border/60 p-4 rounded-lg">
              {code}
            </pre>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-border bg-canvas/40 flex justify-between items-center">
          <span className="text-[10px] text-text-muted">
            Copy syntax to embed in GitHub README, Notion, or Mermaid live editor.
          </span>
          <button
            onClick={handleCopy}
            disabled={loading}
            className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-canvas font-bold text-xs px-4 py-2 rounded transition-all disabled:opacity-50"
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            <span>{copied ? 'Copied!' : 'Copy Code'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
