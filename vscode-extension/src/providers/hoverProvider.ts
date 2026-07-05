/**
 * Hover provider — shows symbol intelligence cards when the developer hovers
 * over a function or class name.
 *
 * Data is fetched from the backend symbol index and call graph.
 * Results are cached per file to avoid hammering the backend on every mouseover.
 */

import * as vscode from 'vscode';
import {
  client,
  Symbol as RepoSymbol,
  FileSymbolsResponse,
} from '../api';
import { DocumentLruCache } from '../utils/lruCache';
import { StateService } from '../utils/stateService';

// Bounded LRU Cache (max 50 documents)
export const hoverCache = new DocumentLruCache<RepoSymbol[]>(50);
// Track in-flight requests to debounce
const inFlight = new Set<string>();

function getActiveRepo(): string {
  return StateService.getActiveRepository();
}

function repoToOwnerRepo(identifier: string): [string, string] | null {
  const parts = identifier.split('/');
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    return null;
  }
  return [parts[0], parts[1]];
}

/**
 * Get the relative file path of the document within the workspace.
 */
function getRelativePath(document: vscode.TextDocument): string {
  const wsFolder = vscode.workspace.getWorkspaceFolder(document.uri);
  if (wsFolder) {
    return vscode.workspace.asRelativePath(document.uri, false);
  }
  return document.uri.fsPath;
}

/**
 * Fetch and cache symbols for a file. Returns null when the backend is
 * unreachable or no symbol index exists yet.
 */
async function getSymbolsForFile(
  owner: string,
  repo: string,
  filePath: string,
  document: vscode.TextDocument
): Promise<RepoSymbol[] | null> {
  const uriStr = document.uri.toString();
  const cached = hoverCache.get(uriStr);
  if (cached && cached.version === document.version) {
    return cached.value;
  }

  const cacheKey = `${owner}/${repo}::${filePath}`;
  if (inFlight.has(cacheKey)) {
    return null; // debounce concurrent requests
  }

  inFlight.add(cacheKey);
  try {
    const result: FileSymbolsResponse = await client.getFileSymbols(owner, repo, filePath);
    hoverCache.set(uriStr, { value: result.symbols, version: document.version });
    return result.symbols;
  } catch {
    // Return null silently — hover should never surface errors to the user
    return null;
  } finally {
    inFlight.delete(cacheKey);
  }
}

/**
 * Find the symbol whose definition range contains the hover position.
 */
function findSymbolAtPosition(
  symbols: RepoSymbol[],
  word: string
): RepoSymbol | null {
  // First try exact name match, then qualified name match
  return (
    symbols.find((s) => s.name === word) ??
    symbols.find((s) => s.qualified.endsWith(`.${word}`) || s.qualified === word) ??
    null
  );
}

/**
 * Build a rich Markdown hover card from a symbol and optional API surface info.
 */
function buildHoverContent(symbol: RepoSymbol): vscode.MarkdownString {
  const md = new vscode.MarkdownString();
  md.isTrusted = true;
  md.supportHtml = false;

  const typeIcon =
    symbol.symbol_type === 'class'
      ? '$(symbol-class)'
      : symbol.symbol_type === 'method'
      ? '$(symbol-method)'
      : '$(symbol-function)';

  md.appendMarkdown(`**${typeIcon} \`${symbol.qualified}\`**\n\n`);

  md.appendMarkdown(`| Property | Value |\n|---|---|\n`);
  md.appendMarkdown(`| Type | \`${symbol.symbol_type}\` |\n`);
  md.appendMarkdown(`| File | \`${symbol.file_path}\` |\n`);
  md.appendMarkdown(`| Line | ${symbol.line_number} |\n`);
  md.appendMarkdown(`| Language | ${symbol.language} |\n`);

  if (symbol.parent_class) {
    md.appendMarkdown(`| Class | \`${symbol.parent_class}\` |\n`);
  }

  if (typeof symbol.fan_in === 'number') {
    md.appendMarkdown(`| Fan-in (callers) | ${symbol.fan_in} |\n`);
  }
  if (typeof symbol.fan_out === 'number') {
    md.appendMarkdown(`| Fan-out (callees) | ${symbol.fan_out} |\n`);
  }

  md.appendMarkdown('\n---\n');
  md.appendMarkdown('_Repo Intelligence Agent_');

  return md;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export class RepoIntelligenceHoverProvider implements vscode.HoverProvider {
  async provideHover(
    document: vscode.TextDocument,
    position: vscode.Position,
    _token: vscode.CancellationToken
  ): Promise<vscode.Hover | null> {
    const repoId = getActiveRepo();
    if (!repoId) {
      return null; // not connected to a repository
    }

    const ownerRepo = repoToOwnerRepo(repoId);
    if (!ownerRepo) {
      return null;
    }
    const [owner, repo] = ownerRepo;

    const wordRange = document.getWordRangeAtPosition(position, /[\w$]+/);
    if (!wordRange) {
      return null;
    }
    const word = document.getText(wordRange);
    if (!word || word.length < 2) {
      return null;
    }

    const filePath = getRelativePath(document);
    const symbols = await getSymbolsForFile(owner, repo, filePath, document);
    if (!symbols) {
      return null;
    }

    const symbol = findSymbolAtPosition(symbols, word);
    if (!symbol) {
      return null;
    }

    const content = buildHoverContent(symbol);
    return new vscode.Hover(content, wordRange);
  }
}
