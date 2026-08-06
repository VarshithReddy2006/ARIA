/**
 * TypeScript SDK Models for RIA Platform.
 */

export interface SDKResponseTS {
  isSuccess: boolean;
  data?: Record<string, unknown>;
  errorMessage?: string;
}

export interface SearchOptionsTS {
  repoId: string;
  queryText: string;
}

export interface AskOptionsTS {
  repoId: string;
  question: string;
}
