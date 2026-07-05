/**
 * CodeLens provider — renders action links above every function and class
 * definition in the active file.
 *
 * Each lens triggers one of the registered extension commands with pre-filled
 * arguments derived from the current file's symbol index.
 */

import * as vscode from 'vscode';
import { client, Symbol as RepoSymbol } from '../api';
import { DocumentLruCache } from '../utils/lruCache';
import { StateService } from '../utils/stateService';

// Bounded LRU Cache (max 50 documents)
export const codeLensCache = new DocumentLruCache<RepoSymbol[]>(50);

function getActiveRepo(): string {
  return StateService.getActiveRepository();
}

function repoToOwnerRepo(id: string): [string, string] | null {
  const p = id.split('/');
  return p.length === 2 && p[0] && p[1] ? [p[0], p[1]] : null;
}

function getRelativePath(document: vscode.TextDocument): string {
  const ws = vscode.workspace.getWorkspaceFolder(document.uri);
  return ws ? vscode.workspace.asRelativePath(document.uri, false) : document.uri.fsPath;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export class RepoIntelligenceCodeLensProvider
  implements vscode.CodeLensProvider, vscode.Disposable
{
  private readonly _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

  private readonly _configWatcher: vscode.Disposable;

  constructor() {
    this._configWatcher = vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('repoIntelligence')) {
        this._onDidChangeCodeLenses.fire();
      }
    });
  }

  dispose(): void {
    this._configWatcher.dispose();
    this._onDidChangeCodeLenses.dispose();
  }

  async provideCodeLenses(
    document: vscode.TextDocument,
    token: vscode.CancellationToken
  ): Promise<vscode.CodeLens[]> {
    if (!vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('codeLens.enabled')) {
      return [];
    }

    const repoId = getActiveRepo();
    if (!repoId) {
      return [];
    }
    const ownerRepo = repoToOwnerRepo(repoId);
    if (!ownerRepo) {
      return [];
    }
    const [owner, repo] = ownerRepo;
    const filePath = getRelativePath(document);

    // Invalidate stale cache
    const cached = codeLensCache.get(document.uri.toString());
    let symbols: RepoSymbol[];
    if (cached && cached.version === document.version) {
      symbols = cached.value;
    } else {
      try {
        const result = await client.getFileSymbols(owner, repo, filePath);
        symbols = result.symbols;
        codeLensCache.set(document.uri.toString(), {
          value: symbols,
          version: document.version,
        });
      } catch {
        return [];
      }
    }

    if (token.isCancellationRequested) {
      return [];
    }

    const lenses: vscode.CodeLens[] = [];

    for (const symbol of symbols) {
      if (
        symbol.symbol_type !== 'function' &&
        symbol.symbol_type !== 'method' &&
        symbol.symbol_type !== 'class'
      ) {
        continue;
      }

      const lineIndex = Math.max(0, symbol.line_number - 1);
      const range = new vscode.Range(lineIndex, 0, lineIndex, 0);
      const functionId = `${filePath}::${symbol.qualified}`; // no need to encode here, handle in command

      lenses.push(
        new vscode.CodeLens(range, {
          title: '$(repo) Repository Intelligence',
          command: 'repoIntelligence.showCodeLensQuickPick',
          arguments: [{ owner, repo, filePath, symbol, functionId }],
          tooltip: 'Open Repository Intelligence actions for this symbol',
        })
      );
    }

    return lenses;
  }

  resolveCodeLens(lens: vscode.CodeLens): vscode.CodeLens {
    return lens;
  }
}
