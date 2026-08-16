/**
 * Shared risk-level styling helpers.
 * Pairs with the semantic tokens defined in tailwind.config.mjs (success/warn/danger).
 */

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;

export function riskBadgeClass(level: RiskLevel): string {
  switch ((level || '').toUpperCase()) {
    case 'CRITICAL':
    case 'DANGEROUS':
      return 'bg-danger/10 text-danger border-danger/30';
    case 'HIGH':
      return 'bg-warn/10 text-warn border-warn/30';
    case 'MEDIUM':
    case 'REVIEW':
      return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30';
    default:
      return 'bg-success/10 text-success border-success/30';
  }
}

export function riskTextClass(level: RiskLevel): string {
  switch ((level || '').toUpperCase()) {
    case 'CRITICAL': return 'text-danger';
    case 'HIGH':     return 'text-warn';
    case 'MEDIUM':   return 'text-yellow-400';
    default:         return 'text-success';
  }
}

/**
 * Text tone for a PR size bucket. Same thresholds as `sizeBadgeClass`, for
 * places that carry the reading as coloured text rather than a filled badge.
 */
export function sizeTextClass(size: string): string {
  switch ((size || '').toUpperCase()) {
    case 'XL': return 'text-danger';
    case 'L':  return 'text-warn';
    case 'M':  return 'text-yellow-400';
    case 'S':  return 'text-success';
    default:   return 'text-text-muted';
  }
}

/**
 * Text tone for a blast radius. Kept separate from `riskTextClass` because the
 * blast vocabulary tops out at EXTREME, which would otherwise fall through to
 * the green default and report the most severe reading as healthy.
 */
export function blastTextClass(level: string): string {
  switch ((level || '').toUpperCase()) {
    case 'EXTREME': return 'text-danger';
    case 'HIGH':    return 'text-warn';
    case 'MEDIUM':  return 'text-yellow-400';
    case 'LOW':     return 'text-success';
    default:        return 'text-text-muted';
  }
}

export function sizeBadgeClass(size: string): string {
  switch ((size || '').toUpperCase()) {
    case 'XL': return 'bg-danger/10 text-danger border-danger/30';
    case 'L':  return 'bg-warn/10 text-warn border-warn/30';
    case 'M':  return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30';
    case 'S':  return 'bg-success/10 text-success border-success/30';
    default:   return 'bg-surface-2 text-text-muted border-border';
  }
}

export function effortBadgeClass(effort: string): string {
  switch ((effort || '').toUpperCase()) {
    case 'HIGH':   return 'bg-danger/10 text-danger border-danger/30';
    case 'MEDIUM': return 'bg-warn/10 text-warn border-warn/30';
    default:       return 'bg-success/10 text-success border-success/30';
  }
}
