import React, { useMemo, useState } from 'react';
import { ChevronRight, FileCode } from 'lucide-react';
import { FilePath } from '../ui/FilePath';

interface FileTreeProps {
  structure: Record<string, string[]>;
  onFileSelect?: (filePath: string) => void;
}

/**
 * Workspace navigator.
 *
 * A quiet left rail rather than a bordered card: a mono section label, thin
 * guide lines for depth, and a clear selected state. Behaviour is unchanged —
 * folders toggle, files call `onFileSelect` with the same full path as before.
 */
export const FileTree: React.FC<FileTreeProps> = ({ structure, onFileSelect }) => {
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>({
    root: true,
    src: true,
  });
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  const toggleFolder = (folder: string) => {
    setOpenFolders((prev) => ({ ...prev, [folder]: !prev[folder] }));
  };

  const handleFileClick = (path: string) => {
    setSelectedFile(path);
    onFileSelect?.(path);
  };

  const directories = useMemo(
    () =>
      Object.keys(structure).sort((a, b) => {
        if (a === 'root' || a === '.') return -1;
        if (b === 'root' || b === '.') return 1;
        return a.localeCompare(b);
      }),
    [structure]
  );

  const fileCount = useMemo(
    () => Object.values(structure).reduce((sum, files) => sum + files.length, 0),
    [structure]
  );

  return (
    <nav aria-label="Workspace files" className="min-w-0">
      <div className="flex items-baseline justify-between gap-3 pb-3 hair-b">
        <span className="mono-label">WORKSPACE</span>
        <span className="mono-detail shrink-0 tabular-nums" style={{ fontSize: 10 }}>
          {fileCount} {fileCount === 1 ? 'FILE' : 'FILES'}
        </span>
      </div>

      <div className="mt-2 max-h-[32rem] overflow-y-auto overflow-x-hidden pr-1">
        {directories.map((dir) => {
          const files = structure[dir] || [];
          const isRoot = dir === 'root' || dir === '.';
          const isOpen = openFolders[dir];

          return (
            <div key={dir} className="min-w-0">
              {!isRoot && (
                <button
                  type="button"
                  onClick={() => toggleFolder(dir)}
                  aria-expanded={isOpen}
                  className="tree-row group w-full flex items-center gap-2 py-2.5 pr-2 text-left min-w-0
                             focus-visible:outline-none focus-visible:shadow-ring"
                >
                  <ChevronRight
                    className={`h-3 w-3 shrink-0 text-text-subtle transition-transform duration-200 ${
                      isOpen ? 'rotate-90' : ''
                    }`}
                    aria-hidden="true"
                  />
                  {/* Directories carry more weight than the files inside them */}
                  <span
                    className={`font-mono text-[11px] font-semibold uppercase tracking-[0.06em] truncate ${
                      isOpen ? 'text-text' : 'text-text-muted group-hover:text-text'
                    }`}
                  >
                    {dir}
                  </span>
                  <span className="mono-detail ml-auto shrink-0 tabular-nums" style={{ fontSize: 9 }}>
                    {files.length}
                  </span>
                </button>
              )}

              {(isRoot || isOpen) && (
                <div className={isRoot ? 'min-w-0' : 'tree-guide min-w-0'}>
                  {files.map((file) => {
                    const fullPath = isRoot ? file : `${dir}/${file}`;
                    const isSelected = selectedFile === fullPath;

                    return (
                      <button
                        key={file}
                        type="button"
                        onClick={() => handleFileClick(fullPath)}
                        aria-pressed={isSelected}
                        title={fullPath}
                        data-selected={isSelected ? 'true' : 'false'}
                        aria-current={isSelected ? 'true' : undefined}
                        className="tree-row group w-full flex items-center gap-2 py-2 pl-3 pr-2
                                   text-left min-w-0 focus-visible:outline-none focus-visible:shadow-ring"
                      >
                        <FileCode
                          className={`h-3 w-3 shrink-0 ${
                            isSelected ? 'text-primary' : 'text-text-subtle'
                          }`}
                          aria-hidden="true"
                        />
                        {/* Shared file language — the row shows the leaf name */}
                        <FilePath
                          path={file}
                          size="sm"
                          tone={isSelected ? 'primary' : 'secondary'}
                          active={isSelected}
                          className="truncate"
                        />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </nav>
  );
};

export default FileTree;
